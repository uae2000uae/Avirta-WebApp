"""Question-bank validator.

Reviews existing questions (by category, or from an uploaded JSON file):
  - duplicates are found in code against the whole bank (no AI needed);
  - optionally an independent blind answer is collected as evidence;
  - the AI reviewer returns ok / improve / fix / remove with a proposed version;
  - proposals are structure-checked in code before they are offered.
Nothing changes in the bank until the admin approves individual results.
Results are stored on disk (contents/question_validations/<job>.json), not in
the session cookie.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from questionmanagement.ai_engine import checks, prompts, verify
from questionmanagement.ai_engine.client import AIError, LLMClient
from questionmanagement.ai_engine.service import jobs
from questionmanagement.ai_engine.textnorm import DedupIndex

RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "contents", "question_validations")
os.makedirs(RESULTS_DIR, exist_ok=True)

REVIEW_CHUNK = 8


def _results_path(job_id: str) -> str:
    safe = "".join(ch for ch in job_id if ch.isalnum())
    return os.path.join(RESULTS_DIR, f"review_{safe}.json")


def load_results(job_id: str) -> Optional[Dict[str, Any]]:
    path = _results_path(job_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _save_results(job_id: str, data: Dict[str, Any]) -> None:
    with open(_results_path(job_id), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)


def _language_of(questions: List[Dict]) -> str:
    sample = " ".join(str(q.get("question", "")) for q in questions[:10])
    arabic = sum(1 for ch in sample if "؀" <= ch <= "ۿ")
    return "arabic" if arabic > len(sample) * 0.2 else "english"


def review(job_id: str, client: LLMClient, runtime: Dict[str, Any], *, groups: Dict[str, List[Dict]],
           bank_questions: List[Dict], options: Dict[str, Any], source: str) -> None:
    """``groups``: {category_id: [questions with "id"]}. Writes results and finishes the job."""
    improve_wording = bool(options.get("improve_wording", True))
    add_explanations = bool(options.get("add_explanations", True))
    rescore_points = bool(options.get("rescore_points", False))
    blind = bool(options.get("blind_check", True))
    check_dups = bool(options.get("check_duplicates", True))

    total = sum(len(v) for v in groups.values()) or 1
    done = 0
    results: List[Dict[str, Any]] = []

    index = DedupIndex()
    if check_dups:
        for q in bank_questions:
            index.add(q)

    for category_id, questions in groups.items():
        language = _language_of(questions)
        for start in range(0, len(questions), REVIEW_CHUNK):
            chunk = questions[start:start + REVIEW_CHUNK]
            jobs.update(job_id, percent=int(100 * done / total),
                        stage=f"Reviewing {category_id}: questions {start + 1}-{start + len(chunk)} of {len(questions)}")
            by_id = {str(q.get("id") or f"row{start + i}"): q for i, q in enumerate(chunk)}
            solved: Dict[str, Dict] = {}
            if blind:
                try:
                    solved = verify.blind_solve(client, {qid: checks.clean_question(q) for qid, q in by_id.items()})
                except AIError as exc:
                    jobs.update(job_id, warning=f"Blind check skipped for one batch: {exc}")
            items = []
            for qid, q in by_id.items():
                item = {"id": qid, **checks.to_bank_shape(checks.clean_question(q, keep_ai_fields=False))}
                s = solved.get(qid)
                if s:
                    item["contestant_answer"] = s.get("answer")
                    item["contestant_confidence"] = s.get("confidence")
                    if s.get("ambiguous"):
                        item["contestant_note"] = "flagged as ambiguous: " + s.get("note", "")
                items.append(item)
            reviews: Dict[str, Dict] = {}
            try:
                data, _ = client.complete_json(
                    prompts.REVIEW_SYSTEM,
                    prompts.review_prompt(items, language=language, category=category_id,
                                          improve_wording=improve_wording, add_explanations=add_explanations,
                                          rescore_points=rescore_points),
                    role="verify", list_key="reviews")
                for r in (data or {}).get("reviews", []) if isinstance(data, dict) else []:
                    if isinstance(r, dict) and str(r.get("id")) in by_id:
                        reviews[str(r["id"])] = r
            except AIError as exc:
                if not results and start == 0:
                    raise
                jobs.update(job_id, warning=f"One batch could not be reviewed: {exc}")

            for qid, original in by_id.items():
                orig_clean = checks.clean_question(original, keep_ai_fields=False)
                r = reviews.get(qid)
                entry: Dict[str, Any] = {
                    "id": qid,
                    "category_id": category_id,
                    "original": checks.to_bank_shape(orig_clean),
                    "verdict": "not_reviewed",
                    "issues": [],
                    "proposed": None,
                    "contestant": solved.get(qid),
                    "duplicate_of": None,
                }
                if source == "upload":
                    entry["raw"] = original  # keep every original field for the corrected download
                if r:
                    verdict = str(r.get("verdict") or "").lower()
                    entry["verdict"] = verdict if verdict in ("ok", "improve", "fix", "remove") else "not_reviewed"
                    entry["issues"] = [str(i)[:200] for i in (r.get("issues") or []) if i][:5]
                    if entry["verdict"] in ("improve", "fix") and isinstance(r.get("question"), dict):
                        proposed = checks.clean_question({**orig_clean, **r["question"]}, keep_ai_fields=False)
                        if not rescore_points:
                            proposed["points"] = orig_clean["points"]
                        problems = checks.check_question(proposed)
                        if problems:
                            entry["issues"].append("AI proposal failed checks: " + "; ".join(problems))
                            entry["verdict"] = "attention"
                        elif checks.to_bank_shape(proposed) == entry["original"]:
                            entry["verdict"] = "ok"
                        else:
                            entry["proposed"] = checks.to_bank_shape(proposed)
                # Code-level structure problems in the original are always reported.
                own_problems = checks.check_question(orig_clean)
                if own_problems and entry["verdict"] == "ok":
                    entry["verdict"] = "attention"
                if own_problems:
                    entry["issues"] = ["Structure: " + "; ".join(own_problems)] + entry["issues"]
                if check_dups:
                    dup = index.find_duplicate(original, exclude_id=original.get("id"))
                    if dup:
                        entry["duplicate_of"] = {"id": dup[0].get("id"), "category_id": dup[0].get("category_id"),
                                                 "question": dup[0].get("question"), "score": dup[1],
                                                 "reason": dup[2]}
                results.append(entry)
            done += len(chunk)

    summary: Dict[str, int] = {}
    for e in results:
        summary[e["verdict"]] = summary.get(e["verdict"], 0) + 1
    summary["duplicates"] = sum(1 for e in results if e["duplicate_of"])
    data = {
        "job_id": job_id,
        "created": datetime.now().isoformat(),
        "source": source,
        "ai_option": runtime["option_id"],
        "model": runtime["model"],
        "options": options,
        "summary": summary,
        "results": results,
    }
    _save_results(job_id, data)
    jobs.update(job_id, status="done", percent=100, stage="Done", summary=summary)


def apply_changes(job_id: str, decisions: List[Dict[str, str]], question_bank, now: Optional[str] = None) -> Dict[str, int]:
    """Apply approved decisions to bank questions.

    ``decisions``: [{"id": ..., "action": "update" | "delete"}]. Returns counts.
    Only results with a stored proposal can be updated; delete removes the
    question from its category file.
    """
    data = load_results(job_id)
    if not data or data.get("source") != "bank":
        raise ValueError("These results cannot be applied to the bank.")
    by_id = {e["id"]: e for e in data["results"]}
    now = now or datetime.now().isoformat(timespec="seconds")
    question_bank.load_questions()
    updated = deleted = skipped = 0
    touched_categories = set()
    for d in decisions:
        entry = by_id.get(str(d.get("id")))
        current = question_bank.questions.get(str(d.get("id")))
        if not entry or not current:
            skipped += 1
            continue
        if d.get("action") == "update" and entry.get("proposed"):
            new_q = dict(current)
            new_q.update(entry["proposed"])
            if new_q.get("type") != "multiple_choice":
                new_q.pop("options", None)
            new_q["updated_at"] = now
            question_bank._save_question(new_q["id"], new_q)  # noqa: SLF001 - bank's own writer
            entry["applied"] = "updated"
            updated += 1
            touched_categories.add(new_q.get("category_id"))
        elif d.get("action") == "delete":
            if _delete_from_file(question_bank.storage_path, current.get("category_id"), current["id"]):
                entry["applied"] = "deleted"
                deleted += 1
                touched_categories.add(current.get("category_id"))
            else:
                skipped += 1
        else:
            skipped += 1
    _save_results(job_id, data)
    question_bank.load_questions()
    return {"updated": updated, "deleted": deleted, "skipped": skipped,
            "categories": sorted(c for c in touched_categories if c)}


def _delete_from_file(storage_path: str, category_id: str, question_id: str) -> bool:
    path = os.path.join(storage_path, f"{category_id}.json")
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as fh:
        items = json.load(fh)
    kept = [q for q in items if q.get("id") != question_id]
    if len(kept) == len(items):
        return False
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(kept, fh, indent=2, ensure_ascii=False)
    return True


def corrected_file(job_id: str, decisions: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """For uploaded files: return the file's questions with approved changes applied."""
    data = load_results(job_id)
    if not data:
        raise ValueError("Results not found.")
    wanted = {str(d.get("id")): d.get("action") for d in decisions}
    out = []
    for e in data["results"]:
        action = wanted.get(e["id"])
        if action == "delete":
            continue
        q = dict(e.get("raw") or e["original"])
        if action == "update" and e.get("proposed"):
            q.update(e["proposed"])
            if q.get("type") != "multiple_choice":
                q.pop("options", None)
        out.append(q)
    return out
