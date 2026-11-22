"""Results of earlier analyses, kept on this computer in data/history.json.

Only the numbers are kept (what the results screen shows), never the recording or the transcript.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse

from . import config
from .calibration import ENGINE, methodologist_scale
from .results import TYPICAL

FILE = config.DATA_DIR / "history.json"
LIMIT = 300
_lock = threading.Lock()


def lesson_name(url: str = "", filename: str = "") -> str:
    """A readable name: the Teams file name from a Dropbox link, or the uploaded file's name."""
    name = filename
    if url:
        path = urllib.parse.urlparse(url).path
        name = urllib.parse.unquote(path.rstrip("/").rsplit("/", 1)[-1]) if "/" in path else url
    name = re.sub(r"\.(mp4|m4a|mp3|wav|webm|mov|mkv)$", "", name, flags=re.I)
    name = re.sub(r"[- ]?\d{4}-?\d{8}_\d{6}UTC-Meeting[- ]Recording$", "", name)
    name = re.sub(r"-?\d{8}_\d{6}UTC-Meeting[- ]Recording$", "", name)
    if filename:
        return name.strip()[:150] or "nagranie"
    return name.replace("-", " ").replace("_", " ").strip()[:150] or "nagranie"


TITLE = re.compile(r"Zaj\w* grupy\s+(?:(STAŁE|DEMO)\s+)?(.+?)\s+((?:PN|WT|ŚR|CZ|PT|SB|ND)[A-ZŚ-]*)\s+(\d{1,2}):?(\d{2})"
                   r"\s+z dnia\s+(\d{4}-\d{2}-\d{2})", re.I)


def lesson_details(name: str) -> dict:
    """Teacher, group and date from a Teams title such as
    "Zajęcia grupy STAŁE Victoria Rachtan PNŚR 1950 z dnia 2026-09-02". The name in the title is the group's
    teacher; a substitute can be corrected by hand in the history."""
    m = TITLE.search(name or "")
    if not m:
        return {}
    kind, teacher, days, hh, mm, date = m.groups()
    return {"teacher": teacher.strip(), "kind": (kind or "DEMO").upper(), "lesson_date": date,
            "group": f"{(kind or 'DEMO').upper()} {teacher.strip()} {days} {int(hh)}:{mm}"}


def _read() -> list[dict]:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _write(items: list[dict]) -> None:
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[-LIMIT:], ensure_ascii=False), encoding="utf-8")
    tmp.replace(FILE)


def save(job_id: str, name: str, result: dict) -> None:
    with _lock:
        items = _read()
        old = next((i for i in items if i["id"] == job_id), None)
        if old:                                  # analysed again: keep the teacher name someone corrected
            old["result"] = result
        else:
            items.append({"id": job_id, "time": time.strftime("%Y-%m-%d %H:%M"), "name": name, "result": result,
                          **lesson_details(name)})
        _write(items)


def set_teacher(job_id: str, teacher: str) -> None:
    with _lock:
        items = _read()
        for i in items:
            if i["id"] == job_id:
                i["teacher"] = teacher.strip()[:80]
        _write(items)


def _rescaled(result: dict) -> dict:
    """The methodologist-scale number from the stored measurement and the current curve, so old and new entries
    (and the teacher trend) are always on the same scale; older entries also get the typical ranges."""
    if result.get("extra") and "typical" not in result["extra"]:    # saved before the typical ranges were shown
        result["extra"]["typical"] = TYPICAL
    m = result.get("methodologist")
    if m and m.get("measured_from_turn") is not None:
        m["teacher_pct"] = methodologist_scale(m["measured_from_turn"])
        m["curve"] = ENGINE
    return result


def listing() -> list[dict]:
    """Newest first, with just the numbers needed for the list."""
    out = []
    for i in reversed(_read()):
        r = _rescaled(i["result"])
        out.append({"id": i["id"], "time": i["time"], "name": i["name"], "teacher": i.get("teacher", ""),
                    "lesson_date": i.get("lesson_date", ""), "kind": i.get("kind", ""),
                    "teacher_en": r["teacher"]["en_pct"], "lesson_en": r["lesson"]["en_pct"],
                    "teacher_scale": (r.get("methodologist") or {}).get("teacher_pct"),
                    "teacher_talk": r["lesson"]["teacher_talk_pct"],
                    "extra": {k: (r.get("extra") or {}).get(k) for k in ("lesson_min", "small_talk_min",
                                                                         "praise_per_10min", "tech_mentions")}})
    return out


def get(job_id: str) -> dict | None:
    item = next((i for i in _read() if i["id"] == job_id), None)
    if item:
        _rescaled(item["result"])
    return item


def delete(job_id: str) -> None:
    with _lock:
        _write([i for i in _read() if i["id"] != job_id])
