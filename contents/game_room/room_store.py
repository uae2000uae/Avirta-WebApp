"""Live game rooms that survive restarts and redeploys.

``PersistentRooms`` is a drop-in replacement for the plain ``game_rooms`` dict.
It keeps rooms in memory as before, and additionally:

* after each request, saves the full state of every room the request touched
  (only when that state actually changed), and
* when a room is not in memory (for example on a freshly deployed revision),
  loads it back from the store.

The store is Firestore when ``ROOM_STORE=firestore`` (set on Cloud Run);
otherwise there is no store and the class behaves exactly like a dict, which is
what local runs and the tests use. Store errors are logged and never break a
game: the room simply stays in memory only.

Room objects are saved as compressed JSON of their attributes. Only the room
classes listed in ``_ALLOWED`` (and plain data) are written or rebuilt, so a
stored document can never instantiate arbitrary code.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import threading
import time
import zlib
from datetime import date, datetime
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

_ALLOWED = {
    "contents.game_room.game_room:GameRoom",
    "contents.thehive.hex_game_room:HexGameRoom",
    "contents.fastest.fastest_game_room:FastestGameRoom",
    "questionmanagement.question_manager:QuestionManager",
}

# A room nobody has touched for this long is treated as finished.
MAX_AGE_SECONDS = 12 * 3600


# --------------------------------------------------------------------------
# Serialisation
# --------------------------------------------------------------------------

def _class_path(obj: Any) -> str:
    cls = type(obj)
    return f"{cls.__module__}:{cls.__qualname__}"


def encode(value: Any) -> Any:
    """Turn a room (and everything inside it) into JSON-compatible data."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [encode(v) for v in value]
    if isinstance(value, tuple):
        return {"__tuple__": [encode(v) for v in value]}
    if isinstance(value, (set, frozenset)):
        return {"__set__": [encode(v) for v in value]}
    if isinstance(value, datetime):
        return {"__dt__": value.isoformat()}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, dict):
        if all(isinstance(k, str) for k in value):
            return {k: encode(v) for k, v in value.items()}
        return {"__pairs__": [[encode(k), encode(v)] for k, v in value.items()]}
    path = _class_path(value)
    if path in _ALLOWED:
        return {"__obj__": path, "state": encode(vars(value))}
    raise TypeError(f"cannot store a {path} inside a game room")


def _hashable(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_hashable(v) for v in value)
    return value


def decode(value: Any) -> Any:
    if isinstance(value, list):
        return [decode(v) for v in value]
    if not isinstance(value, dict):
        return value
    if len(value) == 1:
        (tag, inner), = value.items()
        if tag == "__tuple__":
            return tuple(decode(v) for v in inner)
        if tag == "__set__":
            return {_hashable(decode(v)) for v in inner}
        if tag == "__dt__":
            return datetime.fromisoformat(inner)
        if tag == "__date__":
            return date.fromisoformat(inner)
        if tag == "__pairs__":
            return {_hashable(decode(k)): decode(v) for k, v in inner}
    if set(value) == {"__obj__", "state"}:
        path = value["__obj__"]
        if path not in _ALLOWED:
            raise TypeError(f"refusing to rebuild a {path}")
        module, name = path.split(":")
        cls = getattr(importlib.import_module(module), name)
        obj = cls.__new__(cls)
        obj.__dict__.update(decode(value["state"]))
        return obj
    return {k: decode(v) for k, v in value.items()}


def dumps(room: Any) -> bytes:
    return json.dumps(encode(room), ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True).encode("utf-8")


def loads(raw: bytes) -> Any:
    return decode(json.loads(raw.decode("utf-8")))


# --------------------------------------------------------------------------
# Stores
# --------------------------------------------------------------------------

class FirestoreRoomBackend:
    """rooms/{room_id} = {data: zlib(JSON), kind, updated_at} in a named database."""

    def __init__(self, database: str, collection: str = "rooms"):
        from google.cloud import firestore  # imported lazily; only needed on Cloud Run
        self._col = firestore.Client(database=database).collection(collection)

    def get(self, room_id: str) -> Optional[Dict[str, Any]]:
        snap = self._col.document(room_id).get()
        return snap.to_dict() if snap.exists else None

    def put(self, room_id: str, data: bytes, kind: str) -> None:
        self._col.document(room_id).set({"data": data, "kind": kind, "updated_at": time.time()})

    def delete(self, room_id: str) -> None:
        self._col.document(room_id).delete()


def backend_from_env():
    if os.environ.get("ROOM_STORE", "").lower() != "firestore":
        return None
    database = os.environ.get("FIRESTORE_DATABASE", "avirta-state")
    try:
        return FirestoreRoomBackend(database)
    except Exception as exc:  # pragma: no cover - depends on the environment
        log.error("Room store unavailable, rooms stay in memory only: %s", exc)
        return None


# --------------------------------------------------------------------------
# The dict
# --------------------------------------------------------------------------

class PersistentRooms(dict):
    """A ``dict`` of room_id -> room that saves to and reloads from a store."""

    def __init__(self, backend=None, max_age: float = MAX_AGE_SECONDS):
        super().__init__()
        self.backend = backend
        self.max_age = max_age
        self._digests: Dict[str, str] = {}
        self._lock = threading.RLock()
        self._local = threading.local()

    # -- request tracking ------------------------------------------------
    def begin_request(self) -> None:
        self._local.touched = set()

    def _touch(self, room_id: Any) -> None:
        touched = getattr(self._local, "touched", None)
        if touched is not None and isinstance(room_id, str):
            touched.add(room_id)

    def end_request(self) -> None:
        touched = getattr(self._local, "touched", None) or set()
        self._local.touched = None
        for room_id in touched:
            if dict.__contains__(self, room_id):
                self.save(room_id)

    # -- dict behaviour --------------------------------------------------
    def __contains__(self, room_id) -> bool:
        self._touch(room_id)
        return dict.__contains__(self, room_id) or self._load(room_id)

    def __getitem__(self, room_id):
        self._touch(room_id)
        if not dict.__contains__(self, room_id):
            self._load(room_id)
        return dict.__getitem__(self, room_id)

    def get(self, room_id, default=None):
        return self[room_id] if room_id in self else default

    def __setitem__(self, room_id, room) -> None:
        dict.__setitem__(self, room_id, room)
        self._touch(room_id)
        self.save(room_id)

    def __delitem__(self, room_id) -> None:
        dict.__delitem__(self, room_id)
        self._forget(room_id)

    def pop(self, room_id, *default):
        had = dict.__contains__(self, room_id)
        value = dict.pop(self, room_id, *default)
        if had:
            self._forget(room_id)
        return value

    # -- store -----------------------------------------------------------
    def save(self, room_id: str) -> bool:
        """Write the room if its state changed since the last write."""
        if self.backend is None or not dict.__contains__(self, room_id):
            return False
        room = dict.__getitem__(self, room_id)
        with self._lock:
            try:
                raw = dumps(room)
            except Exception as exc:
                log.error("Room %s could not be serialised: %s", room_id, exc)
                return False
            digest = hashlib.sha1(raw).hexdigest()
            if self._digests.get(room_id) == digest:
                return False
            try:
                self.backend.put(room_id, zlib.compress(raw, 6), _class_path(room))
            except Exception as exc:
                log.error("Room %s could not be saved: %s", room_id, exc)
                return False
            self._digests[room_id] = digest
            return True

    def _load(self, room_id) -> bool:
        if self.backend is None or not isinstance(room_id, str) or not room_id:
            return False
        with self._lock:
            if dict.__contains__(self, room_id):
                return True
            try:
                doc = self.backend.get(room_id)
                if not doc or time.time() - float(doc.get("updated_at", 0)) > self.max_age:
                    return False
                raw = zlib.decompress(bytes(doc["data"]))
                room = loads(raw)
            except Exception as exc:
                log.error("Room %s could not be loaded: %s", room_id, exc)
                return False
            dict.__setitem__(self, room_id, room)
            self._digests[room_id] = hashlib.sha1(raw).hexdigest()
            log.info("Room %s restored from the store", room_id)
            return True

    def _forget(self, room_id) -> None:
        self._digests.pop(room_id, None)
        if self.backend is not None:
            try:
                self.backend.delete(room_id)
            except Exception as exc:
                log.error("Room %s could not be deleted from the store: %s", room_id, exc)
