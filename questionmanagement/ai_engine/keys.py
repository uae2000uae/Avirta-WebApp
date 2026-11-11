"""API key storage for the three AI options.

Read order for a key (first hit wins):
  1. a key saved from the admin page during this process (in-memory)
  2. the environment variable / Google Secret Manager secret
     (OPENAI_API_KEY, ANTHROPIC_API_KEY, CUSTOM_AI_API_KEY)
  3. local development only: contents/admin_controls/.local_ai_keys.json
     (git- and gcloud-ignored; never used on Cloud Run)

The ChatGPT and Claude keys are *managed*: they are maintained in Google Cloud
Secret Manager and can only be read here, never entered on the admin page.
Only the "own key" option (CUSTOM_AI_API_KEY) can be saved from the page; that
writes a new version of the secret (creating it if needed), which needs the
Cloud Run service account to hold "Secret Manager Secret Version Adder" on it
(and "Secret Manager Admin" to create it the first time).
"""
from __future__ import annotations

import json
import os
import threading
from typing import Dict, Optional, Tuple

from contents.admin_controls import secret_loader
from questionmanagement.ai_engine.config import OPTIONS

_LOCK = threading.Lock()
_OVERRIDES: Dict[str, str] = {}  # secret_name -> key saved during this process

_LOCAL_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "contents", "admin_controls", ".local_ai_keys.json",
)


def on_cloud_run() -> bool:
    return bool(os.environ.get("K_SERVICE"))


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    if v.lower().startswith("bearer "):
        v = v[7:].strip()
    if not v or v in {"SET_IN_ENV", "set_in_env"} or v.lower() in {"none", "null"}:
        return None
    return v


def _read_local() -> Dict[str, str]:
    if on_cloud_run() or not os.path.exists(_LOCAL_FILE):
        return {}
    try:
        with open(_LOCAL_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {k: v for k, v in data.items() if isinstance(v, str)}
    except Exception:
        return {}


def _write_local(secret_name: str, value: str) -> None:
    data = _read_local()
    data[secret_name] = value
    with open(_LOCAL_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _lookup(secret_name: str) -> Tuple[Optional[str], str]:
    with _LOCK:
        if _OVERRIDES.get(secret_name):
            return _OVERRIDES[secret_name], "saved from this page"
    env_val = _clean(os.environ.get(secret_name))
    if env_val:
        return env_val, "Secret Manager" if on_cloud_run() else "environment variable"
    gsm_val = _clean(secret_loader.get_secret(secret_name))
    if gsm_val:
        return gsm_val, "Secret Manager"
    local_val = _clean(_read_local().get(secret_name))
    if local_val:
        return local_val, "local development file"
    return None, ""


def get_key(option_id: str) -> Optional[str]:
    meta = OPTIONS.get(option_id)
    if not meta:
        return None
    return _lookup(meta["secret_name"])[0]


def key_status(option_id: str) -> Dict[str, object]:
    """Non-secret description of where (and whether) a key is configured."""
    meta = OPTIONS[option_id]
    value, source = _lookup(meta["secret_name"])
    return {
        "configured": bool(value),
        "source": source,
        "hint": ("…" + value[-4:]) if value and len(value) > 8 else "",
        "secret_name": meta["secret_name"],
        "managed": bool(meta.get("key_managed")),
    }


def _gsm_save(secret_name: str, value: str) -> Tuple[bool, str]:
    try:
        from google.cloud import secretmanager  # type: ignore
        from google.api_core import exceptions as gexc  # type: ignore
    except Exception:
        return False, "google-cloud-secret-manager is not installed."
    project_id = secret_loader._detect_project_id()  # noqa: SLF001 - shared helper
    if not project_id:
        return False, "Could not determine the Google Cloud project."
    secret_id = os.environ.get(f"SECRET_{secret_name}_NAME", secret_name)
    try:
        client = secretmanager.SecretManagerServiceClient()
        parent = f"projects/{project_id}"
        secret_path = f"{parent}/secrets/{secret_id}"
        try:
            client.get_secret(request={"name": secret_path})
        except gexc.NotFound:
            client.create_secret(request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {"replication": {"automatic": {}}},
            })
        client.add_secret_version(request={
            "parent": secret_path,
            "payload": {"data": value.encode("utf-8")},
        })
        return True, f"Saved to Secret Manager as '{secret_id}'."
    except gexc.PermissionDenied:
        return False, ("Permission denied by Secret Manager. Give the Cloud Run service account the "
                       f"'Secret Manager Secret Version Adder' role on '{secret_id}' "
                       "(and 'Secret Manager Admin' if the secret does not exist yet).")
    except Exception as exc:  # network, quota, etc.
        return False, f"Secret Manager error: {type(exc).__name__}: {exc}"


def save_key(option_id: str, value: str) -> Tuple[bool, str]:
    """Store a key for an option. Returns (ok, message) - the message never contains the key."""
    meta = OPTIONS.get(option_id)
    if not meta:
        return False, "Unknown AI option."
    if meta.get("key_managed"):
        return False, (f"The {meta['label']} key is managed in Google Cloud Secret Manager "
                       f"({meta['secret_name']}) and cannot be changed here.")
    cleaned = _clean(value)
    if not cleaned:
        return False, "The key is empty."
    secret_name = meta["secret_name"]

    with _LOCK:
        _OVERRIDES[secret_name] = cleaned
    secret_loader._SECRET_CACHE.clear()  # noqa: SLF001 - drop the stale cached value

    if not on_cloud_run():
        # Local development never writes to the production Secret Manager.
        try:
            _write_local(secret_name, cleaned)
            return True, "Saved to the local development key file (not uploaded anywhere)."
        except Exception as exc:
            return False, f"Could not save the key locally: {exc}"

    ok, msg = _gsm_save(secret_name, cleaned)
    if ok:
        return True, msg
    return False, msg + " The key is active until the service restarts."
