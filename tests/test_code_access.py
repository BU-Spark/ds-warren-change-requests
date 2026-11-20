"""Shared code sign-in, rotation, revocation and protected API regressions."""

import pytest
from fastapi.testclient import TestClient

from reviewer.api import create_app
from reviewer.auth import AuthConfig

ORIGIN = "https://review.example.test"


@pytest.fixture
def code_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WARREN_PUBLIC_URL", ORIGIN)
    monkeypatch.delenv("WARREN_AUTH_MODE")
    with TestClient(
        create_app(tmp_path), base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as client:
        yield client


def test_code_login_protects_data_and_revokes_on_logout(code_client):
    client = code_client
    session = client.get("/api/auth/session").json()
    assert session["mode"] == "code" and session["email"] is None
    assert "1234" not in client.get("/api/auth/session").text
    assert client.get("/api/records").status_code == 401
    assert client.post("/api/auth/login", json={"code": "wrong"}).status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"email": "x", "password": "1234"}
        ).status_code
        == 401
    )
    response = client.post("/api/auth/login", json={"code": "1234"})
    assert response.status_code == 200
    assert all(
        value in response.headers["set-cookie"]
        for value in ("Secure", "HttpOnly", "SameSite=lax")
    )
    assert client.get("/api/records").status_code == 200
    assert client.get("/api/admin/accounts").status_code == 404
    token = client.cookies.get("__Host-warren-session")
    assert client.get("/api/auth/session").json()["email"] == "Shared workspace"
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.set("__Host-warren-session", token)
    assert client.get("/api/records").status_code == 401


def test_code_change_invalidates_existing_sessions(code_client, tmp_path, monkeypatch):
    client = code_client
    client.post("/api/auth/login", json={"code": "1234"})
    token = client.cookies.get("__Host-warren-session")
    monkeypatch.setenv("WARREN_ACCESS_CODE", "Client19Ab")
    with TestClient(
        create_app(tmp_path), base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as changed:
        changed.cookies.set("__Host-warren-session", token)
        assert changed.get("/api/records").status_code == 401
        assert changed.post("/api/auth/login", json={"code": "1234"}).status_code == 401
        assert (
            changed.post("/api/auth/login", json={"code": "client19ab"}).status_code
            == 401
        )
        assert (
            changed.post("/api/auth/login", json={"code": "Client19Ab"}).status_code
            == 200
        )


def test_code_origin_expiry_and_rate_limit(code_client):
    client = code_client
    assert (
        client.post(
            "/api/auth/login",
            json={"code": "1234"},
            headers={"Origin": "https://other.test"},
        ).status_code
        == 403
    )
    client.post("/api/auth/login", json={"code": "1234"})
    with client.app.state.store.database.connect(write=True) as db:
        db.execute("UPDATE code_sessions SET expires_at=0")
    assert client.get("/api/records").status_code == 401
    for _ in range(29):
        assert client.post("/api/auth/login", json={"code": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"code": "1234"}).status_code == 429


def test_code_configuration_rejects_empty_or_non_alphanumeric(code_client, monkeypatch):
    for code in ("", "abc", "code space", "x" * 129):
        monkeypatch.setenv("WARREN_ACCESS_CODE", code)
        with pytest.raises(RuntimeError, match="WARREN_ACCESS_CODE"):
            AuthConfig.from_env()
