"""Checking GitHub for a newer version and installing it with one click.

Only the program files are replaced. Models, settings and the history in data/ stay where they are, and the
Python environment is touched only when the list of libraries changed. The files being replaced are copied to
data/backup first and put back if anything goes wrong.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from . import VERSION, UserError, config

REPO = "feronimus/edugo-analiza"
ASSET = "eduGO_Analiza.zip"
CHECK_EVERY_S = 6 * 3600
KEEP = {"data", ".venv", "runtime", "settings.json"}      # never replaced or removed by an update

_cache: dict = {"checked": 0.0, "info": None}


def _version(tag: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in tag.lstrip("v").split("."))
    except ValueError:
        return (0,)


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "edugo-analiza"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def check(force: bool = False) -> dict:
    """Newest release on GitHub and the notes of every release newer than this one. Fails quietly when offline."""
    if not force and _cache["info"] is not None and time.time() - _cache["checked"] < CHECK_EVERY_S:
        return _cache["info"]
    info = {"current": VERSION, "available": False}
    try:
        releases = [r for r in _get_json(f"https://api.github.com/repos/{REPO}/releases?per_page=20")
                    if not r.get("draft") and not r.get("prerelease")]
        newer = sorted((r for r in releases if _version(r["tag_name"]) > _version(VERSION)),
                       key=lambda r: _version(r["tag_name"]), reverse=True)
        if newer and any(a["name"] == ASSET for a in newer[0].get("assets", [])):
            info.update(available=True, latest=newer[0]["tag_name"].lstrip("v"),
                        notes=[{"version": r["tag_name"].lstrip("v"), "text": (r.get("body") or "").strip()}
                               for r in newer])
    except Exception:
        pass
    _cache.update(checked=time.time(), info=info)
    return info


def _download(url: str, dst: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "edugo-analiza"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)


def _uv() -> Path:
    return config.APP_DIR / "runtime" / "bin" / ("uv.exe" if os.name == "nt" else "uv")


def _venv_python() -> Path:
    return config.APP_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _install_libraries() -> None:
    done = subprocess.run([str(_uv()), "pip", "install", "--python", str(_venv_python()), "-r",
                           str(config.APP_DIR / "requirements.txt")], capture_output=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if done.returncode:
        raise RuntimeError(done.stderr.decode(errors="replace")[-500:])


def install(log=print) -> str:
    """Download the newest release and put its files in place. Returns the new version."""
    info = check(force=True)
    if not info.get("available"):
        raise UserError("Masz już najnowszą wersję.")
    release = _get_json(f"https://api.github.com/repos/{REPO}/releases/tags/v{info['latest']}")
    url = next(a["browser_download_url"] for a in release["assets"] if a["name"] == ASSET)

    work = config.TMP_DIR / "update"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    log("Pobieranie nowej wersji…")
    try:
        _download(url, work / ASSET)
        with zipfile.ZipFile(work / ASSET) as z:
            z.extractall(work / "new")
    except Exception:
        raise UserError("Nie udało się pobrać nowej wersji. Sprawdź połączenie z internetem i spróbuj później.")
    new = work / "new" / "eduGO_Analiza"
    if not (new / "server.py").is_file() or not (new / "edugo" / "__init__.py").is_file():
        raise UserError("Pobrany plik nie jest prawidłową wersją programu eduGO. Aktualizację przerwano.")

    app = config.APP_DIR
    backup = config.DATA_DIR / "backup" / VERSION
    shutil.rmtree(backup, ignore_errors=True)
    backup.mkdir(parents=True)
    old_requirements = (app / "requirements.txt").read_text(encoding="utf-8") if (app / "requirements.txt").exists() else ""
    names = [p.name for p in app.iterdir() if p.name not in KEEP and p.name != "__pycache__"]
    log("Instalowanie…")
    libraries_changed = False
    try:
        for name in names:
            shutil.move(str(app / name), str(backup / name))
        for p in new.iterdir():
            if p.name not in KEEP:
                shutil.copytree(p, app / p.name) if p.is_dir() else shutil.copy2(p, app / p.name)
        if (app / "requirements.txt").read_text(encoding="utf-8") != old_requirements:
            log("Instalowanie dodatkowych składników…")
            libraries_changed = True
            _install_libraries()
    except Exception as e:
        print("update failed, restoring the previous version:", e, file=sys.stderr)
        for p in list(app.iterdir()):          # everything outside KEEP is now either new or half-copied
            if p.name not in KEEP:
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
        for name in names:
            shutil.move(str(backup / name), str(app / name))
        if libraries_changed:
            try:
                _install_libraries()           # back to the libraries the previous version was tested with
            except Exception as e2:
                print("could not restore libraries:", e2, file=sys.stderr)
        raise UserError("Aktualizacja się nie udała – przywrócono poprzednią wersję.")
    shutil.rmtree(work, ignore_errors=True)
    return info["latest"]


_WAIT_THEN_START = """
import socket, subprocess, sys, time
for _ in range(240):                       # wait up to a minute for the old copy to free its port
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", {port})):
            break
    time.sleep(0.25)
subprocess.Popen([sys.executable, {server!r}], cwd={app!r})
"""


def restart(port: int) -> None:
    """Start the updated program once this copy has stopped. A small separate helper does the waiting, so the
    new version needs no special start options."""
    exe = sys.executable
    if os.name == "nt" and exe.lower().endswith("python.exe"):
        exe = exe[:-len("python.exe")] + "pythonw.exe"
    code = _WAIT_THEN_START.format(port=port, server=str(config.APP_DIR / "server.py"), app=str(config.APP_DIR))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen([exe, "-c", code], cwd=str(config.APP_DIR), creationflags=flags, close_fds=True,
                     start_new_session=os.name != "nt")
