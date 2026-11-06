"""Exercise hosted access and email flows with a synthetic provider."""

import pytest
from fastapi.testclient import TestClient

from reviewer import auth
from reviewer.api import create_app

ORIGIN = "https://review.example.test"
EMAIL = "reviewer@example.test"
PASSWORD = "sample-password"
USER = {"email": EMAIL, "email_confirmed_at": "2026-01-01T00:00:00Z"}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    for key, value in {
        "WARREN_SUPABASE_URL": "https://example.supabase.co",
        "WARREN_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
        "WARREN_PUBLIC_URL": ORIGIN,
        "WARREN_ALLOWED_EMAILS": EMAIL,
    }.items():
        monkeypatch.setenv(key, value)
    calls = []

    def provider(config, path, *, method="GET", body=None, token=None):
        calls.append((path, method, body, token))
        if path == "/token?grant_type=password":
            if body["password"] == PASSWORD:
                return {"access_token": "login-token", "expires_in": 3600, "user": USER}
        elif path == "/verify":
            return {"access_token": "recovery-token", "expires_in": 3600, "user": USER}
        elif path == "/user" and token in {"login-token", "recovery-token"}:
            return USER
        elif path in {"/signup", "/recover"}:
            return {}

    monkeypatch.setattr(auth, "provider_request", provider)
    with TestClient(
        create_app(tmp_path), base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as client:
        yield client, calls


def test_sign_in_protects_data_and_downloads(workspace):
    client, _ = workspace
    for path in (
        "/api/sessions",
        "/api/records",
        "/api/reference",
        "/api/sessions/sample/pages/1",
        "/api/checks/sample/differences.csv",
    ):
        assert client.get(path).status_code == 401
    assert client.post("/api/sessions").status_code == 401
    assert client.get("/api/health").status_code == 200
    reply = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert reply.status_code == 200
    assert reply.json() == {"email": EMAIL}
    cookie = reply.headers["set-cookie"]
    assert cookie.startswith("__Host-warren-session=")
    assert "HttpOnly" in cookie and "Secure" in cookie
    assert client.get("/api/records").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/records").status_code == 401


def test_block_unverified_unapproved_and_cross_origin(workspace, monkeypatch):
    client, calls = workspace
    credentials = {"email": EMAIL, "password": PASSWORD}
    assert (
        client.post(
            "/api/auth/login",
            json=credentials,
            headers={"Origin": "https://other.test"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/auth/signup", json={**credentials, "email": "unknown@example.test"}
        ).status_code
        == 200
    )
    assert not calls
    monkeypatch.setattr(
        auth,
        "provider_request",
        lambda *a, **k: {
            "user": {"email": EMAIL, "email_confirmed_at": None},
            "access_token": "unverified",
            "expires_in": 3600,
        },
    )
    assert client.post("/api/auth/login", json=credentials).status_code == 401
    assert client.get("/api/records").status_code == 401


def test_email_confirmation_and_recovery_do_not_grant_workspace_access(workspace):
    client, calls = workspace
    assert (
        client.post(
            "/api/auth/signup", json={"email": EMAIL, "password": PASSWORD}
        ).status_code
        == 200
    )
    assert calls[-1][0] == "/signup"
    assert client.post("/api/auth/forgot", json={"email": EMAIL}).status_code == 200
    assert calls[-1][0] == "/recover"
    link = {"token_hash": "synthetic-link-token"}
    assert (
        client.post("/api/auth/confirm", json={**link, "kind": "email"}).status_code
        == 200
    )
    assert client.get("/api/records").status_code == 401
    assert (
        client.post("/api/auth/reset", json={"password": PASSWORD}).status_code == 400
    )
    assert (
        client.post("/api/auth/confirm", json={**link, "kind": "recovery"}).status_code
        == 200
    )
    assert client.get("/api/records").status_code == 401
    assert (
        client.post("/api/auth/reset", json={"password": PASSWORD}).status_code == 200
    )
    assert calls[-1] == ("/user", "PUT", {"password": PASSWORD}, "recovery-token")
    assert (
        client.post("/api/auth/reset", json={"password": PASSWORD}).status_code == 400
    )


def test_railway_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "synthetic")
    with pytest.raises(RuntimeError, match="authentication variables"):
        create_app(tmp_path)
