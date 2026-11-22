"""From tagged words to the numbers on the results screen."""
from __future__ import annotations

import re

from .calibration import ENGINE, english_turn, methodologist_scale, teacher_english_from_turn

# Phrases that sound like a teacher or like a child. They help find the teacher's voice and check the split:
# if the side called "students" talks much more like a teacher than the side called "teacher", the split is probably
# wrong and the results screen says so.
TEACHER_PHRASES = re.compile(
    r"\b(słuchajcie|powiedzcie|powiedz|przeczytaj|przeczytajcie|zobaczcie|spójrzcie|otwórzcie|zapiszcie|moi drodzy|"
    r"kto (?:chce|mi)|bardzo dobrze|świetnie|brawo|dokładnie|can you|could you|let's|let us|good job|well done|"
    r"very good|excellent|perfect|next one|read (?:the|it|this)|look at|repeat|open your|who (?:can|wants)|tell me|"
    r"thank you very much)\b", re.I)
CHILD_PHRASES = re.compile(r"\b(nie wiem|proszę pani|proszę panią|pani |mogę|ja mam|ja nie|nie rozumiem|i think|"
                           r"i don't know|can i|teacher)\b", re.I)
PRAISE = re.compile(r"\b(good job|well done|excellent|perfect|great|very good|amazing|fantastic|awesome|brilliant|nice|"
                    r"super|brawo|świetnie|bardzo dobrze|pięknie|doskonale|wspaniale)\b", re.I)
TECH_TALK = re.compile(r"(nie słychać|nie słyszę|słyszycie mnie|słychać mnie|słyszysz mnie|can you hear|nie widzę|"
                       r"widzicie mój|widzicie ekran|zacina|zaciął|zacięło|mikrofon|kamer|internet|rozłącz|wyrzuciło|"
                       r"zawiesi|nie działa|przerywa|you're muted)", re.I)
# What is usual for the extra metrics: the middle half (25th-75th percentile) of 86 eduGO lessons by many teachers.
TYPICAL = {"lesson_min": (59.4, 62.2), "small_talk_min": (3.8, 11.5), "praise_per_10min": (6.3, 13.3),
           "tech_mentions": (4.2, 13.0)}
ROLE_CHECK_MIN = -10.0     # measured on 63 lessons: normal ones -3 to +41, ones with mixed-up roles -11 to -32


def role_check(raw: dict) -> float:
    """How much more the "teacher" side talks like a teacher than the "students" side (per 1000 words)."""
    text = {True: [], False: []}
    for w in raw["words"]:
        u = raw["units"][w["unit"]]
        if not u["recording"]:
            text[u["teacher"]].append(w["text"])

    def rate(side, pattern):
        joined = " ".join(text[side])
        return 1000 * len(pattern.findall(joined)) / max(1, len(text[side]))
    return ((rate(True, TEACHER_PHRASES) - rate(False, TEACHER_PHRASES))
            - (rate(True, CHILD_PHRASES) - rate(False, CHILD_PHRASES)))


def extra_metrics(raw: dict) -> dict | None:
    """Experimental extras for the results screen, with the range that is typical for eduGO lessons (TYPICAL)."""
    units = raw["units"]
    live = [w for w in raw["words"] if not units[w["unit"]]["recording"]]
    if not live:
        return None
    start, end = live[0]["t0"], live[-1]["t1"]
    turn = english_turn(raw)              # from the first words until the lesson turns mainly to English
    small_talk = round(turn / 60, 1) if turn is not None else None
    teacher_text = " ".join(w["text"] for w in live if units[w["unit"]]["teacher"])
    lesson_min = (end - start) / 60
    return {"lesson_min": round(lesson_min, 1), "small_talk_min": small_talk,
            "praise_per_10min": round(10 * len(PRAISE.findall(teacher_text)) / max(lesson_min, 1), 1),
            "tech_mentions": len(TECH_TALK.findall(" ".join(w["text"] for w in live))), "typical": TYPICAL}


def timeline(raw: dict) -> list[list[float]]:
    """Seconds of [teacher English, teacher Polish, students English, students Polish] in each minute of the lesson,
    counted from the first words. Drawn as the lesson's course on the results screen."""
    units = raw["units"]
    live = [w for w in raw["words"] if not units[w["unit"]]["recording"] and w["tag"] in ("en", "pl")]
    if not live:
        return []
    start = min(w["t0"] for w in live)
    minutes = [[0.0, 0.0, 0.0, 0.0] for _ in range(int((max(w["t1"] for w in live) - start) // 60) + 1)]
    for w in live:
        col = (0 if units[w["unit"]]["teacher"] else 2) + (w["tag"] == "pl")
        minutes[int((w["t0"] - start) // 60)][col] += w["t1"] - w["t0"]
    return [[round(v, 1) for v in m] for m in minutes]


def _methodologist(raw: dict) -> dict:
    measured, from_minute = teacher_english_from_turn(raw)
    return {"teacher_pct": methodologist_scale(measured),
            "measured_from_turn": round(measured, 1) if measured is not None else None,
            "from_minute": from_minute, "curve": ENGINE}


def _pct(a: float, b: float) -> float | None:
    return round(100 * a / (a + b), 1) if a + b > 0 else None


def summarize(raw: dict) -> dict:
    """Percentages of English/Polish (by speaking time) for the lesson, the teacher and the students."""
    units = raw["units"]

    def role(u):
        if u["recording"]:
            return "recording"
        return "teacher" if u["teacher"] else "students"

    sec = {r: {"en": 0.0, "pl": 0.0, "other": 0.0} for r in ("teacher", "students", "recording")}
    for w in raw["words"]:
        w["role"] = role(units[w["unit"]])
        sec[w["role"]][w["tag"] if w["tag"] in ("en", "pl") else "other"] += w["t1"] - w["t0"]

    out = {}
    for r in ("teacher", "students"):
        s = sec[r]
        out[r] = {"speech_s": round(sum(s.values()), 1), "en_s": round(s["en"], 1), "pl_s": round(s["pl"], 1),
                  "en_pct": _pct(s["en"], s["pl"]), "pl_pct": _pct(s["pl"], s["en"])}
    t, st = out["teacher"], out["students"]
    talk = t["speech_s"] + st["speech_s"]
    en_all, pl_all = t["en_s"] + st["en_s"], t["pl_s"] + st["pl_s"]
    return {
        "version": raw["version"], "duration_s": raw["duration_s"], "timings": raw["timings"],
        "teacher": t, "students": st,
        "lesson": {
            "en_pct": _pct(en_all, pl_all), "pl_pct": _pct(pl_all, en_all), "en_s": round(en_all, 1),
            "pl_s": round(pl_all, 1),
            "teacher_talk_pct": round(100 * t["speech_s"] / talk, 1) if talk else None,
            "students_talk_pct": round(100 * st["speech_s"] / talk, 1) if talk else None,
            "students_share_of_english_pct": _pct(st["en_s"], t["en_s"]),
            "recordings_s": round(sum(sec["recording"].values()), 1),
            "roles_doubtful": role_check(raw) < ROLE_CHECK_MIN,
        },
        "extra": extra_metrics(raw),
        "methodologist": _methodologist(raw),
        "timeline": timeline(raw),
    }
