"""Blind solving and fact-checking shared by the generator and the validator."""
from __future__ import annotations

from typing import Any, Dict, List

from questionmanagement.ai_engine import prompts
from questionmanagement.ai_engine.client import AIError, LLMClient
from questionmanagement.ai_engine.textnorm import answers_match

SOLVE_CHUNK = 10
CHECK_CHUNK = 6


def _chunks(items: List[Any], size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def blind_solve(client: LLMClient, questions: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Answer each question without its key. ``questions``: {id: question}. Best-effort per chunk."""
    results: Dict[str, Dict[str, Any]] = {}
    items = [{"id": qid, "type": q.get("type"), "question": q.get("question"),
              "options": q.get("options") if q.get("type") == "multiple_choice" else []}
             for qid, q in questions.items()]
    last_error = None
    ok_chunks = 0
    for chunk in _chunks(items, SOLVE_CHUNK):
        try:
            data, _ = client.complete_json(prompts.SOLVE_SYSTEM, prompts.solve_prompt(chunk),
                                           role="verify", list_key="answers")
            ok_chunks += 1
        except AIError as exc:
            last_error = exc
            continue
        for a in (data or {}).get("answers", []) if isinstance(data, dict) else []:
            if isinstance(a, dict) and str(a.get("id")) in questions:
                results[str(a.get("id"))] = {
                    "answer": str(a.get("answer") or ""),
                    "confidence": str(a.get("confidence") or "low").lower(),
                    "ambiguous": bool(a.get("ambiguous")),
                    "note": str(a.get("note") or "")[:300],
                }
    if items and not ok_chunks and last_error:
        raise last_error
    return results


def agrees(question: Dict[str, Any], solved: Dict[str, Any]) -> bool:
    """True when the blind answer matches the key confidently and unambiguously."""
    if not solved or solved.get("ambiguous") or solved.get("confidence") == "low":
        return False
    return answers_match(solved.get("answer", ""), question.get("correct_answer", ""),
                         question.get("acceptable_answers") or [])


def fact_check(client: LLMClient, items: Dict[str, Dict[str, Any]], solved: Dict[str, Dict[str, Any]],
               language: str) -> Dict[str, Dict[str, Any]]:
    """Judge each item. Returns {id: {"verdict", "issues", "question"}}; missing ids = not reviewed."""
    payload = []
    for qid, q in items.items():
        s = solved.get(qid) or {}
        payload.append({
            "id": qid, "type": q.get("type"), "question": q.get("question"),
            "options": q.get("options") if q.get("type") == "multiple_choice" else [],
            "proposed_answer": q.get("correct_answer"), "explanation": q.get("explanation", ""),
            "points": q.get("points"), "writer_fact": q.get("fact", ""),
            "contestant_answer": s.get("answer", "(no answer)"),
            "contestant_confidence": s.get("confidence", ""),
            "contestant_note": s.get("note", ""),
        })
    reviews: Dict[str, Dict[str, Any]] = {}
    last_error = None
    ok_chunks = 0
    for chunk in _chunks(payload, CHECK_CHUNK):
        try:
            data, _ = client.complete_json(prompts.CHECK_SYSTEM, prompts.check_prompt(chunk, language),
                                           role="verify", list_key="reviews")
            ok_chunks += 1
        except AIError as exc:
            last_error = exc
            continue
        for r in (data or {}).get("reviews", []) if isinstance(data, dict) else []:
            if isinstance(r, dict) and str(r.get("id")) in items:
                verdict = str(r.get("verdict") or "").lower()
                reviews[str(r.get("id"))] = {
                    "verdict": verdict if verdict in ("correct", "fixed", "reject") else "reject",
                    "issues": [str(i)[:200] for i in (r.get("issues") or []) if i][:4],
                    "question": r.get("question") if isinstance(r.get("question"), dict) else None,
                }
    if payload and not ok_chunks and last_error:
        raise last_error
    return reviews
