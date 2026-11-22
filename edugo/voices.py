"""Who is speaking: the teacher, or one of the students?

Every sentence gets a voice fingerprint (CAM++ model). In a lesson the teacher is the voice that talks the most, so:
  1. Fingerprints are centred on the lesson average. That removes what all voices share in a Teams recording
     (codec, room, microphone colour) and leaves what makes voices different.
  2. A "teacher voice" is built from the long sentences and refined a few times, keeping the sentences that sound most
     like it. Every sentence then gets a similarity to the teacher voice.
  3. The border between teacher and students is set per lesson: a two-group model is fitted to the similarities and
     the border is where the "students" group becomes more likely.
  4. Played recordings are taken out (see recordings.py) and the border is computed again without them, so that a
     long video can't push it around.
  5. Some teachers sound different in English than in Polish (a livelier "teaching voice"). Their English then looks
     less like the teacher voice, which is built mostly from whichever language they speak more. So English and
     Polish sentences each get their own border as well. That border is used only when it is clearly lower than the
     lesson border, never higher: it can give speech back to the teacher, but never take any away.
"""
from __future__ import annotations

import numpy as np

from .recordings import find_recordings

LONG_SENTENCE_S = 1.5     # only sentences at least this long build the teacher voice
TEACHER_KEEP = 0.65       # share of long sentences used to rebuild the teacher voice each round
BORDER_LIMITS = (-0.6, 0.3)
SEED_MIN = 8              # sentences with typical teacher phrases needed to start the teacher voice from them
ENGLISH_SEEDS_MIN = 15    # English sentences with teacher phrases needed to learn the teacher's "English voice"
LANGUAGE_GROUP_MIN = 40   # sentences needed in one language before it gets its own border
LANGUAGE_DROP_MIN = 0.1   # a language border is used only when it is clearly lower; smaller differences are noise
LANGUAGE_SENTENCE_MIN_S = 1.2   # single words are too short for a reliable fingerprint and keep the lesson border


def teacher_similarity(E: np.ndarray, dur: np.ndarray, keep: float = TEACHER_KEEP, rounds: int = 8,
                       seeds: np.ndarray | None = None) -> np.ndarray:
    X = E - E.mean(0)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    long = dur >= LONG_SENTENCE_S
    if long.sum() < 5:
        long = np.ones(len(dur), bool)
    start = seeds if seeds is not None and seeds.sum() >= SEED_MIN else long
    c = (X[start] * dur[start, None]).sum(0)
    c /= np.linalg.norm(c) + 1e-9
    for _ in range(rounds):
        s = X @ c
        closest = long & (s >= np.percentile(s[long], 100 * (1 - keep)))
        c = (X[closest] * dur[closest, None]).sum(0)
        c /= np.linalg.norm(c) + 1e-9
    return X @ c


def teacher_border(s: np.ndarray, w: np.ndarray) -> float:
    """Fit two Gaussians (teacher, students) to the similarities, weighted by duration, and return where they cross."""
    if len(s) < 10:
        return 0.0
    mu = np.percentile(s, [20, 80]).astype(float)
    sd = np.array([s.std(), s.std()]) + 1e-3
    pi = np.array([0.3, 0.7])
    for _ in range(200):
        p = np.stack([pi[k] / sd[k] * np.exp(-0.5 * ((s - mu[k]) / sd[k]) ** 2) for k in range(2)]) + 1e-12
        r = p / p.sum(0) * w
        pi = r.sum(1) / r.sum()
        mu = (r * s).sum(1) / (r.sum(1) + 1e-12)
        sd = np.sqrt((r * (s - mu[:, None]) ** 2).sum(1) / (r.sum(1) + 1e-12)) + 1e-3
    lo, hi = int(np.argmin(mu)), int(np.argmax(mu))
    grid = np.linspace(mu[lo], mu[hi], 400)
    dens = [pi[k] / sd[k] * np.exp(-0.5 * ((grid - mu[k]) / sd[k]) ** 2) for k in (lo, hi)]
    cross = grid[int(np.argmax(dens[1] > dens[0]))]
    return float(min(max(cross, BORDER_LIMITS[0]), BORDER_LIMITS[1]))


def _language_borders(units: list[dict], words: list[dict], border: float) -> list[float]:
    """The border to use for each sentence: the lesson border, or a lower one for its language (see point 5)."""
    en = np.zeros(len(units))
    pl = np.zeros(len(units))
    for w in words:
        if w["tag"] == "en":
            en[w["unit"]] += w["t1"] - w["t0"]
        elif w["tag"] == "pl":
            pl[w["unit"]] += w["t1"] - w["t0"]
    sim = np.array([u["sim"] for u in units])
    dur = np.array([u["t1"] - u["t0"] for u in units])
    live = np.array([not u["recording"] for u in units])
    borders = np.full(len(units), border)
    for group in ((en > pl) & live, (pl >= en) & (pl > 0) & live):
        if group.sum() >= LANGUAGE_GROUP_MIN:
            own = teacher_border(sim[group], dur[group])
            if border - own >= LANGUAGE_DROP_MIN:
                borders[group & (dur >= LANGUAGE_SENTENCE_MIN_S)] = own
    return borders.tolist()


def _english_voice(units: list[dict], words: list[dict], E: np.ndarray, have: list[int], seeds: np.ndarray,
                   dur: np.ndarray) -> None:
    """Many teachers switch to a livelier voice for English classroom phrases ("Excellent!", "Can you read it?").
    The main fingerprint, built mostly from calm explanations, misses those, so they end up with the students.
    Learn a second teacher fingerprint from English sentences with teacher phrases, and give the teacher the
    English sentences that clearly match it. It can only move sentences to the teacher, never away."""
    en, pl = np.zeros(len(units)), np.zeros(len(units))
    for w in words:
        d = w["t1"] - w["t0"]
        en[w["unit"]] += d * (w["tag"] == "en")
        pl[w["unit"]] += d * (w["tag"] == "pl")
    english = np.array([en[i] > pl[i] and not units[i]["recording"] for i in have])
    if (seeds & english).sum() < ENGLISH_SEEDS_MIN:
        return
    X = E - E.mean(0)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    c = X[seeds & english].sum(0)
    sim = X @ (c / np.linalg.norm(c))
    border = teacher_border(sim[english], dur[english])
    for row in np.where(english & (sim >= border) & (dur >= LANGUAGE_SENTENCE_MIN_S))[0]:
        units[have[row]]["teacher"] = True


def assign_roles(units: list[dict], words: list[dict], embs: list) -> float:
    """Set unit["sim"] (similarity to the teacher), unit["recording"] and unit["teacher"] for every sentence;
    return the lesson border."""
    have = [i for i, e in enumerate(embs) if e is not None]
    have_set = set(have)
    E = np.stack([embs[i] for i in have])
    dur = np.array([units[i]["t1"] - units[i]["t0"] for i in have])

    def set_similarities(rows, s):
        for row, v in zip(rows, s):
            units[have[row]]["sim"] = round(float(v), 3)
        for i, u in enumerate(units):          # sentences too short for a fingerprint take their neighbour's value
            if i not in have_set:
                u["sim"] = units[min(have, key=lambda h: abs(h - i))]["sim"]

    from .results import CHILD_PHRASES, TEACHER_PHRASES
    text = {}
    for w in words:
        text.setdefault(w["unit"], []).append(w["text"])
    seeds = np.array([bool(TEACHER_PHRASES.search(" ".join(text.get(i, [])))) and
                      not CHILD_PHRASES.search(" ".join(text.get(i, []))) for i in have]) & (dur >= 1.2)
    s = teacher_similarity(E, dur, seeds=seeds)
    border = teacher_border(s, dur)
    set_similarities(range(len(have)), s)

    recorded = find_recordings(units, words, embs, border)
    keep = [row for row, i in enumerate(have) if not recorded[i]]
    if recorded.any() and len(keep) >= 10:
        s = teacher_similarity(E[keep], dur[keep], seeds=seeds[keep])
        border = teacher_border(s, dur[keep])
        set_similarities(keep, s)
    for u, r in zip(units, recorded):
        u["recording"] = bool(r)
    for u, b in zip(units, _language_borders(units, words, border)):
        u["teacher"] = bool(u["sim"] >= b)
    _english_voice(units, words, E, have, seeds, dur)
    return border
