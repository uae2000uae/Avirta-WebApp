"""
GitHub Integration for Avirta - Push question content to GitHub via the REST API.

This module is deliberately SELF-CONTAINED and INDEPENDENT of any other tool:

  * It does NOT shell out to the `git` binary.
  * It does NOT depend on local git credentials, SSH keys, or a checked-out
    working tree.
  * It does NOT import `git_push_helper` or any other Avirta module for its core
    work (only the optional `secret_loader`, with a graceful fallback).

Instead it talks directly to the GitHub REST API (https://api.github.com) using a
personal-access token (``GITHUB_TOKEN``). Because it is pure HTTP, it works
identically on Cloud Run, in local development, from a background thread, from a
Flask route, or from the command line.

Public surface (can be called from anywhere in the app):

    from contents.admin_controls.github_integration import (
        GitHubIntegration,
        push_all_amended_questions_async,
        push_files_async,
        get_push_progress,
    )

    # Fire-and-forget from a request handler:
    push_all_amended_questions_async(detach=True)

    # Synchronous, returns (ok, message):
    ok, msg = push_all_amended_questions_async(detach=False)

    # Push an explicit list of files:
    push_files_async(["contents/questions/cars.json"], commit_message="Update cars")

    # Direct object use:
    gh = GitHubIntegration()
    if gh.token:
        gh.push_paths(["contents/questions/cars.json"], "Update cars")

Configuration (all optional, resolved via env vars / Google Secret Manager):

    GITHUB_TOKEN   - personal access token with `repo` (or contents:write) scope. Required.
    GITHUB_REPO    - "owner/repo". Defaults to parsing .git/config, else "uae2000uae/Avirta-WebApp".
    GITHUB_BRANCH  - target branch. Defaults to reading .git/HEAD, else "Avirta-1".
    GITHUB_API_URL - API base (for GitHub Enterprise). Defaults to "https://api.github.com".
"""

from __future__ import annotations

import base64
import os
import re
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests

# --- Optional secret loader (graceful fallback to os.environ) ----------------
try:
    from contents.admin_controls.secret_loader import get_secret as _get_secret
except Exception:  # pragma: no cover - fallback if module layout differs
    def _get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
        val = os.environ.get(key)
        return val.strip() if isinstance(val, str) and val.strip() else default


# --- Defaults ----------------------------------------------------------------
_DEFAULT_REPO = "uae2000uae/Avirta-WebApp"  # renamed from Avirta-1
_DEFAULT_BRANCH = "Avirta-1"
_DEFAULT_API = "https://api.github.com"
_COMMIT_AUTHOR_NAME = "Copilot"
_COMMIT_AUTHOR_EMAIL = "223556219+Copilot@users.noreply.github.com"
_REQUEST_TIMEOUT = 30

# Token that tells Cloud Build to skip the build for a commit, so question-data
# syncs never trigger a Cloud Run redeploy. Appended to every commit this module
# makes. (The full-source push in git_push_helper.py intentionally omits it.)
_SKIP_CI_TOKEN = "[skip ci]"


def _repo_root() -> str:
    """Absolute path to the Avirta project root (…/contents/admin_controls/..)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Thread-safe progress state (shape matches git_push_helper for UI parity)
# =============================================================================
_progress_lock = threading.Lock()
_progress_status: Dict[str, object] = {
    "status": "idle",          # "idle" | "running" | "success" | "failed"
    "message": "",
    "errors": [],
    "files_count": 0,
    "current_branch": _DEFAULT_BRANCH,
}


def get_push_progress() -> dict:
    """Progress of the shared GitHub sync (see github_sync.py)."""
    from contents.admin_controls.github_sync import get_status
    return get_status()


def _update_progress(status: Optional[str] = None, message: Optional[str] = None,
                     files_count: Optional[int] = None, error: Optional[str] = None,
                     branch: Optional[str] = None, reset_errors: bool = False) -> None:
    with _progress_lock:
        if reset_errors:
            _progress_status["errors"] = []
        if status is not None:
            _progress_status["status"] = status
        if message is not None:
            _progress_status["message"] = message
        if files_count is not None:
            _progress_status["files_count"] = files_count
        if error is not None:
            _progress_status["errors"].append(error)  # type: ignore[attr-defined]
        if branch is not None:
            _progress_status["current_branch"] = branch


# =============================================================================
# GitHub API client
# =============================================================================
class GitHubIntegration:
    """Minimal GitHub REST API client for committing files to a branch.

    Constructing this object never raises on missing configuration; callers
    should check ``self.token`` before attempting a push.
    """

    def __init__(self, token: Optional[str] = None, repo: Optional[str] = None,
                 branch: Optional[str] = None, api_url: Optional[str] = None,
                 repo_root: Optional[str] = None):
        self.repo_root = repo_root or _repo_root()
        self.token = token or _get_secret("GITHUB_TOKEN")
        self.repo = repo or _get_secret("GITHUB_REPO") or self._detect_repo() or _DEFAULT_REPO
        self.branch = branch or _get_secret("GITHUB_BRANCH") or self._detect_branch() or _DEFAULT_BRANCH
        self.api_url = (api_url or _get_secret("GITHUB_API_URL") or _DEFAULT_API).rstrip("/")

    # -- configuration discovery (file reads only, no git binary) -------------
    def _detect_repo(self) -> Optional[str]:
        """Parse owner/repo from .git/config's origin remote (best-effort)."""
        cfg = os.path.join(self.repo_root, ".git", "config")
        try:
            with open(cfg, "r", encoding="utf-8") as fh:
                text = fh.read()
        except Exception:
            return None
        m = re.search(r"url\s*=\s*.*github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?\s*$",
                      text, re.MULTILINE)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
        return None

    def _detect_branch(self) -> Optional[str]:
        """Read current branch from .git/HEAD (best-effort)."""
        head = os.path.join(self.repo_root, ".git", "HEAD")
        try:
            with open(head, "r", encoding="utf-8") as fh:
                ref = fh.read().strip()
        except Exception:
            return None
        if ref.startswith("ref:"):
            return ref.split("/", 2)[-1]
        return None

    # -- HTTP helpers ---------------------------------------------------------
    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _url(self, path: str) -> str:
        return f"{self.api_url}/repos/{self.repo}/{path.lstrip('/')}"

    def _get(self, path: str) -> requests.Response:
        return requests.get(self._url(path), headers=self._headers, timeout=_REQUEST_TIMEOUT)

    def _post(self, path: str, payload: dict) -> requests.Response:
        return requests.post(self._url(path), headers=self._headers, json=payload,
                             timeout=_REQUEST_TIMEOUT)

    def _patch(self, path: str, payload: dict) -> requests.Response:
        return requests.patch(self._url(path), headers=self._headers, json=payload,
                              timeout=_REQUEST_TIMEOUT)

    # -- core operation -------------------------------------------------------
    def push_paths(self, rel_paths: List[str],
                   commit_message: Optional[str] = None) -> Tuple[bool, str]:
        """Commit the given repo-relative files to the branch in one atomic commit.

        Uses the Git Data API (blobs -> tree -> commit -> ref) so that all files
        land in a single commit and unchanged files produce no diff. Files that
        do not exist locally are skipped. Returns (success, message).
        """
        if not self.token:
            return False, "Missing GITHUB_TOKEN. Set it as an env var or in Secret Manager."

        # Read + normalise the file list.
        blobs: List[Tuple[str, object]] = []  # (posix_path, content or ("__b64__", b64))
        for rel in rel_paths:
            posix = rel.replace("\\", "/").lstrip("/")
            abs_path = os.path.join(self.repo_root, *posix.split("/"))
            if not os.path.isfile(abs_path):
                continue
            try:
                with open(abs_path, "rb") as fh:
                    raw = fh.read()
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                # Store binary content as a base64 blob instead.
                blobs.append((posix, ("__b64__", base64.b64encode(raw).decode("ascii"))))
                continue
            blobs.append((posix, content))

        if not blobs:
            return True, "No matching files found to push. Nothing to do."

        try:
            # 1) Current branch tip.
            r = self._get(f"git/ref/heads/{self.branch}")
            if r.status_code == 404:
                return False, (f"Branch '{self.branch}' not found in {self.repo}. "
                               f"Check GITHUB_BRANCH / GITHUB_REPO.")
            if r.status_code == 401:
                return False, "GitHub rejected the token (401). Check GITHUB_TOKEN validity/scope."
            if not r.ok:
                return False, f"Failed to read branch ref ({r.status_code}): {r.text[:200]}"
            base_commit_sha = r.json()["object"]["sha"]

            # 2) Base tree of that commit.
            r = self._get(f"git/commits/{base_commit_sha}")
            if not r.ok:
                return False, f"Failed to read base commit ({r.status_code}): {r.text[:200]}"
            base_tree_sha = r.json()["tree"]["sha"]

            # 3) Create blobs + assemble tree entries.
            tree_entries = []
            for posix, content in blobs:
                if isinstance(content, tuple) and content[0] == "__b64__":
                    blob_payload = {"content": content[1], "encoding": "base64"}
                else:
                    blob_payload = {"content": content, "encoding": "utf-8"}
                br = self._post("git/blobs", blob_payload)
                if not br.ok:
                    return False, f"Failed to create blob for {posix} ({br.status_code}): {br.text[:200]}"
                tree_entries.append({
                    "path": posix,
                    "mode": "100644",
                    "type": "blob",
                    "sha": br.json()["sha"],
                })

            # 4) Create the new tree on top of the base tree.
            tr = self._post("git/trees", {"base_tree": base_tree_sha, "tree": tree_entries})
            if not tr.ok:
                return False, f"Failed to create tree ({tr.status_code}): {tr.text[:200]}"
            new_tree_sha = tr.json()["sha"]

            # Nothing actually changed -> don't create an empty commit.
            if new_tree_sha == base_tree_sha:
                return True, "No changes detected. Repository already up to date."

            # 5) Create the commit.
            msg = commit_message or "Update amended question files"
            # Ensure Cloud Build skips deploying for this data-only commit.
            if _SKIP_CI_TOKEN not in msg and "[ci skip]" not in msg:
                msg = f"{msg} {_SKIP_CI_TOKEN}"
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            author = {"name": _COMMIT_AUTHOR_NAME, "email": _COMMIT_AUTHOR_EMAIL, "date": now}
            cr = self._post("git/commits", {
                "message": msg,
                "tree": new_tree_sha,
                "parents": [base_commit_sha],
                "author": author,
                "committer": author,
            })
            if not cr.ok:
                return False, f"Failed to create commit ({cr.status_code}): {cr.text[:200]}"
            new_commit_sha = cr.json()["sha"]

            # 6) Move the branch ref forward.
            ur = self._patch(f"git/refs/heads/{self.branch}",
                             {"sha": new_commit_sha, "force": False})
            if not ur.ok:
                return False, f"Failed to update branch ref ({ur.status_code}): {ur.text[:200]}"

            return True, (f"Pushed {len(tree_entries)} file(s) to "
                          f"{self.repo}@{self.branch} ({new_commit_sha[:7]}).")

        except requests.RequestException as e:
            return False, f"Network error talking to GitHub: {e}"
        except Exception as e:  # pragma: no cover - unexpected
            return False, f"Unexpected error during push: {e}"


# =============================================================================
# Module-level helpers (the surface app.py imports)
# =============================================================================
def _list_question_files(repo_root: Optional[str] = None) -> List[str]:
    """Return repo-relative paths of all question JSON files under contents/questions."""
    root = repo_root or _repo_root()
    qdir = os.path.join(root, "contents", "questions")
    out: List[str] = []
    if not os.path.isdir(qdir):
        return out
    for name in sorted(os.listdir(qdir)):
        if name.lower().endswith(".json"):
            out.append(f"contents/questions/{name}")
    return out


def _list_report_files(repo_root: Optional[str] = None) -> List[str]:
    """Return repo-relative paths of all reported-question JSON files."""
    root = repo_root or _repo_root()
    rdir = os.path.join(root, "questionmanagement", "reported_questions")
    out: List[str] = []
    if not os.path.isdir(rdir):
        return out
    for name in sorted(os.listdir(rdir)):
        if name.lower().endswith(".json"):
            out.append(f"questionmanagement/reported_questions/{name}")
    return out


def _run_push(rel_paths: List[str], commit_message: Optional[str],
              gh: Optional[GitHubIntegration] = None) -> Tuple[bool, str]:
    """Perform a push while updating the shared progress state."""
    gh = gh or GitHubIntegration()
    _update_progress(status="running", message="Initializing GitHub push...",
                     branch=gh.branch, files_count=len(rel_paths), reset_errors=True)

    if not gh.token:
        msg = "Missing GITHUB_TOKEN. GitHub upload not started."
        _update_progress(status="failed", message=msg, error=msg)
        return False, msg

    _update_progress(message=f"Uploading {len(rel_paths)} file(s) to {gh.repo}@{gh.branch}...")
    ok, msg = gh.push_paths(rel_paths, commit_message=commit_message)
    if ok:
        _update_progress(status="success", message=msg)
    else:
        _update_progress(status="failed", message=msg, error=msg)
    return ok, msg


# All app pushes go through the single sync in github_sync.py: it sends every
# changed data file in one commit, queues requests instead of dropping them,
# retries, and reports failures to the in-game / admin pop-up. These wrappers
# keep the old function names working for existing call sites.
def _sync(reason: str) -> Tuple[bool, str]:
    from contents.admin_controls.github_sync import request_sync
    return request_sync(reason)


def push_files_async(rel_paths: List[str], commit_message: Optional[str] = None,
                     detach: bool = True) -> Tuple[bool, str]:
    return _sync(commit_message or "files updated")


def push_all_amended_questions_async(commit_message: Optional[str] = None,
                                     detach: bool = True,
                                     repo_root: Optional[str] = None) -> Tuple[bool, str]:
    return _sync(commit_message or "questions updated")


def push_reports_async(commit_message: Optional[str] = None, detach: bool = True,
                       repo_root: Optional[str] = None,
                       include_questions: bool = True) -> Tuple[bool, str]:
    return _sync(commit_message or "question reported")


def push_usage_ledger_async(commit_message: Optional[str] = None,
                            detach: bool = True) -> Tuple[bool, str]:
    return _sync(commit_message or "usage counts")


def push_to_github(commit_message: Optional[str] = None,
                   detach: bool = False) -> Tuple[bool, str]:
    return _sync(commit_message or "manual sync")


# =============================================================================
# CLI entrypoint  ->  python -m contents.admin_controls.github_integration
# =============================================================================
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Push Avirta question files to GitHub via the REST API (no git binary)."
    )
    parser.add_argument("--message", "-m", default=None, help="Commit message")
    parser.add_argument("--files", nargs="*", default=None,
                        help="Explicit repo-relative files to push (default: all question JSON)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be pushed and the resolved config, then exit")
    args = parser.parse_args()

    gh = GitHubIntegration()
    targets = args.files if args.files else _list_question_files()

    print("Avirta - GitHub Integration (REST API)")
    print("======================================")
    print(f"Repo   : {gh.repo}")
    print(f"Branch : {gh.branch}")
    print(f"Token  : {'present' if gh.token else 'MISSING (set GITHUB_TOKEN)'}")
    print(f"Files  : {len(targets)} file(s)")

    if args.dry_run:
        for t in targets:
            print(f"  - {t}")
        sys.exit(0)

    ok, msg = _run_push(targets, args.message, gh=gh)
    print(f"\nResult: {msg}")
    sys.exit(0 if ok else 1)
