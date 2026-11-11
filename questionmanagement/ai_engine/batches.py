"""Storage for AI-generated batches (questionmanagement/ai_generated_questions).

File format (unchanged, so existing history pages and old batches keep working):
    {"metadata": {...}, "questions": [...]}
Legacy batches that are a bare list of questions are still readable.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

BATCH_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ai_generated_questions")
os.makedirs(BATCH_DIR, exist_ok=True)


def _path(batch_id: str) -> str:
    safe = "".join(ch for ch in str(batch_id) if ch.isalnum() or ch in "-_")
    return os.path.join(BATCH_DIR, f"{safe}.json")


def _load(batch_id: str) -> Any:
    path = _path(batch_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def save_batch(batch_id: str, questions: List[Dict], metadata: Dict) -> None:
    metadata = dict(metadata)
    metadata.setdefault("timestamp", datetime.now().isoformat())
    metadata["num_questions"] = len(questions)
    with open(_path(batch_id), "w", encoding="utf-8") as fh:
        json.dump({"metadata": metadata, "questions": questions}, fh, indent=2, ensure_ascii=False)


def get_batch(batch_id: str) -> Optional[List[Dict]]:
    data = _load(batch_id)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("questions"), list):
        return data["questions"]
    return None


def get_batch_metadata(batch_id: str) -> Optional[Dict]:
    data = _load(batch_id)
    path = _path(batch_id)
    if data is None:
        return None
    if isinstance(data, dict) and isinstance(data.get("metadata"), dict):
        meta = dict(data["metadata"])
        meta.setdefault("num_questions", len(data.get("questions") or []))
        return meta
    ts = datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
    return {"timestamp": ts, "num_questions": len(data) if isinstance(data, list) else 0,
            "prompt": "Unknown (legacy format)", "question_type": "mixed", "difficulty": "mixed",
            "language": "unknown"}


def get_all_batches() -> List[Dict]:
    out = []
    for name in os.listdir(BATCH_DIR):
        if not name.endswith(".json"):
            continue
        batch_id = name[:-5]
        meta = get_batch_metadata(batch_id) or {"timestamp": "", "num_questions": 0, "prompt": "Unreadable batch"}
        out.append({"batch_id": batch_id, "metadata": meta})
    out.sort(key=lambda b: str(b["metadata"].get("timestamp", "")), reverse=True)
    return out


def recent_questions(limit_batches: int = 40) -> List[Dict]:
    qs: List[Dict] = []
    for b in get_all_batches()[:limit_batches]:
        for q in get_batch(b["batch_id"]) or []:
            if isinstance(q, dict):
                qs.append(q)
    return qs
