"""Tests for the single GitHub sync (fake GitHub API, temp project folder)."""
import hashlib
import json
import os
import time

import pytest

from contents.admin_controls import github_sync


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class FakeResp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.ok = 200 <= status < 300
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeGitHub:
    """Just enough of the Git Data API for sync_once."""

    def __init__(self, root, remote_files=None, fail=None):
        self.token = "t"
        self.repo = "owner/repo"
        self.branch = "main"
        self.repo_root = root
        self.remote = dict(remote_files or {})  # path -> sha
        self.fail = fail
        self.commits = []
        self.blobs = []

    def _get(self, path):
        if self.fail == "network":
            import requests
            raise requests.ConnectionError("down")
        if self.fail == "auth":
            return FakeResp(401)
        if path.startswith("git/ref/heads/"):
            return FakeResp(200, {"object": {"sha": "head1"}})
        if path.startswith("git/commits/"):
            return FakeResp(200, {"tree": {"sha": "tree1"}})
        if path.startswith("git/trees/"):
            return FakeResp(200, {"tree": [{"path": p, "sha": s, "type": "blob"} for p, s in self.remote.items()]})
        return FakeResp(404)

    def _post(self, path, payload):
        if path == "git/blobs":
            self.blobs.append(payload)
            return FakeResp(201, {"sha": "b%d" % len(self.blobs)})
        if path == "git/trees":
            return FakeResp(201, {"sha": "tree2"})
        if path == "git/commits":
            self.commits.append(payload)
            return FakeResp(201, {"sha": "commit123456"})
        return FakeResp(404)

    def _patch(self, path, payload):
        return FakeResp(200, {})


def write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return text.encode("utf-8")


@pytest.fixture()
def project(tmp_path, monkeypatch):
    root = str(tmp_path)
    monkeypatch.setattr(github_sync, "_repo_root", lambda: root)
    with github_sync._lock:
        github_sync._snapshot.clear()
        github_sync._baselines.pop(os.path.abspath(root), None)
        github_sync._state.update(status="idle", pending=[], last_success=None, last_failure=None, history=[])
    return root


def test_only_changed_data_files_are_committed(project):
    same = write(project, "contents/questions/geo.json", '[{"q": 1}]')
    write(project, "contents/questions/sci.json", '[{"q": 2}]')
    write(project, "datastore/usage/usage_x.json", "{}")
    write(project, "app.py", "print('source code is never synced')")
    write(project, "contents/admin_controls/.local_ai_keys.json", "{}")
    gh = FakeGitHub(project, {"contents/questions/geo.json": blob_sha(same)})
    ok, msg, files = github_sync.sync_once(["test"], gh=gh, root=project)
    assert ok and files == 2, msg
    assert len(gh.commits) == 1 and "[skip ci]" in gh.commits[0]["message"]
    assert len(gh.blobs) == 2


def test_up_to_date_makes_no_commit(project):
    data = write(project, "contents/questions/geo.json", "[]")
    gh = FakeGitHub(project, {"contents/questions/geo.json": blob_sha(data)})
    ok, msg, files = github_sync.sync_once(["test"], gh=gh, root=project)
    assert ok and files == 0 and not gh.commits and "up to date" in msg


def test_snapshot_keeps_files_deleted_after_request(project):
    log = write(project, "contents/game_events/events/room1.jsonl", '{"e":"game_ended"}\n')
    snap = github_sync._read_all(project)
    os.remove(os.path.join(project, "contents", "game_events", "events", "room1.jsonl"))
    gh = FakeGitHub(project)
    ok, _msg, files = github_sync.sync_once(["game ended"], gh=gh, root=project, snapshot=snap)
    assert ok and files == 1 and gh.blobs[0]["content"] == log.decode()


def test_auth_failure_is_reported(project):
    write(project, "contents/questions/geo.json", "[]")
    ok, msg, _ = github_sync.sync_once(["test"], gh=FakeGitHub(project, fail="auth"), root=project)
    assert not ok and "token" in msg.lower()


def test_worker_records_failure_and_queues_requests(project, monkeypatch):
    write(project, "contents/questions/geo.json", "[]")
    calls = []
    events = []

    def fake_sync(reasons, gh=None, root=None, snapshot=None):
        calls.append(list(reasons))
        time.sleep(0.05)
        return False, "GitHub rejected the token (HTTP 401).", 0

    monkeypatch.setattr(github_sync, "sync_once", fake_sync)
    github_sync.set_event_hook(lambda level, message, detail: events.append(level))
    try:
        github_sync.request_sync("game ended (r1)")
        github_sync.request_sync("manual sync")  # arrives while the first is running -> queued, not dropped
        for _ in range(100):
            st = github_sync.get_status()
            if st["status"] == "failed" and not st["pending"] and github_sync._worker is None:
                break
            time.sleep(0.02)
        flat = [r for c in calls for r in c]
        assert "game ended (r1)" in flat and "manual sync" in flat
        failure = github_sync.current_failure()
        assert failure and failure["id"] and "token" in failure["message"].lower()
        assert "ERROR" in events
    finally:
        github_sync.set_event_hook(None)


def test_end_game_requests_sync_and_alerts_admin(client, monkeypatch):
    import app as app_module
    requested = []
    monkeypatch.setattr(app_module._github_sync, "request_sync", lambda reason, capture=True: (requested.append(reason) or (True, "ok")))
    with client.session_transaction() as s:
        s["admin_authenticated"] = True
        s["_csrf_token"] = "test-token"
    # Direct helper call inside a request context marks this browser as watching.
    with app_module.app.test_request_context("/"):
        from flask import session
        app_module._request_github_sync("game ended (abc)")
        assert session.get("sync_watch")
    assert requested == ["game ended (abc)"]

    with github_sync._lock:
        github_sync._state.update(last_failure={"id": "f1", "time": "2099-01-01T00:00:00+00:00",
                                                "message": "boom", "reasons": ["x"]}, last_success=None)
    data = client.get("/api/sync/alerts").get_json()
    assert data["watch"] and data["failure"]["id"] == "f1" and data["is_admin"]
    client.post("/api/sync/ack", json={"id": "f1"}, headers={"X-CSRFToken": _csrf(client)})
    assert client.get("/api/sync/alerts").get_json()["failure"] is None


def test_players_are_not_polled(client):
    assert client.get("/api/sync/alerts").get_json() == {"watch": False}


def _csrf(client):
    with client.session_transaction() as s:
        return s["_csrf_token"]


def test_files_untouched_since_start_are_never_pushed(project):
    """A new revision ships older copies of data files. If another revision
    updated one on GitHub since, the untouched copy must not roll it back."""
    write(project, "datastore/usage/usage_old_revision.json", '{"Q1": 10}')
    write(project, "contents/questions/geo.json", "[1]")
    github_sync.capture_baseline(project)            # the files as deployed
    newer = b'{"Q1": 12}'                             # the old revision synced 2 more uses
    gh = FakeGitHub(project, {"datastore/usage/usage_old_revision.json": blob_sha(newer)})
    write(project, "contents/questions/geo.json", "[1, 2]")                 # changed here
    mine = write(project, "datastore/usage/usage_this_revision.json", '{"Q2": 1}')  # created here
    ok, msg, files = github_sync.sync_once(["game ended"], gh=gh, root=project)
    assert ok and files == 2, msg
    pushed = {b["content"] for b in gh.blobs}
    assert mine.decode() in pushed and "[1, 2]" in pushed
    assert '{"Q1": 10}' not in pushed                 # the stale ledger stays on GitHub as 12
