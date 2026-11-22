"""English or Polish? A tag for every word of the transcript.

Each word gets a score d = ln P(word | English) - ln P(word | Polish), from:
  - Polish letters (ą ć ę ł ń ó ś ź ż)             -> clearly Polish
  - how common the word is in each language        -> the main signal (wordfreq lists)
  - letter patterns, for words not in either list  -> a small letter-trigram model
Words that say nothing about the language (um/uh, names, "okay", "super"...) get d = 0.
A two-state Viterbi pass over each speech piece then picks EN or PL for every word, so words that exist in both
languages ("no", "to", "a", "i", "do") take the language of the sentence around them. Mixed sentences are fine:
the language can switch in the middle of a sentence when the evidence is strong enough.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

from wordfreq import top_n_list, zipf_frequency

PL_LETTERS = set("ąćęłńóśźż")
FILLERS = {
    "um", "umm", "uh", "uhm", "uhh", "mm", "mmm", "hmm", "hm", "mhm", "mm-hmm", "uh-huh", "ah", "ahh",
    "eh", "ee", "eee", "yy", "yyy", "ehm", "em", "er", "erm", "ha", "haha", "hahaha", "ooo", "oo", "ugh",
    "huh", "oh", "ooh", "aa", "aaa", "ach", "och",
}
# real words that carry no language evidence in a PL/EN classroom
ZERO_EVIDENCE = {"okay", "ok", "okej", "okey", "super", "wow", "aha", "hej", "hey", "bye", "pa", "halo", "hello"}
# zero-evidence words whose language is still clear when said on their own ("Okay." / "Okej.")
WEAK_LANG = {"okay": "en", "ok": "en", "hello": "en", "hey": "en", "bye": "en", "wow": "en", "yes": "en", "no": None,
             "okej": "pl", "okey": "pl", "hej": "pl", "pa": "pl", "halo": "pl", "tak": "pl", "nie": "pl"}
LN10 = math.log(10)
SWITCH = math.log(0.06)   # log prob of switching language between consecutive words
STAY = math.log(0.94)
DECISIVE = 1.5            # |d| needed for a word to count as real evidence
_WORD_RE = re.compile(r"[^\w'\-]+", re.UNICODE)


def norm(word: str) -> str:
    return _WORD_RE.sub("", word.lower()).strip("'-")


class _CharModel:
    """Character trigram log-likelihoods trained on each language's top words."""

    def __init__(self, n_words: int = 30000):
        self.models = {}
        for lang in ("en", "pl"):
            c = Counter()
            for w in top_n_list(lang, n_words):
                if not w.isalpha():
                    continue
                s = f"^^{w}$"
                for i in range(len(s) - 2):
                    c[s[i:i + 3]] += 1
            total = sum(c.values())
            self.models[lang] = (c, total, len(c) + 1)

    def loglik(self, w: str, lang: str) -> float:
        c, total, v = self.models[lang]
        s = f"^^{w}$"
        return sum(math.log((c.get(s[i:i + 3], 0) + 0.5) / (total + 0.5 * v)) for i in range(len(s) - 2))

    def d(self, w: str) -> float:
        return self.loglik(w, "en") - self.loglik(w, "pl")


_char_model: _CharModel | None = None


def _cm() -> _CharModel:
    global _char_model
    if _char_model is None:
        _char_model = _CharModel()
    return _char_model


@lru_cache(maxsize=200000)
def weak_lang(raw: str):
    """Language of a word said on its own, if it is clear without context; else None."""
    w = norm(raw)
    if w in WEAK_LANG:
        return WEAK_LANG[w]
    if not w or w in FILLERS or w in ZERO_EVIDENCE or any(ch.isdigit() for ch in w):
        return None
    if any(ch in PL_LETTERS for ch in w):
        return "pl"
    return None


def word_evidence(w: str) -> tuple[float, str]:
    """Return (d, kind). kind in {'filler','zero','pl_letters','lex','char','number'}."""
    if not w:
        return 0.0, "zero"
    if w in FILLERS:
        return 0.0, "filler"
    if any(ch.isdigit() for ch in w):
        return 0.0, "number"
    if w in ZERO_EVIDENCE:
        return 0.0, "zero"
    if any(ch in PL_LETTERS for ch in w):
        return -6.0, "pl_letters"
    fe, fp = zipf_frequency(w, "en"), zipf_frequency(w, "pl")
    cd = max(-4.0, min(4.0, _cm().d(w) * 0.5))
    if fe == 0 and fp == 0:
        return cd, "char"
    lex = ((fe or 0.8) - (fp or 0.8)) * LN10
    lex = max(-6.0, min(6.0, lex))
    if max(fe, fp) < 2.5:                      # rare in both: blend with spelling model
        return 0.5 * lex + 0.5 * cd, "lex"
    return lex, "lex"


def tag_utterance(words: list[str], sentence_start_flags: list[bool]) -> tuple[list[str], list[float]]:
    """Tag the words of one utterance. Returns (tags, evidence) with tags in
    {'en','pl','neutral','filler'}."""
    n = len(words)
    d = []
    kinds = []
    for raw, starts_sentence in zip(words, sentence_start_flags):
        w = norm(raw)
        dv, kind = word_evidence(w)
        # capitalised mid-sentence word that isn't very common -> proper name -> no evidence
        if (kind in ("lex", "char") and raw[:1].isupper() and not starts_sentence
                and max(zipf_frequency(w, "en"), zipf_frequency(w, "pl")) < 4.0):
            dv, kind = 0.0, "name"
        d.append(dv)
        kinds.append(kind)

    if not any(abs(x) >= DECISIVE for x in d):
        return ["filler" if k == "filler" else "neutral" for k in kinds], d

    # Viterbi over EN(0)/PL(1)
    score = [d[0] / 2, -d[0] / 2]
    back = []
    for i in range(1, n):
        e = (d[i] / 2, -d[i] / 2)
        new, bp = [], []
        for s in (0, 1):
            stay, sw = score[s] + STAY, score[1 - s] + SWITCH
            if stay >= sw:
                new.append(stay + e[s]); bp.append(s)
            else:
                new.append(sw + e[s]); bp.append(1 - s)
        score, back = new, back + [bp]
    state = 0 if score[0] >= score[1] else 1
    path = [state]
    for bp in reversed(back):
        state = bp[state]
        path.append(state)
    path.reverse()
    tags = []
    for k, s in zip(kinds, path):
        if k == "filler":
            tags.append("filler")
        elif k == "name":
            tags.append("neutral")          # names are not language use
        elif k == "number":                 # numbers count in the language spoken around them ("four" vs "cztery")
            tags.append("en" if s == 0 else "pl")
        else:
            tags.append("en" if s == 0 else "pl")
    return tags, d


UNCLEAR_LP = -2.3   # mean recogniser confidence (log-prob) below this: the word is "unclear", not counted


def tag_words(words: list[dict]) -> None:
    """Set w["tag"] for every word: en, pl, neutral (names, lone ambiguous words), filler (um/uh) or unclear.

    Words need text, seg (speech piece), unit (sentence) and lp (recogniser confidence)."""
    by_seg: dict[int, list[dict]] = {}
    for w in words:
        by_seg.setdefault(w["seg"], []).append(w)
    for ws in by_seg.values():
        texts = [w["text"] for w in ws]
        starts = [i == 0 or texts[i - 1][-1:] in ".?!" for i in range(len(texts))]
        tags, d = tag_utterance(texts, starts)
        for w, tag, dv in zip(ws, tags, d):
            w["tag"], w["d"] = tag, dv
    by_unit: dict[int, list[dict]] = {}
    for w in words:
        by_unit.setdefault(w["unit"], []).append(w)
    for ws in by_unit.values():
        # A sentence with no clearly-English or clearly-Polish word ("Okay.", "No.") only keeps words whose
        # language is obvious on their own.
        if not any(abs(w["d"]) >= DECISIVE for w in ws):
            for w in ws:
                if w["tag"] in ("en", "pl", "neutral"):
                    w["tag"] = weak_lang(w["text"]) or "neutral"
        for w in ws:
            if w["tag"] in ("en", "pl") and w["lp"] < UNCLEAR_LP:
                w["tag"] = "unclear"
    for w in words:
        del w["d"]
