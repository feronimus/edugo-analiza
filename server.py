"""eduGO Analiza - the local web app.

    python server.py --open

Starts on this computer only (127.0.0.1), picks a free port and opens the browser. Starting it a second time just
opens the browser on the copy that is already running.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import uuid
import webbrowser
from pathlib import Path

from edugo import VERSION, UserError, config, feedback, history, updates
from edugo.analyzer import Analyzer
from edugo.audio import download, load_audio
from edugo.results import summarize

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

STATIC = Path(__file__).resolve().parent / "static"
PORT_FILE = config.DATA_DIR / "port.txt"
IDLE_MINUTES = float(os.environ.get("EDUGO_IDLE_MINUTES", "15"))   # free the models' memory after this long idle

analyzer = Analyzer()
jobs: dict[str, dict] = {}
queued: "queue.Queue[str]" = queue.Queue()
last_activity = time.time()
update_state = {"status": "idle", "message": ""}
app = FastAPI(title="eduGO Analiza", version=VERSION)


def _update(job, stage=None, frac=None, msg=None):
    if stage is not None:
        job["stage"] = stage
    if frac is not None:
        job["progress"] = round(float(frac), 3)
    if msg is not None:
        job["message"] = msg


def _run_jobs():
    global last_activity
    while True:
        job = jobs.get(queued.get())
        last_activity = time.time()
        if not job or job["cancel"]:
            continue
        job["status"] = "running"
        job["started"] = time.time()
        path = None
        try:
            if job["source"] == "url":
                _update(job, "download", 0, "Pobieranie nagrania z Dropboxa…")
                info = {}
                path = download(job["url"], lambda f, m: _update(job, "download", f, m), lambda: job["cancel"], info)
                if info.get("filename"):
                    job["label"] = history.lesson_name(filename=info["filename"])
            else:
                path = Path(job["file"])
            analyzer.set_mode(job["mode"])
            _update(job, "decode", 0, "Odczyt ścieżki dźwiękowej…")
            audio = load_audio(path)
            raw = analyzer.analyze(audio, lambda s, f, m: _update(job, s, f, m), lambda: job["cancel"])
            del audio
            job["result"] = summarize(raw)
            job["status"] = "done"
            try:
                history.save(job["id"], job["label"], job["result"])
            except OSError:
                traceback.print_exc()      # the result is still shown, only the history entry is missing
            _update(job, "done", 1, "Gotowe")
        except UserError as e:
            job["status"] = "cancelled" if job["cancel"] else "error"
            job["error"] = str(e)
        except MemoryError:
            analyzer.close()
            job["status"] = "error"
            job["error"] = "Za mało pamięci na tym komputerze. Zamknij inne programy i spróbuj ponownie."
        except Exception as e:
            traceback.print_exc()
            analyzer.close()            # start from fresh workers next time
            job["status"] = "error"
            job["error"] = (f"Nieoczekiwany błąd ({type(e).__name__}). Spróbuj ponownie – jeśli błąd się powtórzy, "
                            "uruchom program jeszcze raz.")
        finally:
            if path and Path(path).exists():
                try:
                    Path(path).unlink()     # recordings are never kept
                except OSError:
                    pass
            job["finished"] = time.time()
            last_activity = time.time()


def _free_memory_when_idle():
    global last_activity
    while True:
        time.sleep(10)
        if any(j["status"] in ("queued", "running") for j in jobs.values()):
            last_activity = time.time()
        elif analyzer.pool is not None and time.time() - last_activity > IDLE_MINUTES * 60:
            analyzer.close()


def _warm_up():
    try:
        analyzer.load()
    except Exception:
        traceback.print_exc()           # the first job loads again and shows a clear message if it still fails


def _new_job(**fields) -> dict:
    job = {"id": uuid.uuid4().hex[:12], "status": "queued", "stage": "queued", "progress": 0.0,
           "message": "W kolejce…", "cancel": False, "created": time.time(), **fields}
    jobs[job["id"]] = job
    queued.put(job["id"])
    return job


def _public(job) -> dict:
    out = {k: job.get(k) for k in ("id", "status", "stage", "progress", "message", "error")}
    if job.get("started"):
        out["elapsed_s"] = round((job.get("finished") or time.time()) - job["started"], 1)
    out["queue_position"] = sum(1 for j in jobs.values() if j["status"] == "queued" and j["created"] < job["created"])
    if job.get("result"):
        out["result"] = job["result"]
    return out


def _job(jid: str) -> dict:
    if jid not in jobs:
        raise HTTPException(404, "Nie znaleziono tej analizy (być może program został uruchomiony ponownie).")
    return jobs[jid]


NO_CACHE = {"Cache-Control": "no-cache"}   # after an update the browser must not mix old and new scripts


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers=NO_CACHE)


MEDIA_TYPES = {".js": "text/javascript", ".css": "text/css", ".html": "text/html", ".png": "image/png",
               ".ico": "image/x-icon", ".svg": "image/svg+xml"}   # set here: Windows may map .js to text/plain


@app.get("/static/{name:path}")
def static_file(name: str):
    p = (STATIC / name).resolve()
    if STATIC not in p.parents or not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, media_type=MEDIA_TYPES.get(p.suffix.lower()), headers=NO_CACHE)


@app.get("/api/health")
def health():
    return {"app": "edugo", "version": VERSION, "models_loaded": analyzer.pool is not None,
            "workers": analyzer.workers}


@app.post("/api/jobs")
async def create_job(url: str = Form(""), mode: str = Form("balanced"), file: UploadFile | None = File(None)):
    if mode not in ("full", "balanced", "light"):
        mode = "balanced"
    if file is not None and file.filename:
        dst = config.TMP_DIR / f"upload_{uuid.uuid4().hex}{Path(file.filename).suffix[:8]}"
        with open(dst, "wb") as f:
            while chunk := await file.read(1 << 20):
                f.write(chunk)
        return _public(_new_job(source="file", file=str(dst), label=history.lesson_name(filename=file.filename),
                                mode=mode))
    if url.strip():
        return _public(_new_job(source="url", url=url.strip(), label=history.lesson_name(url=url.strip()), mode=mode))
    raise HTTPException(400, "Podaj link do nagrania albo wybierz plik.")


@app.get("/api/jobs")
def list_jobs():
    """Analyses started since the program was started, newest first (for the progress badge and the queue)."""
    out = []
    for job in sorted(jobs.values(), key=lambda j: j["created"], reverse=True):
        item = _public(job)
        item.pop("result", None)
        item["label"] = job.get("label", "")
        out.append(item)
    return out


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    return _public(_job(jid))


@app.post("/api/jobs/{jid}/cancel")
def cancel_job(jid: str):
    job = _job(jid)
    if job["status"] in ("queued", "running"):
        job["cancel"] = True
        if job["status"] == "queued":
            job["status"] = "cancelled"
            job["error"] = "Analiza przerwana."
    return {"ok": True}


@app.get("/api/history")
def history_list():
    return history.listing()


@app.get("/api/history/{hid}")
def history_item(hid: str):
    item = history.get(hid)
    if not item:
        raise HTTPException(404, "Nie ma takiej analizy w historii.")
    return item


@app.post("/api/history/{hid}/teacher")
def history_teacher(hid: str, teacher: str = Form("")):
    history.set_teacher(hid, teacher)
    return {"ok": True}


@app.delete("/api/history/{hid}")
def history_delete(hid: str):
    history.delete(hid)
    return {"ok": True}


@app.post("/api/open-data")
def open_data_folder():
    """Show the folder with the history, models and log in Explorer / Finder."""
    path = str(config.DATA_DIR)
    try:
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
    except OSError:
        raise HTTPException(500, f"Nie udało się otworzyć folderu: {path}")
    return {"ok": True, "path": path}


@app.get("/api/update")
def update_check(force: bool = False):
    return {**updates.check(force), **update_state}


def _install_update():
    try:
        update_state.update(status="running", message="Pobieranie nowej wersji…")
        updates.install(lambda m: update_state.update(message=m))
        update_state.update(status="restarting", message="Uruchamianie nowej wersji…")
        analyzer.close()
        updates.restart(int(PORT_FILE.read_text().strip()))
        time.sleep(1.5)                 # let the browser receive the last status
        os._exit(0)
    except UserError as e:
        update_state.update(status="error", message=str(e))
    except Exception:
        traceback.print_exc()
        update_state.update(status="error", message="Aktualizacja się nie udała. Spróbuj później.")


@app.post("/api/update")
def update_install():
    if any(j["status"] in ("queued", "running") for j in jobs.values()):
        raise HTTPException(409, "Poczekaj, aż skończą się trwające analizy.")
    if update_state["status"] not in ("running", "restarting"):
        threading.Thread(target=_install_update, daemon=True).start()
    return update_state


@app.get("/api/feedback")
def feedback_enabled():
    return {"enabled": feedback.enabled()}


@app.post("/api/feedback")
def feedback_send(text: str = Form("")):
    try:
        feedback.send(text)
    except UserError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.get("/api/jobs/{jid}/wyniki.csv")
def export_csv(jid: str):
    job = jobs.get(jid)
    if job is None:                         # an analysis from the history, after the program was restarted
        item = history.get(jid)
        if not item:
            raise HTTPException(404, "Nie ma takiej analizy.")
        job = {"result": item["result"], "label": item["name"]}
    if not job.get("result"):
        raise HTTPException(409, "Analiza jeszcze trwa.")
    r = job["result"]
    t, s, lesson = r["teacher"], r["students"], r["lesson"]
    rows = [["nagranie", job.get("label", "")],
            ["dlugosc_min", round(r["duration_s"] / 60, 1)],
            ["nauczyciel_angielski_skala_metodyka_%", (r.get("methodologist") or {}).get("teacher_pct")],
            ["nauczyciel_angielski_od_przejscia_na_angielski_%", (r.get("methodologist") or {}).get("measured_from_turn")],
            ["lekcja_przechodzi_na_angielski_od_min", (r.get("methodologist") or {}).get("from_minute")],
            ["lekcja_angielski_%", lesson["en_pct"]], ["lekcja_polski_%", lesson["pl_pct"]],
            ["nauczyciel_angielski_%", t["en_pct"]], ["nauczyciel_polski_%", t["pl_pct"]],
            ["uczniowie_angielski_%", s["en_pct"]], ["uczniowie_polski_%", s["pl_pct"]],
            ["nauczyciel_udzial_w_mowie_%", lesson["teacher_talk_pct"]],
            ["uczniowie_udzial_w_mowie_%", lesson["students_talk_pct"]],
            ["uczniowie_udzial_w_angielskim_%", lesson["students_share_of_english_pct"]],
            ["nagrania_odtwarzane_min", round(lesson["recordings_s"] / 60, 1)],
            ["eksperymentalne_dlugosc_lekcji_min", (r.get("extra") or {}).get("lesson_min")],
            ["eksperymentalne_small_talk_min", (r.get("extra") or {}).get("small_talk_min")],
            ["eksperymentalne_pochwaly_na_10_min", (r.get("extra") or {}).get("praise_per_10min")],
            ["eksperymentalne_wzmianki_o_technice", (r.get("extra") or {}).get("tech_mentions")],
            ["wersja", r["version"]]]
    buf = io.StringIO()
    csv.writer(buf, delimiter=";").writerows(
        [[k, str(v).replace(".", ",") if isinstance(v, float) else v] for k, v in rows])
    return Response("﻿" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="edugo_{jid}.csv"'})


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _running_copy() -> str | None:
    try:
        port = int(PORT_FILE.read_text().strip())
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
            if json.load(r).get("app") == "edugo":
                return f"http://127.0.0.1:{port}/"
    except Exception:
        pass
    return None


def main():
    if sys.stdout is None or not sys.stdout.isatty():     # started from the icon (Windows or Mac): log to a file
        sys.stdout = sys.stderr = open(config.DATA_DIR / "server.log", "a", encoding="utf-8", buffering=1)
    parser = argparse.ArgumentParser()
    parser.add_argument("--open", action="store_true", help="open the browser when ready")
    args, _ = parser.parse_known_args()       # options from other versions are ignored, never fatal

    url = _running_copy()
    if url:
        if args.open:
            webbrowser.open(url)
        return
    port = int(os.environ.get("EDUGO_PORT", "8765"))
    while not _port_free(port):
        port += 1
    PORT_FILE.write_text(str(port))
    for target in (_run_jobs, _warm_up, _free_memory_when_idle):
        threading.Thread(target=target, daemon=True).start()
    if args.open:
        def open_when_ready():
            for _ in range(100):
                if not _port_free(port):
                    webbrowser.open(f"http://127.0.0.1:{port}/")
                    return
                time.sleep(0.1)
        threading.Thread(target=open_when_ready, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
