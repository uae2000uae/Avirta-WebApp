"""Per-instance usage ledger (grow-only counters) for question `use_count`.

Why this exists
---------------
`use_count` is a counter incremented from many game sessions/instances. Storing
it inline in the question files makes it *unmergeable* — two sessions both read
5, both write 6, and the true 7 is lost — and it rewrites the whole category
file on every single play (constant churn).

This module keeps each running instance's usage in its OWN file:

    datastore/usage/usage_<INSTANCE_ID>.json   ->   { "Q0001331": 12, ... }

Each instance only ever writes its own file, so pushes never conflict and no
increment is ever lost (a grow-only / G-Counter CRDT). The effective use count
of a question is:

    effective = base (value frozen in the question file) + sum of that id
                across all ledger files

The question files themselves are NEVER rewritten on a play, so they stop
churning and only change on genuine content edits (admin add/edit/delete).

Public surface
--------------
    increment(question_id)          -> bump this instance's tally by 1
    get_totals()                    -> {question_id: total across all ledgers}
    this_ledger_relpath()           -> repo-relative path of this instance's file
    rollup_into_question_files(...)  -> (optional, single-writer) fold totals into
                                        the question files and compact ledgers
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from typing import Dict, List, Optional

_LOCK = threading.RLock()
_USAGE_SUBDIR = ("datastore", "usage")


def _repo_root() -> str:
    # questionmanagement/usage_ledger.py -> repo root is one level up
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def usage_dir() -> str:
    d = os.path.join(_repo_root(), *_USAGE_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


_INSTANCE_ID: Optional[str] = None


def instance_id() -> str:
    """Stable id for this container/process.

    Persisted in datastore/usage/.instance_id so a process restart within the
    same container reuses the same ledger file. A brand-new container (e.g. a new
    Cloud Run revision) gets a fresh id; totals still sum correctly across files.
    """
    global _INSTANCE_ID
    if _INSTANCE_ID:
        return _INSTANCE_ID
    with _LOCK:
        if _INSTANCE_ID:
            return _INSTANCE_ID
        marker = os.path.join(usage_dir(), ".instance_id")
        try:
            if os.path.isfile(marker):
                with open(marker, "r", encoding="utf-8") as fh:
                    val = fh.read().strip()
                if val:
                    _INSTANCE_ID = val
                    return _INSTANCE_ID
        except Exception:
            pass
        rev = os.environ.get("K_REVISION") or "local"
        _INSTANCE_ID = f"{rev}_{uuid.uuid4().hex[:8]}"
        try:
            with open(marker, "w", encoding="utf-8") as fh:
                fh.write(_INSTANCE_ID)
        except Exception:
            pass
        return _INSTANCE_ID


def _ledger_filename(inst: Optional[str] = None) -> str:
    return f"usage_{inst or instance_id()}.json"


def this_ledger_path() -> str:
    return os.path.join(usage_dir(), _ledger_filename())


def this_ledger_relpath() -> str:
    """Repo-relative path of this instance's ledger (for the GitHub push)."""
    return f"{_USAGE_SUBDIR[0]}/{_USAGE_SUBDIR[1]}/{_ledger_filename()}"


# In-memory copy of THIS instance's ledger (disk is kept in sync on every write).
_ledger: Optional[Dict[str, int]] = None


def _load_this_ledger() -> Dict[str, int]:
    global _ledger
    if _ledger is not None:
        return _ledger
    data: Dict[str, int] = {}
    path = this_ledger_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                data = {str(k): int(v) for k, v in raw.items()
                        if isinstance(v, (int, float))}
        except Exception:
            data = {}
    _ledger = data
    return _ledger


def _save_this_ledger() -> None:
    path = this_ledger_path()
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(_ledger or {}, fh, ensure_ascii=False, sort_keys=True, indent=0)
    os.replace(tmp, path)  # atomic


# Order in which this instance played questions (oldest first, newest last).
# Used to break ties: among equally used questions, the ones just played go last.
_RECENT: Dict[str, None] = {}
_RECENT_MAX = 3000


def increment(question_id: str, n: int = 1) -> int:
    """Add `n` to this instance's tally for `question_id`; returns new local tally."""
    if not question_id:
        return 0
    with _LOCK:
        led = _load_this_ledger()
        led[question_id] = int(led.get(question_id, 0)) + int(n)
        _save_this_ledger()
        _RECENT.pop(question_id, None)
        _RECENT[question_id] = None
        while len(_RECENT) > _RECENT_MAX:
            _RECENT.pop(next(iter(_RECENT)))
        return led[question_id]


def recently_played() -> Dict[str, int]:
    """{question_id: rank}, higher = played more recently on this instance."""
    with _LOCK:
        return {qid: i for i, qid in enumerate(_RECENT)}


def list_ledger_files(directory: Optional[str] = None) -> List[str]:
    d = directory or usage_dir()
    out: List[str] = []
    if os.path.isdir(d):
        for name in sorted(os.listdir(d)):
            if name.startswith("usage_") and name.endswith(".json"):
                out.append(os.path.join(d, name))
    return out


def get_totals() -> Dict[str, int]:
    """Sum usage across ALL ledger files -> {question_id: total_uses}."""
    totals: Dict[str, int] = {}
    with _LOCK:
        for path in list_ledger_files():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            for qid, v in raw.items():
                try:
                    totals[str(qid)] = totals.get(str(qid), 0) + int(v)
                except (TypeError, ValueError):
                    continue
    return totals


def rollup_into_question_files(question_storage_path: str) -> Dict[str, int]:
    """Fold every ledger total into the question files' `use_count`, then clear
    the ledgers. SINGLE-WRITER operation — run from one place (an admin action or
    a scheduled task on one instance) during a quiet moment.

    Returns a summary: {"questions_updated": n, "ledgers_cleared": m}.
    """
    with _LOCK:
        totals = get_totals()
        updated = 0
        if totals and os.path.isdir(question_storage_path):
            for name in os.listdir(question_storage_path):
                if not name.endswith(".json"):
                    continue
                fpath = os.path.join(question_storage_path, name)
                try:
                    with open(fpath, "r", encoding="utf-8") as fh:
                        questions = json.load(fh)
                except Exception:
                    continue
                if not isinstance(questions, list):
                    continue
                changed = False
                for q in questions:
                    qid = q.get("id")
                    delta = totals.get(qid, 0)
                    if qid and delta:
                        q["use_count"] = int(q.get("use_count", 0) or 0) + int(delta)
                        changed = True
                        updated += 1
                if changed:
                    tmp = f"{fpath}.tmp"
                    with open(tmp, "w", encoding="utf-8") as fh:
                        json.dump(questions, fh, ensure_ascii=False, indent=2)
                    os.replace(tmp, fpath)

        # Compact: delete all ledger files and reset our in-memory ledger. Their
        # counts are now baked into the question files.
        cleared = 0
        for path in list_ledger_files():
            try:
                os.remove(path)
                cleared += 1
            except Exception:
                pass
        global _ledger
        _ledger = {}
        return {"questions_updated": updated, "ledgers_cleared": cleared}
