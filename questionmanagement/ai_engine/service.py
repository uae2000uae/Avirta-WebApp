"""Small helpers shared by routes: build a client for the active (or a given) option,
and a thread-safe job registry for progress polling."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from questionmanagement.ai_engine import config, keys
from questionmanagement.ai_engine.client import AIError, LLMClient


def ai_config_of(admin_setup) -> Dict[str, Any]:
    gs = getattr(admin_setup, "game_settings", {}) or {}
    return config.normalize_ai_config(gs.get("ai_config"))


def build_client(admin_setup, option_id: Optional[str] = None,
                 overrides: Optional[Dict[str, Any]] = None) -> Tuple[LLMClient, Dict[str, Any]]:
    """Client for ``option_id`` (default: the active option). ``overrides`` lets the
    settings page test unsaved values (model/base_url/api_format/quality)."""
    cfg = ai_config_of(admin_setup)
    oid = option_id if option_id in config.OPTION_IDS else cfg["active"]
    if overrides:
        merged = dict(cfg["options"][oid])
        merged.update({k: v for k, v in overrides.items() if v not in (None, "")})
        cfg["options"][oid] = config.normalize_option_config(oid, merged)
    runtime = config.resolve_runtime(cfg, oid)
    api_key = keys.get_key(oid) or ""
    if not api_key and not _is_local(runtime["base_url"]):
        if config.OPTIONS[oid].get("key_managed"):
            raise AIError(f"{runtime['secret_name']} was not found in Google Cloud Secret Manager. "
                          "Add it in the Cloud Console (Security > Secret Manager).")
        raise AIError(f"No API key is set for {runtime['label']}. Add one in Admin > API Settings.")
    return LLMClient(runtime, api_key), runtime


def _is_local(url: str) -> bool:
    return any(h in (url or "") for h in ("localhost", "127.0.0.1", "0.0.0.0"))


class Jobs:
    """Tiny in-memory job registry (the service runs on a single instance)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def create(self, kind: str, **fields) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            # Keep the registry small.
            if len(self._jobs) > 30:
                for old in sorted(self._jobs, key=lambda j: self._jobs[j]["created"])[:10]:
                    self._jobs.pop(old, None)
            self._jobs[job_id] = {"id": job_id, "kind": kind, "status": "running", "percent": 0,
                                  "stage": "Starting…", "created": time.time(), **fields}
        return job_id

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(fields)

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def latest(self, kind: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            mine = [j for j in self._jobs.values() if j["kind"] == kind]
            return dict(max(mine, key=lambda j: j["created"])) if mine else None


jobs = Jobs()


def run_in_background(job_id: str, fn, *args, **kwargs) -> None:
    def _run():
        try:
            fn(job_id, *args, **kwargs)
        except AIError as exc:
            jobs.update(job_id, status="error", error=str(exc), stage="Stopped")
        except Exception as exc:  # never leave a job "running" forever
            jobs.update(job_id, status="error", error=f"{type(exc).__name__}: {exc}", stage="Stopped")
    threading.Thread(target=_run, daemon=True).start()
