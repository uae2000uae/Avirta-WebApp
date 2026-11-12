"""Admin login: password only, from ADMIN_PASSWORD (Secret Manager/env), lockout after failures."""
import pytest

from contents.admin_controls import admin_auth, secret_loader


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "correct horse")
    secret_loader._SECRET_CACHE.clear()
    admin_auth.reset()
    yield
    admin_auth.reset()


def test_correct_password():
    assert admin_auth.check_login("1.2.3.4", "correct horse") == (True, "")


def test_wrong_or_empty_password():
    assert admin_auth.check_login("1.2.3.4", "nope")[0] is False
    assert admin_auth.check_login("1.2.3.4", "")[0] is False
    assert admin_auth.check_login("1.2.3.4", None)[0] is False
    assert admin_auth.check_login("1.2.3.4", "correct horse ")[0] is False  # exact match only


def test_old_hard_coded_password_no_longer_works():
    assert admin_auth.check_login("1.2.3.4", "123333")[0] is False


def test_lockout_after_repeated_failures_even_with_right_password():
    for _ in range(admin_auth.MAX_FAILURES):
        admin_auth.check_login("9.9.9.9", "bad")
    ok, msg = admin_auth.check_login("9.9.9.9", "correct horse")
    assert not ok and "Too many" in msg
    # Other addresses are not affected; the lock expires.
    assert admin_auth.check_login("8.8.8.8", "correct horse")[0]
    later = __import__("time").time() + admin_auth.LOCKOUT + 1
    assert admin_auth.check_login("9.9.9.9", "correct horse", now=later)[0]


def test_fails_closed_without_a_password(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setattr(secret_loader, "_detect_project_id", lambda: None)
    secret_loader._SECRET_CACHE.clear()
    ok, msg = admin_auth.check_login("1.2.3.4", "anything")
    assert not ok and "not configured" in msg


def test_login_route_needs_only_the_password(client):
    with client.session_transaction() as s:
        s["_csrf_token"] = "t"
    bad = client.post("/admin", data={"password": "123333", "csrf_token": "t"})
    assert b"Invalid password" in bad.data
    good = client.post("/admin", data={"password": "correct horse", "csrf_token": "t"})
    assert good.status_code == 302
    with client.session_transaction() as s:
        assert s.get("admin_authenticated") is True


def test_login_forms_have_no_username_field(client):
    page = client.get("/").data.decode("utf-8")
    assert 'name="password"' in page and 'name="username"' not in page
