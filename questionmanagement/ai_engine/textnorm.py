"""Arabic/English text normalization and near-duplicate detection.

Duplicate detection runs automatically against the whole question bank (and
recent AI batches), so admins no longer pick "reference categories" by hand.

Two questions are treated as duplicates when either:
- their wording is nearly the same (paraphrase), or
- they have the same non-trivial answer and clearly overlapping wording
  (the same fact asked a different way).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Set, Tuple

_AR_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_AR_MAP = str.maketrans({
    "إ": "ا", "أ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
})

# Stopwords are listed in their *normalized* form.
_STOP = set("""
a an the of in on at to for from by with and or is are was were be been being which what who whom whose
when where why how this that these those it its as into than then there their they he she his her
do does did has have had not no yes true false which's name named called following
من في على الي الى عن ما ماذا هو هي هل اي التي الذي الذين كم متي اين كيف لماذا مع او و ان كان كانت
هذا هذه ذلك تلك يوجد تم قد لم لا ثم بين عند كل اول اسم يسمي تسمي يعرف تعرف اكثر اقل احد احدي
""".split())

_TRIVIAL_ANSWERS = {"true", "false", "yes", "no", "صح", "خطا", "صحيح", "نعم", "لا"}


def normalize(text: str) -> str:
    """Lowercase, strip Arabic diacritics/tatweel, unify letter variants and digits,
    drop punctuation and collapse whitespace."""
    s = unicodedata.normalize("NFKC", str(text or ""))
    s = _AR_DIACRITICS.sub("", s).translate(_AR_MAP).lower()
    s = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s)
    return " ".join(s.split())


def _stem(token: str) -> str:
    # Light Arabic stemming: drop the definite article and common one-letter
    # prefixes so "والقاهرة" / "القاهرة" / "قاهرة" match.
    for prefix in ("وال", "بال", "كال", "فال", "لل", "ال"):
        if token.startswith(prefix) and len(token) - len(prefix) >= 2:
            return token[len(prefix):]
    return token


def tokens(text: str) -> Set[str]:
    return {_stem(t) for t in normalize(text).split() if t not in _STOP and len(t) > 1}


def trigrams(text: str) -> Set[str]:
    s = normalize(text).replace(" ", "")
    return {s[i:i + 3] for i in range(max(0, len(s) - 2))}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _dice(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def answer_key(answer: str) -> str:
    a = normalize(answer)
    a = " ".join(_stem(t) for t in a.split())
    if a in _TRIVIAL_ANSWERS or a.replace(" ", "").replace(".", "").isdigit():
        return ""  # True/False and bare numbers coincide too often to mean "same fact"
    return a


def answers_match(given: str, expected: str, alternatives: Iterable[str] = ()) -> bool:
    """Lenient-but-safe answer comparison used by the blind check."""
    g = answer_key(given) or normalize(given)
    if not g:
        return False
    for cand in [expected, *list(alternatives or [])]:
        c = answer_key(cand) or normalize(cand)
        if not c:
            continue
        if g == c:
            return True
        gt, ct = set(g.split()), set(c.split())
        # Multi-word names: "Ibn Battuta" vs "Muhammad Ibn Battuta".
        if gt and ct and min(len(gt), len(ct)) >= 1 and (gt <= ct or ct <= gt) and len(gt & ct) >= max(1, min(len(gt), len(ct))):
            if max(len(gt), len(ct)) - min(len(gt), len(ct)) <= 2:
                return True
    return False


class _Entry:
    __slots__ = ("ref", "text", "answer", "tok", "tri")

    def __init__(self, ref: Dict, text: str, answer: str):
        self.ref = ref
        self.text = text
        self.answer = answer_key(answer)
        self.tok = tokens(text)
        self.tri = trigrams(text)


class DedupIndex:
    """In-memory index of known questions for fast near-duplicate lookup."""

    WORDING_THRESHOLD = 0.78   # paraphrase of the same question
    SAME_ANSWER_THRESHOLD = 0.50  # same answer + overlapping wording = same fact

    def __init__(self):
        self._entries: List[_Entry] = []
        self._by_token: Dict[str, List[int]] = {}
        self._by_answer: Dict[str, List[int]] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def add(self, question: Dict, ref: Optional[Dict] = None) -> None:
        text = str(question.get("question") or "")
        if not text.strip():
            return
        entry = _Entry(ref or {"id": question.get("id"), "category_id": question.get("category_id"),
                               "question": text, "correct_answer": question.get("correct_answer")},
                       text, str(question.get("correct_answer") or ""))
        idx = len(self._entries)
        self._entries.append(entry)
        for t in entry.tok:
            self._by_token.setdefault(t, []).append(idx)
        if entry.answer:
            self._by_answer.setdefault(entry.answer, []).append(idx)

    def similarity(self, a: _Entry, b: _Entry) -> float:
        return 0.5 * _jaccard(a.tok, b.tok) + 0.5 * _dice(a.tri, b.tri)

    def find_duplicate(self, question: Dict, exclude_id: Optional[str] = None) -> Optional[Tuple[Dict, float, str]]:
        """Return (matched_ref, score, reason) for the closest duplicate, else None."""
        probe = _Entry({}, str(question.get("question") or ""), str(question.get("correct_answer") or ""))
        if not probe.tok and not probe.tri:
            return None
        candidates: Set[int] = set()
        for t in probe.tok:
            posting = self._by_token.get(t)
            if posting and len(posting) < 400:  # skip ubiquitous tokens
                candidates.update(posting)
        if probe.answer:
            candidates.update(self._by_answer.get(probe.answer, []))
        best: Optional[Tuple[Dict, float, str]] = None
        for idx in candidates:
            entry = self._entries[idx]
            if exclude_id and entry.ref.get("id") == exclude_id:
                continue
            score = self.similarity(probe, entry)
            reason = ""
            if score >= self.WORDING_THRESHOLD:
                reason = "same wording"
            elif probe.answer and probe.answer == entry.answer and score >= self.SAME_ANSWER_THRESHOLD:
                reason = "same fact and answer"
            if reason and (best is None or score > best[1]):
                best = (entry.ref, round(score, 2), reason)
        return best

    def related(self, text: str, limit: int = 40) -> List[Dict]:
        """Existing questions most related to ``text`` (used to steer the AI away up front)."""
        probe_tok = tokens(text)
        probe_tri = trigrams(text)
        scores: Dict[int, float] = {}
        for t in probe_tok:
            for idx in self._by_token.get(t, [])[:2000]:
                scores[idx] = scores.get(idx, 0.0) + 1.0
        ranked = sorted(scores, key=lambda i: (-scores[i], -_dice(probe_tri, self._entries[i].tri)))
        return [self._entries[i].ref for i in ranked[:limit]]

    def entries_for_category(self, category_id: str, limit: int = 60) -> List[Dict]:
        out = [e.ref for e in self._entries if e.ref.get("category_id") == category_id]
        return out[:limit]
