"""The teacher's English on the methodologists' scale.

Methodologists judge a lesson by ear and use the bands of their rating sheet (below). Their judgement sits higher than
a stopwatch: a teacher who speaks English about half of the time is usually rated "Niezła ilość języka angielskiego"
(60-79%). This module turns the measured share into a number on that scale.

Every lesson starts with a Polish opening (greeting, small talk, organisation) of its own length. The teacher's
English is measured from the moment this lesson turns mainly to English: the first two minutes in which English
takes at least as much time as Polish. A lesson that never turns to English is measured as a whole. The measured
share then goes through a rising curve to the methodologists' scale.

The curve belongs to the engine version it was made with: when the voice or language steps change, it is made again.
"""
from __future__ import annotations

import numpy as np

ENGINE = "2.3"
KNOTS_MEASURED = [0.0, 15.87, 25.32, 29.83, 33.85, 38.15, 39.16, 42.86, 46.84, 50.7, 52.17, 54.68, 59.49, 64.39,
                  69.9, 76.06, 89.08, 100.0]
KNOTS_BAND = [0.0, 0.0, 0.8, 1.2, 1.4, 1.5, 2.0, 2.364, 2.5, 3.25, 3.5, 3.538, 3.667, 3.8, 4.25, 4.5, 5.0, 5.0]
BANDS = [  # the bands of the rating sheet (the "translated too much" band is about translation, not amount, so it is left out)
    ("Dominacja języka polskiego", 0, 29),
    ("Niewielka ilość języka angielskiego", 29, 44),
    ("Umiarkowana ilość języka angielskiego", 45, 59),
    ("Niezła ilość języka angielskiego", 60, 79),
    ("Znaczna ilość języka angielskiego", 80, 89),
    ("Dominująca ilość języka angielskiego", 90, 100),
]
WINDOW_S, STEP_S = 120, 30


def english_turn(raw: dict) -> float | None:
    """Seconds from the first words until the lesson turns mainly to English, or None if it never does."""
    units = raw["units"]
    live = [w for w in raw["words"] if not units[w["unit"]]["recording"]]
    if not live:
        return None
    start, end = min(w["t0"] for w in live), max(w["t1"] for w in live)
    for t in np.arange(start, end - WINDOW_S, STEP_S):
        window = [w for w in live if t <= w["t0"] < t + WINDOW_S]
        en = sum(w["t1"] - w["t0"] for w in window if w["tag"] == "en")
        pl = sum(w["t1"] - w["t0"] for w in window if w["tag"] == "pl")
        if en + pl > 20 and en >= pl:
            return float(t - start)
    return None


def teacher_english_from_turn(raw: dict) -> tuple[float | None, float]:
    """The teacher's English share from the moment the lesson turns to English, and that moment in minutes."""
    units = raw["units"]
    live = [w for w in raw["words"] if not units[w["unit"]]["recording"]]
    if not live:
        return None, 0.0
    turn = english_turn(raw) or 0.0
    start = min(w["t0"] for w in live)
    en = pl = 0.0
    for w in live:
        if units[w["unit"]]["teacher"] and w["t0"] - start >= turn:
            en += (w["t1"] - w["t0"]) * (w["tag"] == "en")
            pl += (w["t1"] - w["t0"]) * (w["tag"] == "pl")
    return (100 * en / (en + pl) if en + pl > 0 else None), round(turn / 60, 1)


def methodologist_scale(measured: float | None) -> float | None:
    if measured is None:
        return None
    band = float(np.interp(measured, KNOTS_MEASURED, KNOTS_BAND))
    middles = [(lo + hi) / 2 for _, lo, hi in BANDS]
    return round(float(np.interp(band, range(len(BANDS)), middles)), 1)
