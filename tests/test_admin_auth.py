"""Admin login: hashed password from Secret Manager/env, lockout after failures."""
import pytest
from werkzeug.security import generate_password_hash

from contents.admin_controls import admin_auth, secret_loader


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", generate_password_hash("correct horse", method="pbkdf2:sha256:1000"))
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    secret_loader._SECRET_CACHE.clear()
    admin_auth.reset()
    yield
    admin_auth.reset()


def test_correct_login():
    assert admin_auth.check_login("1.2.3.4", "Admin", "correct horse") == (True, "")


def test_wrong_password_or_username():
    assert admin_auth.check_login("1.2.3.4", "Admin", "nope")[0] is False
    assert admin_auth.check_login("1.2.3.4", "admin2", "correct horse")[0] is False


def test_old_hard_coded_password_no_longer_works():
    assert admin_auth.check_login("1.2.3.4", "Admin", "123333")[0] is False


def test_lockout_after_repeated_failures_even_with_right_password():
    for _ in range(admin_auth.MAX_FAILURES):
        admin_auth.check_login("9.9.9.9", "Admin", "bad")
    ok, msg = admin_auth.check_login("9.9.9.9", "Admin", "correct horse")
    assert not ok and "Too many" in msg
    # Other addresses are not affected; the lock expires.
    assert admin_auth.check_login("8.8.8.8", "Admin", "correct horse")[0]
    later = __import__("time").time() + admin_auth.LOCKOUT + 1
    assert admin_auth.check_login("9.9.9.9", "Admin", "correct horse", now=later)[0]


def test_fails_closed_without_a_hash(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "")
    monkeypatch.setattr(secret_loader, "_detect_project_id", lambda: None)
    secret_loader._SECRET_CACHE.clear()
    ok, msg = admin_auth.check_login("1.2.3.4", "Admin", "anything")
    assert not ok and "not configured" in msg


def test_login_route_uses_the_hash(client):
    with client.session_transaction() as s:
        s["_csrf_token"] = "t"
    bad = client.post("/admin", data={"username": "Admin", "password": "123333", "csrf_token": "t"})
    assert b"Invalid username or password" in bad.data
    good = client.post("/admin", data={"username": "Admin", "password": "correct horse", "csrf_token": "t"})
    assert good.status_code == 302
    with client.session_transaction() as s:
        assert s.get("admin_authenticated") is True
