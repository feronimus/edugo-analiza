"""The analysis itself: speech detection, transcription and voice fingerprints, spread over worker processes.

Speed tricks (none of them changes the result):
  - Speech detection runs on fixed 2-minute blocks in parallel. Fixed, so the result doesn't depend on how many
    cores a computer has.
  - Speech pieces are sorted by length before batching, so a batch isn't padded to one long piece.
  - Several worker processes, each with its own copy of the models; the audio is shared through shared memory.
  - Each worker also computes the voice fingerprints for its pieces, so that overlaps with transcription.
Workers stay loaded between analyses and are closed after a while of inactivity by the server.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import sys
import threading
import time
from multiprocessing import shared_memory

import numpy as np

from . import VERSION, UserError, config
from .audio import SR
from .language import tag_words
from .voices import assign_roles

MAX_PIECE_S = 15.0          # touching speech pieces are joined up to this length
BATCH_AUDIO_S = 80.0        # max padded audio per model call (batch size x longest piece)
BATCH_MAX = 16
SPEECH_OPTS = dict(min_silence_duration_ms=300, max_speech_duration_s=15, speech_pad_ms=100, min_speech_duration_ms=150)
BLOCK_S = 120.0
BLOCK_OVERLAP_S = 16.0      # longer than any speech piece, so a piece starting in a block also ends in it
MAX_WORD_S = 1.2            # a word can't be longer than this (pauses inside a piece are not speech)
SENTENCE_MAX_S = 8.0        # longer sentences are cut, so one fingerprint doesn't cover two speakers
FINGERPRINT_PAD_S = 0.15    # audio added around a sentence for its fingerprint
CPU_MODES = {"full": 0, "balanced": 1, "light": 2}    # how many cores to leave free for other programs

# With pythonw.exe (no console) Windows would start every worker with the console python.exe and each one would
# open a terminal window. Point multiprocessing at pythonw.exe instead.
if os.name == "nt" and sys.executable.lower().endswith("pythonw.exe"):
    _pythonw = os.path.join(os.path.dirname(getattr(sys, "_base_executable", sys.executable)), "pythonw.exe")
    if os.path.exists(_pythonw):
        sys._base_executable = _pythonw


# ---------------------------------------------------------------- inside a worker process
_worker: dict = {}


def _start_worker(data_dir: str):
    if sys.stdout is None or sys.stderr is None:      # pythonw: libraries must be able to print
        sys.stdout = sys.stdout or open(os.devnull, "w")
        sys.stderr = sys.stderr or open(os.devnull, "w")
    try:                                              # keep the computer responsive during an analysis
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
        else:
            os.nice(5)
    except Exception:
        pass
    os.environ["EDUGO_DATA"] = data_dir
    os.environ.setdefault("HF_HOME", os.path.join(data_dir, "hf"))
    import onnx_asr
    import onnxruntime as rt
    import sherpa_onnx
    so = rt.SessionOptions()
    so.intra_op_num_threads = 1
    so.inter_op_num_threads = 1
    _worker["asr"] = onnx_asr.load_model(config.ASR_MODEL, quantization="int8", sess_options=so).with_timestamps()
    _worker["voice"] = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(config.SPEAKER_MODEL), num_threads=1))


def _shared_audio(name: str, n: int) -> np.ndarray:
    if _worker.get("shm_name") != name:
        if "shm" in _worker:
            _worker["shm"].close()
        _worker["shm"] = shared_memory.SharedMemory(name=name)
        _worker["shm_name"] = name
    return np.ndarray((n,), dtype=np.float32, buffer=_worker["shm"].buf)


def _find_speech(task):
    """(shm, n, start, end) -> speech pieces that start inside [start, end)."""
    name, n, a, b = task
    audio = _shared_audio(name, n)
    if "vad" not in _worker:
        import onnx_asr
        _worker["vad"] = onnx_asr.load_vad("silero")
    lo, hi = int(a * SR), min(n, int((b + BLOCK_OVERLAP_S) * SR))
    block = np.ascontiguousarray(audio[lo:hi])
    segs = next(iter(_worker["vad"].segment_batch(block[None, :], np.array([len(block)]), SR, **SPEECH_OPTS)))
    return [((s + lo) / SR, (e + lo) / SR) for s, e in segs if a <= (s + lo) / SR < b]


def _transcribe(task):
    """(shm, n, [(piece_id, start, end), ...]) -> words, sentences and a voice fingerprint per sentence."""
    name, n, pieces = task
    audio = _shared_audio(name, n)
    results = _worker["asr"].recognize([audio[int(a * SR):int(b * SR)] for _, a, b in pieces], sample_rate=SR)
    out = []
    for (pid, a, b), res in zip(pieces, results):
        words = tokens_to_words(res, a, b)
        for w in words:
            w["seg"] = pid
        sentences = split_sentences(words)
        prints = []
        for s in sentences:
            t0, t1 = words[s[0]]["t0"], words[s[-1]]["t1"]
            st = _worker["voice"].create_stream()
            st.accept_waveform(SR, audio[int(max(0.0, t0 - FINGERPRINT_PAD_S) * SR):
                                         int(min(n / SR, t1 + FINGERPRINT_PAD_S) * SR)])
            st.input_finished()
            if _worker["voice"].is_ready(st):
                e = np.asarray(_worker["voice"].compute(st), dtype=np.float32)
                prints.append((e / (np.linalg.norm(e) or 1.0)).tobytes())
            else:
                prints.append(None)
        out.append((pid, words, [(s[0], s[-1]) for s in sentences], prints))
    return out, sum(b - a for _, a, b in pieces)


def _ready(_):
    return os.getpid()


# ---------------------------------------------------------------- words and sentences
def tokens_to_words(res, start: float, end: float) -> list[dict]:
    """Join the recogniser's sub-word tokens into words with start/end time and mean confidence (lp)."""
    toks = res.tokens or []
    lps = res.logprobs or [0.0] * len(toks)
    words: list[dict] = []
    for tok, t, lp in zip(toks, res.timestamps or [], lps):
        core = tok.strip()
        if not core:
            continue
        if not any(ch.isalnum() for ch in core):      # punctuation sticks to the previous word
            if words:
                words[-1]["text"] += core
            continue
        if tok.startswith(" ") or not words:
            words.append({"text": core, "t0": start + float(t), "lps": [float(lp)]})
        else:
            words[-1]["text"] += core
            words[-1]["lps"].append(float(lp))
    for i, w in enumerate(words):
        nxt = words[i + 1]["t0"] if i + 1 < len(words) else end
        w["t1"] = round(max(w["t0"] + 0.05, min(nxt, w["t0"] + MAX_WORD_S, end)), 3)
        w["t0"] = round(w["t0"], 3)
        w["lp"] = round(float(np.mean(w.pop("lps"))), 2)
    return words


def split_sentences(words: list[dict]) -> list[list[int]]:
    """Word indices per sentence: split at . ? ! and cut sentences longer than SENTENCE_MAX_S in halves."""
    found, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        if w["text"][-1:] in ".?!":
            found.append(cur)
            cur = []
    if cur:
        found.append(cur)
    sentences = []
    for s in found:
        if words[s[-1]]["t1"] - words[s[0]]["t0"] <= SENTENCE_MAX_S:
            sentences.append(s)
            continue
        part = []
        for i in s:
            part.append(i)
            if words[i]["t1"] - words[part[0]]["t0"] >= SENTENCE_MAX_S / 2:
                sentences.append(part)
                part = []
        if part:
            sentences.append(part)
    return sentences


# ---------------------------------------------------------------- main process
def _ram_gb() -> float:
    try:
        if os.name == "nt":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MemoryStatus()
            m.dwLength = ctypes.sizeof(MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 1e9
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except Exception:
        return 8.0


def plan_workers(mode: str = "balanced", cores: int | None = None) -> int:
    """One worker per physical core, minus the cores to keep free, limited by memory (about 1 GB per worker).
    Measured on a 6-core Ryzen: 6 workers x 1 thread beats 3x2 and 2x3."""
    if not cores:
        n = os.cpu_count() or 4
        cores = max(1, n // 2) if n >= 4 else n       # hyper-threading siblings don't help here
    free = CPU_MODES.get(mode, 1)
    usable = max(1, cores - free) if cores > 2 else max(1, cores - min(free, 1))
    by_ram = max(1, int((_ram_gb() - 3.5) // 1.0))
    return int(os.environ.get("EDUGO_WORKERS", "0")) or max(1, min(usable, by_ram))


class Analyzer:
    def __init__(self, workers: int | None = None):
        self.fixed = workers is not None
        self.workers = workers or plan_workers()
        self.pool = None
        self._lock = threading.Lock()

    def set_mode(self, mode: str):
        """Use more or less of the CPU. The result is the same; only the time changes."""
        if self.fixed or mode not in CPU_MODES:
            return
        w = plan_workers(mode)
        if w != self.workers:
            with self._lock:
                self.close()
                self.workers = w

    def load(self, log=lambda m: None):
        with self._lock:
            if self.pool is not None:
                return
            config.ensure_models(log)
            log("Wczytywanie modeli…")
            self.pool = mp.get_context("spawn").Pool(self.workers, initializer=_start_worker,
                                                     initargs=(str(config.DATA_DIR),))
            try:
                self.pool.map_async(_ready, range(self.workers)).get(timeout=900)
            except Exception:
                self.close()
                raise

    def close(self):
        if self.pool:
            try:
                self.pool.terminate()
            except Exception:
                pass
            self.pool = None

    def _worker_pids(self):
        try:
            return frozenset(p.pid for p in self.pool._pool)
        except Exception:
            return frozenset()

    def analyze(self, audio: np.ndarray, progress=lambda stage, frac, msg: None, cancel=lambda: False) -> dict:
        """If a worker dies or hangs (out of memory, killed, sleep/wake...) the workers are restarted and the analysis
        is repeated once, with half as many workers."""
        try:
            return self._analyze(audio, progress, cancel)
        except UserError:
            raise
        except Exception:
            if cancel():
                raise UserError("Analiza przerwana.")
            self.close()
            if not self.fixed:
                self.workers = max(1, self.workers // 2)
            progress("models", 0.0, "Wystąpił chwilowy problem – ponawiam analizę…")
            return self._analyze(audio, progress, cancel)

    def _analyze(self, audio: np.ndarray, progress, cancel) -> dict:
        self.load(lambda m: progress("models", 0.0, m))
        started = time.perf_counter()
        timings = {}
        dur = len(audio) / SR
        if dur < 5:
            raise UserError("Nagranie jest za krótkie.")
        shm = shared_memory.SharedMemory(create=True, size=audio.nbytes)
        try:
            np.ndarray(audio.shape, dtype=np.float32, buffer=shm.buf)[:] = audio
            t0 = time.perf_counter()
            progress("asr", 0.0, "Wykrywanie mowy…")
            pieces = self._speech_pieces(shm.name, len(audio))
            timings["speech_detection_s"] = round(time.perf_counter() - t0, 1)
            if not pieces:
                raise UserError("Nie wykryto mowy w nagraniu.")
            t0 = time.perf_counter()
            per_piece = self._transcribe_all(shm.name, len(audio), pieces, progress, cancel)
            timings["transcription_s"] = round(time.perf_counter() - t0, 1)
        finally:
            shm.close()
            shm.unlink()

        t0 = time.perf_counter()
        words, units, prints = [], [], []
        for pid in range(len(pieces)):
            if pid not in per_piece:
                continue
            ws, sentences, ps = per_piece[pid]
            base = len(words)
            words.extend(ws)
            for (a, b), e in zip(sentences, ps):
                for i in range(base + a, base + b + 1):
                    words[i]["unit"] = len(units)
                units.append({"t0": round(words[base + a]["t0"], 2), "t1": round(words[base + b]["t1"], 2)})
                prints.append(None if e is None else np.frombuffer(e, dtype=np.float32))
        if len(units) < 3:
            raise UserError("Za mało mowy, żeby odróżnić nauczyciela od uczniów.")
        tag_words(words)
        border = assign_roles(units, words, prints)
        timings["roles_s"] = round(time.perf_counter() - t0, 1)
        timings["total_s"] = round(time.perf_counter() - started, 1)
        timings["workers"] = self.workers
        progress("done", 1.0, "Gotowe")
        return {"version": VERSION, "duration_s": round(dur, 1), "timings": timings, "border": round(border, 3),
                "units": units, "words": words}

    def _speech_pieces(self, shm_name: str, n: int) -> list[tuple[float, float]]:
        dur = n / SR
        blocks = [(shm_name, n, a, min(dur, a + BLOCK_S)) for a in np.arange(0, dur, BLOCK_S)]
        found = sorted(s for part in self.pool.map_async(_find_speech, blocks).get(timeout=600) for s in part)
        pieces = []
        for a, b in found:
            if pieces and a <= pieces[-1][1] and b - pieces[-1][0] <= MAX_PIECE_S:
                pieces[-1][1] = b
            else:
                pieces.append([a, b])
        return [(a, b) for a, b in pieces]

    def _transcribe_all(self, shm_name, n, pieces, progress, cancel) -> dict:
        order = sorted(range(len(pieces)), key=lambda i: pieces[i][1] - pieces[i][0], reverse=True)
        batches, cur = [], []
        for i in order:
            longest = (pieces[cur[0]][1] - pieces[cur[0]][0]) if cur else 0
            if cur and (len(cur) >= BATCH_MAX or (len(cur) + 1) * longest > BATCH_AUDIO_S):
                batches.append(cur)
                cur = []
            cur.append(i)
        if cur:
            batches.append(cur)
        tasks = [(shm_name, n, [(i, pieces[i][0], pieces[i][1]) for i in b]) for b in batches]
        total = sum(b - a for a, b in pieces)
        done = 0.0
        per_piece = {}
        results = self.pool.imap_unordered(_transcribe, tasks)
        pids = self._worker_pids()
        for _ in tasks:
            waited = 0
            while True:                          # a dead worker would otherwise make us wait forever
                try:
                    res, secs = results.next(timeout=2)
                    break
                except mp.TimeoutError:
                    waited += 2
                    if cancel():
                        self.close()
                        raise UserError("Analiza przerwana.")
                    if self._worker_pids() != pids or waited > 900:
                        raise RuntimeError("worker died or hung")
            if cancel():
                self.close()
                raise UserError("Analiza przerwana.")
            for pid, words, sentences, prints in res:
                per_piece[pid] = (words, sentences, prints)
            done += secs
            progress("asr", min(1.0, done / total), f"Rozpoznawanie mowy i głosów… {done / total * 100:.0f}%")
        return per_piece
