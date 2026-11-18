"""Bring data changes from GitHub into this running server (the pull half of
github_sync.py).

Why this exists
---------------
A Cloud Run container starts from the files that were in the repository when
it was deployed. Data syncs are committed with ``[skip ci]``, so they never
redeploy, and before this module the server never read them back:

  * a container that restarts (Cloud Run recycles instances, a crash, a new
    revision) went back to the deploy-time copy of the question files and the
    usage ledgers, so the questions played since then looked unplayed and came
    back in the next game;
  * a question edited or added directly on GitHub never reached a running game.

``refresh()`` fixes both. It is called before the question bank is read (every
``load_questions()``, so before every new board and at startup). It is cheap:
one GitHub call when nothing changed, throttled to one check every
``GITHUB_PULL_INTERVAL`` seconds, and it never raises.

Per file it does:

  * same as GitHub              -> nothing;
  * usage ledger (grow-only)    -> merge, keeping the larger count per question,
                                   so no play recorded here or there is lost;
  * not changed here since it
    last matched GitHub         -> replace with GitHub's copy;
  * changed here and on GitHub  -> keep ours (the next sync pushes it) and log.

Files are only added or updated, never deleted, and a file deleted on this
server (a category, a closed report) is not brought back.

Switch: ``GITHUB_PULL`` = 1/0. Default: on when running on Cloud Run
(``K_SERVICE`` is set), off elsewhere so a developer's checkout and the tests
are never rewritten behind their back.
"""
from __future__ import annotations

import base64
import fnmatch
import hashlib
import logging
import os
import threading
import time
from typing import Dict, Optional

import requests

from contents.admin_controls import github_sync
from contents.admin_controls.github_integration import GitHubIntegration, _repo_root

log = logging.getLogger("avirta.github_pull")

# Data the app reads from disk while it runs (repo-relative, fnmatch syntax).
PULL_GLOBS = [
    "contents/questions/*.json",
    "datastore/usage/*.json",
    "questionmanagement/reported_questions/*.json",
    "contents/category_tags.json",
]
LEDGER_GLOB = "datastore/usage/usage_*.json"

PULL_TIMEOUT = 8              # seconds per GitHub call; a game must not hang on GitHub
DEFAULT_INTERVAL = 20         # seconds between two checks of GitHub

_pull_lock = threading.Lock()
_last_check: Dict[str, float] = {}   # root -> time of the last check
_last_head: Dict[str, str] = {}      # root -> GitHub commit fully applied here
_last_result: Dict[str, object] = {}


def enabled() -> bool:
    val = os.environ.get("GITHUB_PULL", "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return bool(os.environ.get("K_SERVICE"))


def _interval() -> float:
    try:
        return max(0.0, float(os.environ.get("GITHUB_PULL_INTERVAL", DEFAULT_INTERVAL)))
    except ValueError:
        return DEFAULT_INTERVAL


def _blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _wanted(rel: str) -> bool:
    if os.path.basename(rel) in github_sync.NEVER_SYNC:
        return False
    return any(fnmatch.fnmatch(rel, pattern) for pattern in PULL_GLOBS)


def _get(gh, path: str):
    return gh._get(path, timeout=PULL_TIMEOUT)


def _read(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.pulltmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)  # atomic: readers see the old or the new file, never half


def _fetch_blob(gh, sha: str) -> bytes:
    r = _get(gh, f"git/blobs/{sha}")
    if not r.ok:
        raise ValueError(f"blob {sha[:7]}: HTTP {r.status_code}")
    body = r.json()
    if body.get("encoding") == "base64":
        return base64.b64decode(body.get("content", ""))
    return str(body.get("content", "")).encode("utf-8")


def last_result() -> Dict[str, object]:
    return dict(_last_result)


def refresh(force: bool = False, gh=None, root: Optional[str] = None) -> Dict[str, object]:
    """Apply GitHub's newer data files to this server. Never raises.

    Returns a summary: {"status", "pulled", "merged", "conflicts", "message"}.
    """
    if gh is None and not enabled():
        return {"status": "disabled"}
    root = os.path.abspath(root or (gh.repo_root if gh is not None else _repo_root()))
    with _pull_lock:
        now = time.time()
        if not force and now - _last_check.get(root, 0.0) < _interval():
            return {"status": "throttled"}
        _last_check[root] = now
        result = _refresh_locked(gh, root)
        _last_result.clear()
        _last_result.update(result, time=now)
        if result.get("status") == "error":
            log.warning("GITHUB_PULL_FAILED %s", result.get("message"))
        elif result.get("pulled") or result.get("merged") or result.get("conflicts"):
            log.info("GITHUB_PULL %s", result.get("message"))
        return result


def _refresh_locked(gh, root: str) -> Dict[str, object]:
    out: Dict[str, object] = {"status": "ok", "pulled": 0, "merged": 0, "conflicts": 0}
    try:
        gh = gh or GitHubIntegration(repo_root=root)
        if not gh.token:
            return {"status": "disabled", "message": "GITHUB_TOKEN is missing."}
        # The files as they are before the first pull are the shipped copy.
        github_sync.capture_baseline(root)

        r = _get(gh, f"git/ref/heads/{gh.branch}")
        if not r.ok:
            return {"status": "error", "message": f"Could not read the branch (HTTP {r.status_code})."}
        head = r.json()["object"]["sha"]
        if _last_head.get(root) == head:
            return dict(out, status="unchanged", message="Already up to date.")
        r = _get(gh, f"git/commits/{head}")
        if not r.ok:
            return {"status": "error", "message": f"Could not read the latest commit (HTTP {r.status_code})."}
        r = _get(gh, f"git/trees/{r.json()['tree']['sha']}?recursive=1")
        if not r.ok:
            return {"status": "error", "message": f"Could not read the repository tree (HTTP {r.status_code})."}
        remote = {e["path"]: e["sha"] for e in r.json().get("tree", [])
                  if e.get("type") == "blob" and _wanted(e.get("path", ""))}

        for rel, sha in sorted(remote.items()):
            path = os.path.join(root, *rel.split("/"))
            local = _read(path)
            known = github_sync.known_remote_sha(rel, root)
            if local is None and known is not None:
                continue  # deleted on this server (a category or report): keep it deleted
            if local is not None and _blob_sha(local) == sha:
                github_sync.remember_remote_sha(rel, sha, root)
                continue
            if fnmatch.fnmatch(rel, LEDGER_GLOB):
                from questionmanagement.usage_ledger import merge_ledger_file
                merged = merge_ledger_file(os.path.basename(rel), _fetch_blob(gh, sha),
                                           directory=os.path.dirname(path))
                if _blob_sha(merged) == sha:
                    github_sync.remember_remote_sha(rel, sha, root)
                out["merged"] = int(out["merged"]) + 1
                continue
            if local is None or _blob_sha(local) == known:
                data = _fetch_blob(gh, sha)
                _write(path, data)
                github_sync.remember_remote_sha(rel, sha, root)
                out["pulled"] = int(out["pulled"]) + 1
                continue
            # Changed here and on GitHub: ours wins, the next sync sends it.
            out["conflicts"] = int(out["conflicts"]) + 1
            log.warning("GITHUB_PULL_CONFLICT %s changed here and on GitHub; keeping this server's copy", rel)

        _last_head[root] = head
        out["message"] = (f"{out['pulled']} file(s) updated, {out['merged']} usage ledger(s) merged, "
                          f"{out['conflicts']} kept local, from {head[:7]}.")
        return out
    except requests.RequestException as exc:
        return {"status": "error", "message": f"Network error talking to GitHub: {type(exc).__name__}."}
    except (KeyError, ValueError, OSError) as exc:
        return {"status": "error", "message": f"Pull failed: {type(exc).__name__}: {exc}"}
