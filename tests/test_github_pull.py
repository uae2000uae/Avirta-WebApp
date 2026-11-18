"""Tests for pulling GitHub data changes into a running server (fake GitHub, temp folder)."""
import base64
import hashlib
import json
import os

import pytest

from contents.admin_controls import github_pull, github_sync


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class FakeResp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.ok = 200 <= status < 300

    def json(self):
        return self._payload


class FakeGitHub:
    """GitHub holding ``files`` (path -> bytes) at commit ``head``."""

    def __init__(self, root, files, head="head1"):
        self.token = "t"
        self.branch = "main"
        self.repo_root = str(root)
        self.files = dict(files)
        self.head = head
        self.calls = []

    def _get(self, path, timeout=None):
        self.calls.append(path)
        if path.startswith("git/ref/heads/"):
            return FakeResp(200, {"object": {"sha": self.head}})
        if path.startswith("git/commits/"):
            return FakeResp(200, {"tree": {"sha": "tree-" + self.head}})
        if path.startswith("git/trees/"):
            return FakeResp(200, {"tree": [{"path": p, "sha": blob_sha(d), "type": "blob"}
                                           for p, d in self.files.items()]})
        if path.startswith("git/blobs/"):
            sha = path.rsplit("/", 1)[1]
            for d in self.files.values():
                if blob_sha(d) == sha:
                    return FakeResp(200, {"content": base64.b64encode(d).decode(), "encoding": "base64"})
        return FakeResp(404)


def write(root, rel, data: bytes):
    path = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def read(root, rel):
    path = os.path.join(str(root), *rel.split("/"))
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return fh.read()


Q = "contents/questions/science.json"


def test_newer_question_file_on_github_replaces_untouched_local_copy(tmp_path):
    write(tmp_path, Q, b'[{"id": "Q1"}]')
    github_sync.capture_baseline(str(tmp_path))  # as shipped with the deploy
    gh = FakeGitHub(tmp_path, {Q: b'[{"id": "Q1"}, {"id": "Q2"}]'})

    res = github_pull.refresh(force=True, gh=gh)

    assert res["pulled"] == 1
    assert read(tmp_path, Q) == b'[{"id": "Q1"}, {"id": "Q2"}]'
    # The pulled copy is GitHub's: the next sync must not push it back.
    assert not github_sync._changed_here(Q, read(tmp_path, Q), str(tmp_path))


def test_new_file_on_github_is_added(tmp_path):
    github_sync.capture_baseline(str(tmp_path))
    gh = FakeGitHub(tmp_path, {"contents/questions/new.json": b"[]"})
    assert github_pull.refresh(force=True, gh=gh)["pulled"] == 1
    assert read(tmp_path, "contents/questions/new.json") == b"[]"


def test_file_changed_here_and_on_github_keeps_local_copy(tmp_path):
    write(tmp_path, Q, b"shipped")
    github_sync.capture_baseline(str(tmp_path))
    write(tmp_path, Q, b"edited here")
    gh = FakeGitHub(tmp_path, {Q: b"edited on github"})

    res = github_pull.refresh(force=True, gh=gh)

    assert res["conflicts"] == 1
    assert read(tmp_path, Q) == b"edited here"


def test_file_deleted_here_is_not_brought_back(tmp_path):
    write(tmp_path, Q, b"[]")
    github_sync.capture_baseline(str(tmp_path))
    os.remove(os.path.join(str(tmp_path), *Q.split("/")))
    gh = FakeGitHub(tmp_path, {Q: b"[]"})

    github_pull.refresh(force=True, gh=gh)

    assert read(tmp_path, Q) is None


def test_usage_ledgers_merge_keeping_the_larger_count(tmp_path):
    rel = "datastore/usage/usage_other.json"
    write(tmp_path, rel, json.dumps({"Q1": 5, "Q2": 1}).encode())
    github_sync.capture_baseline(str(tmp_path))
    write(tmp_path, rel, json.dumps({"Q1": 5, "Q2": 1, "Q3": 1}).encode())  # played here
    gh = FakeGitHub(tmp_path, {rel: json.dumps({"Q1": 7, "Q2": 1}).encode()})

    res = github_pull.refresh(force=True, gh=gh)

    assert res["merged"] == 1
    assert json.loads(read(tmp_path, rel)) == {"Q1": 7, "Q2": 1, "Q3": 1}


def test_other_servers_plays_count_after_a_restart(tmp_path):
    """A fresh container (deploy-time files) must see plays pushed since."""
    rel = "datastore/usage/usage_rev1_aaaa.json"
    github_sync.capture_baseline(str(tmp_path))  # this ledger was not in the deploy
    gh = FakeGitHub(tmp_path, {rel: json.dumps({"Q1": 3}).encode()})

    github_pull.refresh(force=True, gh=gh)

    assert json.loads(read(tmp_path, rel)) == {"Q1": 3}


def test_only_runtime_data_is_pulled(tmp_path):
    github_sync.capture_baseline(str(tmp_path))
    gh = FakeGitHub(tmp_path, {"app.py": b"code", "contents/game_events/rooms/r.json": b"{}",
                               Q: b"[]"})
    github_pull.refresh(force=True, gh=gh)
    assert read(tmp_path, "app.py") is None
    assert read(tmp_path, "contents/game_events/rooms/r.json") is None
    assert read(tmp_path, Q) == b"[]"


def test_unchanged_commit_costs_one_call(tmp_path):
    github_sync.capture_baseline(str(tmp_path))
    gh = FakeGitHub(tmp_path, {Q: b"[]"})
    github_pull.refresh(force=True, gh=gh)
    gh.calls.clear()

    res = github_pull.refresh(force=True, gh=gh)

    assert res["status"] == "unchanged"
    assert len(gh.calls) == 1


def test_checks_are_throttled(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_PULL_INTERVAL", "60")
    gh = FakeGitHub(tmp_path, {})
    github_pull.refresh(force=True, gh=gh)
    assert github_pull.refresh(gh=gh)["status"] == "throttled"


def test_github_errors_never_raise(tmp_path):
    class Down(FakeGitHub):
        def _get(self, path, timeout=None):
            import requests
            raise requests.ConnectionError("down")

    res = github_pull.refresh(force=True, gh=Down(tmp_path, {}))
    assert res["status"] == "error"


@pytest.mark.parametrize("env,expected", [
    ({}, False),
    ({"K_SERVICE": "avirta"}, True),
    ({"K_SERVICE": "avirta", "GITHUB_PULL": "0"}, False),
    ({"GITHUB_PULL": "1"}, True),
])
def test_enabled_on_cloud_run_by_default(monkeypatch, env, expected):
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("GITHUB_PULL", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert github_pull.enabled() is expected


def test_successful_push_lets_later_github_edits_through(tmp_path):
    """After a sync pushes our edit, a later edit made on GitHub is pulled."""
    write(tmp_path, Q, b"shipped")
    github_sync.capture_baseline(str(tmp_path))
    write(tmp_path, Q, b"edited here")
    github_sync.remember_remote_sha(Q, blob_sha(b"edited here"), str(tmp_path))  # as sync_once does
    gh = FakeGitHub(tmp_path, {Q: b"edited on github later"})

    assert github_pull.refresh(force=True, gh=gh)["pulled"] == 1
    assert read(tmp_path, Q) == b"edited on github later"


def test_own_ledger_merge_updates_the_in_memory_copy(tmp_path, monkeypatch):
    from questionmanagement import usage_ledger
    monkeypatch.setattr(usage_ledger, "usage_dir", lambda: str(tmp_path))
    monkeypatch.setattr(usage_ledger, "_INSTANCE_ID", "me")
    monkeypatch.setattr(usage_ledger, "_ledger", {"Q1": 2})

    usage_ledger.merge_ledger_file("usage_me.json", json.dumps({"Q1": 1, "Q9": 4}).encode())
    usage_ledger.increment("Q1")

    with open(os.path.join(str(tmp_path), "usage_me.json"), encoding="utf-8") as fh:
        assert json.load(fh) == {"Q1": 3, "Q9": 4}
