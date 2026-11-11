"""One GitHub sync for all app data.

Every trigger (the admin "Sync to GitHub" button, ending or resetting a game,
saving questions, reports, AI reviews...) calls ``request_sync(reason)``. A
single background worker then:

  1. lists every data file the app can change at runtime (SYNC_GLOBS);
  2. compares each file's git blob hash with the branch on GitHub and keeps
     only the files that differ (so unchanged files cost nothing);
  3. commits them in ONE commit (``[skip ci]`` so it never redeploys);
  4. retries transient failures, and if it still fails records a failure that
     the in-game / admin pop-up shows immediately (see /api/sync/alerts).

Requests are never dropped: if a sync is running, the next one is queued and
runs right after (several requests in the meantime collapse into one).
Source code is never pushed from here - it cannot change on the server.
Files are only added/updated, never deleted on GitHub.
"""
from __future__ import annotations

import glob
import hashlib
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

import requests

from contents.admin_controls.github_integration import GitHubIntegration, _repo_root

log = logging.getLogger("avirta.github_sync")

# Repo-relative patterns of runtime data (posix paths, fnmatch syntax).
SYNC_GLOBS = [
    "contents/questions/*.json",
    "questionmanagement/reported_questions/*.json",
    "datastore/usage/*.json",
    "contents/game_events/*.json",
    "contents/game_events/events/*.jsonl",
    "contents/game_events/rooms/*.json",
    "questionmanagement/ai_generated_questions/*.json",
    "contents/admin_controls/game_settings.json",
    "contents/admin_controls/saved_api_settings.json",
]
NEVER_SYNC = {".local_ai_keys.json"}

MAX_ATTEMPTS = 3
RETRY_DELAYS = (5, 20)          # seconds before attempt 2 and 3
MAX_FILE_BYTES = 20 * 1024 * 1024

_lock = threading.Lock()
_wake = threading.Event()
_state: Dict[str, object] = {
    "status": "idle",            # idle | running | success | failed
    "message": "",
    "errors": [],
    "files_count": 0,
    "current_branch": "",
    "pending": [],               # reasons waiting for the next run
    "last_success": None,        # {"time", "message", "files"}
    "last_failure": None,        # {"id", "time", "message", "reasons"}
    "history": [],               # last runs, newest first
}
_worker: Optional[threading.Thread] = None
# Contents captured at request time, for files the app deletes right after
# asking for a sync (e.g. a finished game's log files). path -> bytes
_snapshot: Dict[str, bytes] = {}
_on_event: Optional[Callable[[str, str, str], None]] = None  # (level, message, detail)


def set_event_hook(fn: Callable[[str, str, str], None]) -> None:
    """Let the app record sync results in its admin log / stats."""
    global _on_event
    _on_event = fn


def _emit(level: str, message: str, detail: str = "") -> None:
    if level == "ERROR":
        # Tagged so it is easy to find (and alert on) in Cloud Logging.
        log.error("GITHUB_SYNC_FAILED %s %s", message, detail)
    else:
        log.info("GITHUB_SYNC %s", message)
    if _on_event:
        try:
            _on_event(level, message, detail)
        except Exception:
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------- files
def list_sync_files(root: Optional[str] = None) -> List[str]:
    """Repo-relative paths of every runtime data file that exists right now."""
    root = root or _repo_root()
    out = set()
    for pattern in SYNC_GLOBS:
        for path in glob.glob(os.path.join(root, *pattern.split("/"))):
            if os.path.isfile(path) and os.path.basename(path) not in NEVER_SYNC:
                out.add(os.path.relpath(path, root).replace("\\", "/"))
    return sorted(out)


def _blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


# ---------------------------------------------------------------------- sync
def _read_all(root: str) -> Dict[str, bytes]:
    data: Dict[str, bytes] = {}
    for rel in list_sync_files(root):
        path = os.path.join(root, *rel.split("/"))
        try:
            if os.path.getsize(path) <= MAX_FILE_BYTES:
                with open(path, "rb") as fh:
                    data[rel] = fh.read()
        except OSError:
            continue
    return data


def sync_once(reasons: List[str], gh: Optional[GitHubIntegration] = None,
              root: Optional[str] = None, snapshot: Optional[Dict[str, bytes]] = None) -> Tuple[bool, str, int]:
    """Run one sync. Returns (ok, message, files_committed)."""
    gh = gh or GitHubIntegration()
    root = root or gh.repo_root
    if not gh.token:
        return False, "GITHUB_TOKEN is missing (add it in Google Cloud Secret Manager).", 0
    _set(current_branch=gh.branch, message=f"Checking {gh.repo}@{gh.branch}…")

    local = dict(snapshot or {})
    local.update(_read_all(root))  # files on disk now win over older snapshots

    try:
        r = gh._get(f"git/ref/heads/{gh.branch}")
        if r.status_code in (401, 403):
            return False, f"GitHub rejected the token (HTTP {r.status_code}). Check GITHUB_TOKEN and its access to {gh.repo}.", 0
        if r.status_code == 404:
            return False, f"Branch '{gh.branch}' or repository '{gh.repo}' was not found on GitHub.", 0
        if not r.ok:
            return False, f"Could not read the branch (HTTP {r.status_code}).", 0
        head_sha = r.json()["object"]["sha"]
        r = gh._get(f"git/commits/{head_sha}")
        if not r.ok:
            return False, f"Could not read the latest commit (HTTP {r.status_code}).", 0
        base_tree = r.json()["tree"]["sha"]
        r = gh._get(f"git/trees/{base_tree}?recursive=1")
        if not r.ok:
            return False, f"Could not read the repository tree (HTTP {r.status_code}).", 0
        remote = {e["path"]: e["sha"] for e in r.json().get("tree", []) if e.get("type") == "blob"}

        changed = [p for p, data in local.items() if remote.get(p) != _blob_sha(data)]
        if not changed:
            return True, f"Already up to date ({len(local)} data files checked).", 0

        _set(files_count=len(changed), message=f"Uploading {len(changed)} changed file(s)…")
        entries = []
        for rel in changed:
            data = local[rel]
            try:
                payload = {"content": data.decode("utf-8"), "encoding": "utf-8"}
            except UnicodeDecodeError:
                import base64
                payload = {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"}
            br = gh._post("git/blobs", payload)
            if not br.ok:
                return False, f"Upload of {rel} failed (HTTP {br.status_code}).", 0
            entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": br.json()["sha"]})

        tr = gh._post("git/trees", {"base_tree": base_tree, "tree": entries})
        if not tr.ok:
            return False, f"Could not build the commit tree (HTTP {tr.status_code}).", 0
        summary = ", ".join(sorted(set(reasons)))[:120] or "manual sync"
        author = {"name": "Avirta", "email": "avirta-sync@users.noreply.github.com", "date": _now()}
        cr = gh._post("git/commits", {
            "message": f"Sync app data: {summary} [skip ci]",
            "tree": tr.json()["sha"], "parents": [head_sha], "author": author, "committer": author,
        })
        if not cr.ok:
            return False, f"Could not create the commit (HTTP {cr.status_code}).", 0
        ur = gh._patch(f"git/refs/heads/{gh.branch}", {"sha": cr.json()["sha"], "force": False})
        if ur.status_code == 422:
            return False, "The branch moved on GitHub while syncing (will retry).", 0
        if not ur.ok:
            return False, f"Could not update the branch (HTTP {ur.status_code}).", 0
        return True, f"Synced {len(changed)} file(s) to {gh.repo}@{gh.branch} ({cr.json()['sha'][:7]}).", len(changed)
    except requests.RequestException as exc:
        return False, f"Network error talking to GitHub: {type(exc).__name__}.", 0
    except (KeyError, ValueError) as exc:
        return False, f"Unexpected answer from GitHub ({type(exc).__name__}).", 0


# -------------------------------------------------------------------- worker
def _set(**fields) -> None:
    with _lock:
        _state.update(fields)


def _run_worker() -> None:
    global _worker
    while True:
        with _lock:
            reasons = list(_state["pending"])
            _state["pending"] = []
            snap = dict(_snapshot)
            _snapshot.clear()
            if not reasons:
                _worker = None
                return
            _state.update(status="running", errors=[], files_count=0,
                          message="Starting sync…")
        ok, msg, files = False, "", 0
        for attempt in range(1, MAX_ATTEMPTS + 1):
            ok, msg, files = sync_once(reasons, snapshot=snap)
            if ok or "token" in msg.lower() or "not found" in msg.lower():
                break  # success, or a configuration problem retrying cannot fix
            if attempt < MAX_ATTEMPTS:
                _set(message=f"{msg} Retrying ({attempt + 1}/{MAX_ATTEMPTS})…")
                time.sleep(RETRY_DELAYS[attempt - 1])
        entry = {"time": _now(), "ok": ok, "message": msg, "reasons": reasons, "files": files}
        with _lock:
            _state["history"] = ([entry] + list(_state["history"]))[:20]
            if ok:
                _state.update(status="success", message=msg, last_success=entry)
            else:
                # Keep captured contents (e.g. deleted game logs) for the next attempt.
                for k, v in snap.items():
                    _snapshot.setdefault(k, v)
                failure = dict(entry, id=uuid.uuid4().hex[:10])
                _state.update(status="failed", message=msg, errors=[msg], last_failure=failure)
        if ok:
            _emit("SUCCESS" if files else "INFO", msg, ", ".join(reasons))
        else:
            _emit("ERROR", f"GitHub sync failed: {msg}", ", ".join(reasons))


def request_sync(reason: str = "manual sync", capture: bool = True) -> Tuple[bool, str]:
    """Queue a sync. Never drops a request.

    ``capture`` reads the data files now, so files deleted before the worker
    runs (a finished game's logs) are still sent.
    """
    global _worker
    captured = _read_all(_repo_root()) if capture else {}
    with _lock:
        _snapshot.update(captured)
        if reason not in _state["pending"]:
            _state["pending"].append(reason)
        if _worker is not None and _worker.is_alive():
            return True, "Queued: will sync right after the one in progress."
        _worker = threading.Thread(target=_run_worker, name="github-sync", daemon=True)
        _worker.start()
    return True, "Sync to GitHub started."


def get_status() -> Dict[str, object]:
    with _lock:
        out = dict(_state)
        out["errors"] = list(_state["errors"])
        out["pending"] = list(_state["pending"])
        out["history"] = list(_state["history"])
        return out


def current_failure() -> Optional[Dict[str, object]]:
    """The latest failure, unless a later sync succeeded."""
    with _lock:
        fail, ok = _state["last_failure"], _state["last_success"]
        if not fail:
            return None
        if ok and str(ok["time"]) > str(fail["time"]):
            return None
        return dict(fail)
