"""Question generation pipeline.

For each round:
  1. ask the model for a few more questions than still needed, steering it away
     from questions already in the bank on this topic;
  2. clean + structure-check each question in code;
  3. drop near-duplicates of anything in the bank, recent AI batches or this run;
  4. (verify on) blind-solve every question, accept confident matches, send the
     rest to a fact-check that keeps, fixes or rejects them.
Rounds repeat until the requested count is reached or progress stalls.
"""
from __future__ import annotations

import math
import random
import uuid
from datetime import datetime
from typing import Any, Dict, List

from questionmanagement.ai_engine import checks, prompts, verify
from questionmanagement.ai_engine.batches import recent_questions, save_batch
from questionmanagement.ai_engine.client import AIError, LLMClient
from questionmanagement.ai_engine.service import jobs
from questionmanagement.ai_engine.sources import wikipedia_notes
from questionmanagement.ai_engine.textnorm import DedupIndex

DIFFICULTY_POINTS = {"easiest": 100, "easy": 200, "medium": 300, "hard": 400, "hardest": 500}


def build_bank_index(bank_questions: List[Dict[str, Any]], include_recent_batches: bool = True) -> DedupIndex:
    index = DedupIndex()
    for q in bank_questions:
        index.add(q)
    if include_recent_batches:
        for q in recent_questions():
            index.add(q, ref={"id": None, "category_id": "(recent AI batch)",
                              "question": q.get("question"), "correct_answer": q.get("correct_answer")})
    return index


def target_distribution(count: int, difficulty: str) -> Dict[int, int]:
    if difficulty in DIFFICULTY_POINTS:
        return {DIFFICULTY_POINTS[difficulty]: count}
    base, extra = divmod(count, 5)
    return {p: base + (1 if i < extra else 0) for i, p in enumerate(checks.POINT_LEVELS)}


def _round_distribution(target: Dict[int, int], accepted: List[Dict], ask: int) -> Dict[int, int]:
    have: Dict[int, int] = {}
    for q in accepted:
        have[q["points"]] = have.get(q["points"], 0) + 1
    missing = {p: max(0, n - have.get(p, 0)) for p, n in target.items()}
    total = sum(missing.values()) or 1
    dist = {p: math.floor(ask * n / total) for p, n in missing.items()}
    # Hand out the remainder to the most-missing levels.
    for p in sorted(missing, key=lambda p: -missing[p]):
        if sum(dist.values()) >= ask:
            break
        if missing[p]:
            dist[p] += 1
    return {p: n for p, n in dist.items() if n}


def generate(job_id: str, client: LLMClient, runtime: Dict[str, Any], request: Dict[str, Any],
             bank_questions: List[Dict[str, Any]]) -> None:
    topic = request["topic"].strip()
    focus = (request.get("focus") or "").strip()
    count = max(1, min(50, int(request.get("count") or 10)))
    types = [t for t in (request.get("types") or []) if t in checks.TYPES] or list(checks.TYPES)
    difficulty = request.get("difficulty") or "mixed"
    language = request.get("language") or "arabic"
    explanations = bool(request.get("explanations", True))
    do_verify = bool(request.get("verify", True))
    use_sources = bool(request.get("use_sources", runtime.get("use_sources", True)))
    category = (request.get("category") or "").strip()
    profile = runtime["profile"]
    chunk = int(profile["chunk"])

    def progress(percent: int, stage: str, **extra):
        jobs.update(job_id, percent=max(0, min(100, int(percent))), stage=stage, **extra)

    progress(4, "Loading the question bank to avoid repeats…")
    index = build_bank_index(bank_questions)
    avoid_refs = index.related(f"{topic} {focus} {category}", limit=50)
    if category:
        avoid_refs = index.entries_for_category(category, 30) + avoid_refs
    seen, avoid = set(), []
    for r in avoid_refs:
        text = r.get("question") or ""
        if text and text not in seen:
            seen.add(text)
            avoid.append(f"{text} → {r.get('correct_answer', '')}")

    notes = {"sources": [], "facts": []}
    if use_sources:
        progress(8, "Reading Wikipedia reference notes…")
        notes = wikipedia_notes(topic, language)

    target = target_distribution(count, difficulty)
    accepted: List[Dict[str, Any]] = []
    run_index = DedupIndex()
    stats = {"written": 0, "structure": 0, "duplicate": 0, "wrong_type": 0, "low_confidence": 0,
             "fact_check_rejected": 0, "verified": 0, "corrected": 0, "unverified": 0, "calls_failed": 0}
    dropped: List[Dict[str, Any]] = []
    rng = random.Random()
    max_rounds = math.ceil(count / chunk) * 3 + 2
    stalled = 0
    rounds = 0

    def drop(q: Dict, reason: str):
        if len(dropped) < 60:
            dropped.append({"question": q.get("question", ""), "answer": q.get("correct_answer", ""), "reason": reason})

    while len(accepted) < count and rounds < max_rounds and stalled < 3:
        rounds += 1
        need = count - len(accepted)
        ask = min(chunk, need + max(1, need // 3))
        dist = _round_distribution(target, accepted, ask) or {300: ask}
        ask = sum(dist.values())
        done_frac = len(accepted) / count
        progress(12 + 80 * done_frac, f"Writing {ask} questions (round {rounds})…",
                 generated=len(accepted), target=count)

        recent = [f"{q['question']} → {q['correct_answer']}" for q in accepted]
        prompt = prompts.generation_prompt(
            topic=topic, focus=focus, count=ask, types=types, distribution=dist, language=language,
            explanations=explanations, avoid=recent + avoid, facts=notes["facts"], category=category)
        try:
            data, _info = client.complete_json(prompts.GENERATE_SYSTEM, prompt, role="generate",
                                               list_key="questions")
        except AIError as exc:
            stats["calls_failed"] += 1
            if stats["calls_failed"] >= 3 or not accepted and stats["calls_failed"] >= 2:
                raise
            jobs.update(job_id, warning=str(exc))
            stalled += 1
            continue
        raw_list = data.get("questions") if isinstance(data, dict) else data if isinstance(data, list) else []
        candidates: Dict[str, Dict[str, Any]] = {}
        for raw in raw_list or []:
            if not isinstance(raw, dict):
                continue
            stats["written"] += 1
            q = checks.clean_question(raw)
            if q["type"] not in types:
                stats["wrong_type"] += 1
                drop(q, "type not requested")
                continue
            if difficulty in DIFFICULTY_POINTS:
                q["points"] = DIFFICULTY_POINTS[difficulty]
            if str(raw.get("confidence", "high")).lower() not in ("high", "medium"):
                stats["low_confidence"] += 1
                drop(q, "writer was not confident")
                continue
            problems = checks.check_question(q)
            if problems:
                stats["structure"] += 1
                drop(q, "; ".join(problems))
                continue
            dup = index.find_duplicate(q) or run_index.find_duplicate(q)
            if dup:
                stats["duplicate"] += 1
                drop(q, f"duplicate of: {dup[0].get('question', '')[:80]} ({dup[2]})")
                continue
            run_index.add(q)  # also blocks repeats inside this round
            candidates[uuid.uuid4().hex[:8]] = q

        newly: List[Dict[str, Any]] = []
        if candidates and do_verify:
            progress(12 + 80 * done_frac, f"Fact-checking {len(candidates)} questions (blind answer)…")
            try:
                solved = verify.blind_solve(client, candidates)
            except AIError as exc:
                stats["calls_failed"] += 1
                if stats["calls_failed"] >= 3:
                    raise
                jobs.update(job_id, warning=str(exc))
                stalled += 1
                continue
            to_judge = {}
            for qid, q in candidates.items():
                if verify.agrees(q, solved.get(qid)):
                    q["verification"] = "verified"
                    newly.append(q)
                elif profile.get("judge"):
                    to_judge[qid] = q
                else:
                    stats["fact_check_rejected"] += 1
                    drop(q, "independent answer disagreed: " + (solved.get(qid) or {}).get("answer", "no answer"))
            if to_judge:
                progress(12 + 80 * done_frac, f"Reviewing {len(to_judge)} disputed questions…")
                try:
                    reviews = verify.fact_check(client, to_judge, solved, language)
                except AIError as exc:
                    stats["calls_failed"] += 1
                    if stats["calls_failed"] >= 3:
                        raise
                    jobs.update(job_id, warning=str(exc))
                    reviews = {}
                for qid, q in to_judge.items():
                    r = reviews.get(qid)
                    if not r or r["verdict"] == "reject":
                        stats["fact_check_rejected"] += 1
                        drop(q, "fact-check: " + ("; ".join(r["issues"]) if r and r["issues"] else "could not verify"))
                        continue
                    if r["verdict"] == "fixed" and r["question"]:
                        fixed = checks.clean_question({**q, **r["question"]})
                        if difficulty in DIFFICULTY_POINTS:
                            fixed["points"] = DIFFICULTY_POINTS[difficulty]
                        if checks.check_question(fixed) or fixed["type"] not in types or index.find_duplicate(fixed):
                            stats["fact_check_rejected"] += 1
                            drop(q, "fact-check fix was not usable")
                            continue
                        fixed["verification"] = "corrected"
                        fixed["review_note"] = "; ".join(r["issues"])[:300]
                        newly.append(fixed)
                    else:
                        q["verification"] = "verified"
                        newly.append(q)
        else:
            for q in candidates.values():
                q["verification"] = "unverified"
                newly.append(q)

        added = 0
        for q in newly:
            if len(accepted) >= count:
                break
            checks.shuffle_options(q, rng)
            accepted.append(q)
            stats[q["verification"]] = stats.get(q["verification"], 0) + 1
            added += 1
        stalled = 0 if added else stalled + 1

    if not accepted:
        raise AIError("No question passed the checks. Try a broader topic, another model, or turn off "
                      "Wikipedia notes if the topic is very specific.")

    batch_id = str(uuid.uuid4())
    metadata = {
        "timestamp": datetime.now().isoformat(),
        "prompt": f"{topic}. {focus}".strip(". ") if focus else topic,
        "topic": topic,
        "focus": focus,
        "category": category,
        "question_type": ",".join(types),
        "difficulty": difficulty,
        "language": language,
        "include_explanations": explanations,
        "num_requested": count,
        "num_returned": len(accepted),
        "ai_option": runtime["option_id"],
        "model": runtime["model"],
        "quality": runtime["quality"],
        "verified": do_verify,
        "sources": notes["sources"],
        "generation_version": "v5_ai_engine",
        "stats": stats,
        "dropped": dropped,
    }
    save_batch(batch_id, accepted, metadata)
    jobs.update(job_id, status="done", percent=100, stage="Done", batch_id=batch_id,
                generated=len(accepted), target=count, stats=stats)
