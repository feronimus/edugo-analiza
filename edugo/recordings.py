"""Played recordings (textbook audio, slide videos, songs, quiz-app voices) are not counted as teacher or students.

Sentences are grouped by voice (voice fingerprints + average-linkage clustering). A group is a played recording
when ALL of these hold:
  - it speaks only English (>= 95 %), fluently (high recogniser confidence, no "uh/um" hesitations),
  - the same voice never speaks Polish anywhere in the lesson (the closest Polish sentences are far away in voice space).
    A real teacher or child reading English also speaks Polish at some point; a recorded narrator never does.
  - it is not the teacher's voice (the group's voice is far from the teacher's average voice). This matters in lessons
    where the teacher speaks almost only English - their English would otherwise look like a narrator.
On the hand-checked lessons it caught 57-100 % of the recorded time (single played words are the hardest) and
removed at most 2 s of real speech; it removed no teacher speech in any of the 7 almost-English-only lessons tested.
"""
from __future__ import annotations

import numpy as np

MIN_SIM = 0.55        # cosine similarity for "same voice"
MIN_UNIT_S = 0.8      # sentences shorter than this are too short for a reliable voice fingerprint
EN_MIN = 0.95
LP_MIN = -0.15        # mean token log-prob: recordings are recognised with high confidence
FILLER_MAX = 0.05
PL_NEIGHBOUR_MAX = 0.35
TEACHER_COS_MAX = 0.2   # recordings measured at -0.32..0.11 from the teacher's voice, real teacher groups at 0.47..0.85


def _cluster_by_voice(X: np.ndarray, min_sim: float) -> np.ndarray:
    n = len(X)
    S = X @ X.T
    np.fill_diagonal(S, -np.inf)
    size = np.ones(n)
    lab = np.arange(n)
    while n > 1:
        i, j = np.unravel_index(np.argmax(S), S.shape)
        if S[i, j] < min_sim:
            break
        S[i, :] = (S[i, :] * size[i] + S[j, :] * size[j]) / (size[i] + size[j])
        S[:, i] = S[i, :]
        S[i, i] = -np.inf
        S[j, :] = -np.inf
        S[:, j] = -np.inf
        size[i] += size[j]
        lab[lab == j] = i
    return lab


def find_recordings(units: list[dict], words: list[dict], embs: list, threshold: float) -> np.ndarray:
    """Boolean array over units: True = played recording."""
    n = len(units)
    flagged = np.zeros(n, bool)
    have = np.array([e is not None for e in embs])
    if have.sum() < 10:
        return flagged
    dim = next(len(e) for e in embs if e is not None)
    E = np.stack([e if e is not None else np.zeros(dim, np.float32) for e in embs]).astype(np.float64)
    mu = E[have].mean(0)
    Ec = E - mu
    Ec /= np.linalg.norm(Ec, axis=1, keepdims=True) + 1e-9
    Ec[~have] = 0.0
    by: dict[int, list[dict]] = {}
    for w in words:
        by.setdefault(w["unit"], []).append(w)
    dur = np.array([u["t1"] - u["t0"] for u in units])
    en = np.array([sum(w["t1"] - w["t0"] for w in by.get(i, []) if w["tag"] == "en") for i in range(n)])
    pl = np.array([sum(w["t1"] - w["t0"] for w in by.get(i, []) if w["tag"] == "pl") for i in range(n)])
    sim = np.array([u.get("sim", 0.0) for u in units])
    cand = np.where((dur >= MIN_UNIT_S) & have)[0]
    if len(cand) < 3:
        return flagged
    lab = _cluster_by_voice(Ec[cand], MIN_SIM)
    plu = np.where((pl > en) & (pl >= 1.0) & have)[0]
    tmask = (sim >= threshold) & have
    tcen = Ec[tmask].mean(0) if tmask.any() else np.zeros(Ec.shape[1])
    tcen /= np.linalg.norm(tcen) + 1e-9
    for c in np.unique(lab):
        idx = cand[lab == c]
        if len(idx) < 3 or dur[idx].sum() < 6:
            continue
        ws = [w for i in idx for w in by.get(i, [])]
        if not ws:
            continue
        if en[idx].sum() / max(en[idx].sum() + pl[idx].sum(), 1e-3) < EN_MIN:
            continue
        if np.mean([w["lp"] for w in ws]) < LP_MIN or np.mean([w["tag"] == "filler" for w in ws]) > FILLER_MAX:
            continue
        cen = Ec[idx].mean(0)
        cen /= np.linalg.norm(cen) + 1e-9
        if cen @ tcen >= TEACHER_COS_MAX:
            continue                                     # the teacher's own voice (e.g. a teacher who speaks only English)
        others = np.setdiff1d(plu, idx)
        s_pl = np.sort(Ec[others] @ cen) if len(others) else np.array([-1.0])
        pl3 = s_pl[-3] if len(s_pl) >= 3 else s_pl[-1]
        if pl3 >= PL_NEIGHBOUR_MAX:
            continue
        s = Ec @ cen
        flagged[idx] = True
        flagged[(s >= MIN_SIM + 0.1) & (en >= pl) & have] = True
    return flagged
