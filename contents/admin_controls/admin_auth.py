"""Admin login checks.

Admin access is password only. The password is never stored in the code: it
lives in Google Cloud Secret Manager as ADMIN_PASSWORD (read through
secret_loader, so an environment variable of the same name also works for
local development) and is compared in constant time.

If no password is configured, admin login is refused (fail closed).

Repeated failures are throttled per client address: after MAX_FAILURES failed
attempts within WINDOW seconds, that address is locked out for LOCKOUT seconds.
The service runs on a single instance, so in-memory tracking is enough.
"""
from __future__ import annotations

import hmac
import threading
import time
from typing import Dict, List, Optional, Tuple

from contents.admin_controls.secret_loader import get_secret

MAX_FAILURES = 5
WINDOW = 15 * 60
LOCKOUT = 15 * 60

_lock = threading.Lock()
_failures: Dict[str, List[float]] = {}
_locked_until: Dict[str, float] = {}


def _password() -> Optional[str]:
    value = get_secret("ADMIN_PASSWORD")
    value = value.strip() if value else ""
    return value or None


def is_configured() -> bool:
    return bool(_password())


def client_key(request) -> str:
    """Best-effort client address (Cloud Run puts the real one first in X-Forwarded-For)."""
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or request.remote_addr or "unknown"


def seconds_locked(key: str, now: Optional[float] = None) -> int:
    now = now or time.time()
    with _lock:
        until = _locked_until.get(key, 0)
        if until <= now:
            _locked_until.pop(key, None)
            return 0
        return int(until - now) + 1


def _record_failure(key: str, now: float) -> None:
    with _lock:
        recent = [t for t in _failures.get(key, []) if now - t < WINDOW]
        recent.append(now)
        _failures[key] = recent
        if len(recent) >= MAX_FAILURES:
            _locked_until[key] = now + LOCKOUT
            _failures[key] = []


def check_login(key: str, password: str, now: Optional[float] = None) -> Tuple[bool, str]:
    """Return (ok, message). The message is safe to show on the login page."""
    now = now or time.time()
    wait = seconds_locked(key, now)
    if wait:
        return False, f"Too many failed attempts. Try again in {max(1, wait // 60)} minute(s)."
    stored = _password()
    if not stored:
        return False, "Admin login is not configured on this server (ADMIN_PASSWORD is missing)."
    if hmac.compare_digest((password or "").encode("utf-8"), stored.encode("utf-8")):
        with _lock:
            _failures.pop(key, None)
        return True, ""
    _record_failure(key, now)
    wait = seconds_locked(key, now)
    if wait:
        return False, f"Too many failed attempts. Try again in {max(1, wait // 60)} minute(s)."
    return False, "Invalid password."


def reset() -> None:
    """Forget all failures (used by tests)."""
    with _lock:
        _failures.clear()
        _locked_until.clear()
