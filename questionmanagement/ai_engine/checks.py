"""Deterministic (non-AI) checks and clean-up for a single question.

These rules are enforced in code because an AI review can pass a structurally
broken question. ``clean_question`` returns the app's standard shape:

    {"type", "question", "options"(multiple_choice only), "correct_answer",
     "explanation", "points"}

plus, during generation only, "acceptable_answers" and "fact" (kept in the AI
batch for review, dropped when saved to the bank).
"""
from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional, Tuple

from questionmanagement.ai_engine.textnorm import normalize

POINT_LEVELS = (100, 200, 300, 400, 500)
TYPES = ("multiple_choice", "true_false", "text")

_TYPE_ALIASES = {
    "mcq": "multiple_choice", "multiple choice": "multiple_choice", "multiple-choice": "multiple_choice",
    "multiple_choice": "multiple_choice", "choice": "multiple_choice",
    "true false": "true_false", "true/false": "true_false", "true-false": "true_false",
    "true_false": "true_false", "boolean": "true_false", "tf": "true_false",
    "short_answer": "text", "short answer": "text", "short": "text", "open": "text",
    "open_ended": "text", "fill_in_the_blank": "text", "text": "text",
}
_TRUE = {"true", "صح", "صحيح", "نعم", "yes"}
_FALSE = {"false", "خطا", "خطأ", "غير صحيح", "لا", "no"}
_BANNED_OPTIONS = {"all of the above", "none of the above", "جميع ما سبق", "كل ما سبق", "لا شيء مما سبق",
                   "جميع الاجابات صحيحه", "لا شيء مما ذكر"}
_SOURCE_LEAK = re.compile(r"\b(according to the (text|passage|source|facts?)|provided facts?|the passage)\b|"
                          r"(وفقا للنص|حسب النص|المصدر المقدم|الحقائق المقدمه)", re.IGNORECASE)


def normalize_type(value: Any) -> str:
    return _TYPE_ALIASES.get(str(value or "").strip().lower(), "text")


def snap_points(value: Any, default: int = 300) -> int:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return min(POINT_LEVELS, key=lambda p: abs(p - n))


def _str(v: Any) -> str:
    return " ".join(str(v if v is not None else "").split())


def clean_question(raw: Dict[str, Any], keep_ai_fields: bool = True) -> Dict[str, Any]:
    qtype = normalize_type(raw.get("type"))
    q: Dict[str, Any] = {
        "type": qtype,
        "question": _str(raw.get("question")),
        "correct_answer": _str(raw.get("correct_answer")),
        "explanation": _str(raw.get("explanation")),
        "points": snap_points(raw.get("points")),
    }
    if qtype == "multiple_choice":
        q["options"] = [_str(o) for o in (raw.get("options") or []) if _str(o)]
        # Snap the answer to the exact option text when only spacing/case differs.
        na = normalize(q["correct_answer"])
        for opt in q["options"]:
            if normalize(opt) == na:
                q["correct_answer"] = opt
                break
    elif qtype == "true_false":
        a = normalize(q["correct_answer"])
        if a in {normalize(x) for x in _TRUE}:
            q["correct_answer"] = "True"
        elif a in {normalize(x) for x in _FALSE}:
            q["correct_answer"] = "False"
    if keep_ai_fields:
        alts = raw.get("acceptable_answers") or []
        if isinstance(alts, list):
            q["acceptable_answers"] = [_str(a) for a in alts if _str(a)][:6]
        if raw.get("fact"):
            q["fact"] = _str(raw.get("fact"))
    return q


def check_question(q: Dict[str, Any]) -> List[str]:
    """Return a list of problems (empty = structurally valid)."""
    issues: List[str] = []
    if len(q.get("question", "")) < 8:
        issues.append("question text is missing or too short")
    if not q.get("correct_answer"):
        issues.append("correct answer is missing")
    if q.get("points") not in POINT_LEVELS:
        issues.append("points must be 100-500")
    if _SOURCE_LEAK.search(normalize(q.get("question", ""))) or _SOURCE_LEAK.search(q.get("question", "")):
        issues.append("question refers to a source/passage")
    qtype = q.get("type")
    if qtype == "multiple_choice":
        opts = q.get("options") or []
        norm = [normalize(o) for o in opts]
        if len(opts) != 4:
            issues.append("multiple choice needs exactly 4 options")
        if len(set(norm)) != len(norm):
            issues.append("options repeat")
        if normalize(q.get("correct_answer", "")) not in norm:
            issues.append("correct answer is not one of the options")
        if any(n in {normalize(b) for b in _BANNED_OPTIONS} for n in norm):
            issues.append("uses 'all/none of the above'")
    elif qtype == "true_false":
        if q.get("correct_answer") not in ("True", "False"):
            issues.append("true/false answer must be True or False")
    elif qtype == "text":
        if len(q.get("correct_answer", "").split()) > 8:
            issues.append("text answer is too long to judge")
    else:
        issues.append("unknown question type")
    # The answer should not be given away in the question.
    ans = normalize(q.get("correct_answer", ""))
    if qtype != "true_false" and len(ans) >= 4 and ans in normalize(q.get("question", "")):
        issues.append("question gives away the answer")
    return issues


def shuffle_options(q: Dict[str, Any], rng: Optional[random.Random] = None) -> None:
    """Randomize the correct option's position (models favour position A/B)."""
    if q.get("type") == "multiple_choice" and isinstance(q.get("options"), list):
        (rng or random).shuffle(q["options"])


def to_bank_shape(q: Dict[str, Any]) -> Dict[str, Any]:
    """Strip AI-only fields so the question matches the bank's format."""
    out = {k: q[k] for k in ("type", "question", "correct_answer", "explanation", "points") if k in q}
    if q.get("type") == "multiple_choice":
        out["options"] = list(q.get("options") or [])
    return out


def check_all(questions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    ok, bad = [], []
    for q in questions:
        problems = check_question(q)
        (bad if problems else ok).append({"question": q, "issues": problems} if problems else q)
    return ok, bad
