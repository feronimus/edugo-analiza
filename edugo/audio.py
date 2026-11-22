"""Getting the recording: Dropbox link -> temporary file -> 16 kHz mono audio."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

from . import UserError
from .config import TMP_DIR

SR = 16000
DROPBOX_HOSTS = ("dropbox.com", "www.dropbox.com", "dl.dropboxusercontent.com", "dl.dropbox.com")


def dropbox_direct_url(url: str) -> str:
    """A Dropbox share link with dl=1, which returns the file itself instead of the preview page."""
    url = url.strip()
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not any(p.netloc == h or p.netloc.endswith("." + h) for h in DROPBOX_HOSTS):
        raise UserError("To nie jest link do Dropboxa. Wklej link do udostępnionego pliku z Dropboxa (dropbox.com/…).")
    q = urllib.parse.parse_qs(p.query, keep_blank_values=True)
    q["dl"] = ["1"]
    return urllib.parse.urlunparse(p._replace(query=urllib.parse.urlencode(q, doseq=True)))


def download(url: str, progress=lambda frac, msg: None, cancel=lambda: False, info: dict | None = None) -> Path:
    """Download the recording, trying up to 3 times when the connection drops.
    The file's own name (the Teams title, with Polish letters) is put in info["filename"] when given."""
    url = dropbox_direct_url(url)
    if shutil.disk_usage(TMP_DIR).free < 1.5e9:
        raise UserError("Za mało wolnego miejsca na dysku (potrzeba ok. 1,5 GB). Zwolnij miejsce i spróbuj ponownie.")
    last_error = None
    for attempt in range(3):
        try:
            return _download_once(url, progress, cancel, info)
        except UserError:
            raise
        except Exception as e:
            last_error = e
            for _ in range(5 * (attempt + 1)):
                if cancel():
                    raise UserError("Analiza przerwana.")
                time.sleep(1)
            progress(0.0, f"Problem z połączeniem – ponawiam pobieranie ({attempt + 2}/3)…")
    raise UserError(f"Nie udało się pobrać nagrania z Dropboxa – sprawdź połączenie z internetem i link ({last_error}).")


def _file_name(content_disposition: str) -> str:
    m = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition or "")
    if m:
        return urllib.parse.unquote(m.group(1))
    m = re.search(r'filename="([^"]+)"', content_disposition or "")
    return m.group(1) if m else ""


def _download_once(url: str, progress, cancel, info: dict | None = None) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 eduGO-analiza"})
    fd, name = tempfile.mkstemp(suffix=".mp4", dir=TMP_DIR)
    os.close(fd)
    path = Path(name)
    try:
        try:
            response = urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:
            if e.code in (400, 403, 404, 410):
                raise UserError("Dropbox nie udostępnia tego pliku (link wygasł, został usunięty albo nie jest "
                                "publiczny). Sprawdź link w arkuszu.") from e
            raise
        with response as resp, open(path, "wb") as out:
            if "text/html" in resp.headers.get("Content-Type", ""):
                raise UserError("Dropbox zwrócił stronę zamiast pliku. Sprawdź, czy plik jest udostępniony "
                                "„każdemu, kto ma link”.")
            if info is not None:
                info["filename"] = _file_name(resp.headers.get("Content-Disposition", ""))
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            while chunk := resp.read(1 << 20):
                if cancel():
                    raise UserError("Analiza przerwana.")
                out.write(chunk)
                got += len(chunk)
                msg = f"Pobieranie nagrania… {got / 1e6:.0f} MB" + (f" z {total / 1e6:.0f} MB" if total else "")
                progress(got / total if total else 0.0, msg)
        if path.stat().st_size < 10_000:
            raise UserError("Pobrany plik jest pusty lub uszkodzony.")
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def load_audio(path: str | Path) -> np.ndarray:
    """Decode any audio or video file to 16 kHz mono float32 (PyAV bundles its own FFmpeg)."""
    import av
    try:
        container = av.open(str(path))
    except Exception as e:
        raise UserError("Nie da się odczytać pliku nagrania (nieobsługiwany format lub plik uszkodzony).") from e
    with container:
        if not container.streams.audio:
            raise UserError("Nagranie nie zawiera ścieżki dźwiękowej.")
        resampler = av.AudioResampler(format="flt", layout="mono", rate=SR)
        parts = []
        for frame in container.decode(container.streams.audio[0]):
            parts.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(frame))
        parts.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(None))
    if not parts:
        raise UserError("Ścieżka dźwiękowa jest pusta.")
    return np.concatenate(parts).astype(np.float32)
