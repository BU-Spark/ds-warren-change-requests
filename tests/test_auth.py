"""Synthetic account lifecycle, access control, and revocation regressions."""

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from reviewer import accounts as account_module
from reviewer import auth
from reviewer.api import create_app

ORIGIN = "https://review.example.test"
EMAIL = "reviewer@example.test"
ADMIN = "admin@example.test"
PASSWORD = "sample-password"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("WARREN_PUBLIC_URL", ORIGIN)
    app = create_app(tmp_path)
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        yield client, app.state.accounts


def activate(accounts, email=EMAIL, *, admin=False):
    link = accounts.invite(email, admin=admin)
    setup = accounts.confirm(link, "invite")
    assert accounts.set_password(setup, PASSWORD)


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_invitation_and_password_setup_are_required(workspace):
    client, accounts = workspace
    assert login(client).status_code == 401
    token = accounts.invite(EMAIL)
    assert login(client).status_code == 401
    reply = client.post("/api/auth/confirm", json={"kind": "invite", "token": token})
    assert reply.status_code == 200
    assert "HttpOnly" in reply.headers["set-cookie"]
    assert "Secure" in reply.headers["set-cookie"]
    assert client.get("/api/records").status_code == 401
    assert (
        client.post("/api/auth/reset", json={"password": PASSWORD}).status_code == 200
    )
    assert client.get("/api/records").status_code == 401
    assert login(client).json() == {"email": EMAIL, "role": "reviewer"}
    assert client.get("/api/records").status_code == 200


def test_protect_data_downloads_and_admin_routes(workspace):
    client, _ = workspace
    for path in (
        "/api/sessions",
        "/api/records",
        "/api/reference",
        "/api/classification-map",
        "/api/sessions/sample/pages/1",
        "/api/documents/sample/pages/1",
        "/api/sessions/sample/evidence",
        "/api/checks/sample/differences.csv",
        "/api/reference/sample/source",
        "/api/admin/accounts",
        "/api/documents",
        "/api/documents/sample/deletion-preview",
        "/api/documents/sample/source-info",
        "/api/sessions/sample/deletion-preview",
    ):
        assert client.get(path).status_code == 401
    assert client.post("/api/sessions").status_code == 401
    assert (
        client.request(
            "DELETE", "/api/documents/sample", json={"confirmation": "a" * 64}
        ).status_code
        == 401
    )
    assert client.get("/api/health").status_code == 200


def test_logout_revokes_copied_session_token(workspace):
    client, accounts = workspace
    activate(accounts)
    response = login(client)
    assert response.status_code == 200
    assert "SameSite=lax" in response.headers["set-cookie"]
    token = client.cookies.get("__Host-warren-session")
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.set("__Host-warren-session", token)
    assert client.get("/api/records").status_code == 401


def test_no_public_signup_or_recovery_email_endpoints(workspace):
    client, accounts = workspace
    activate(accounts)
    assert login(client).status_code == 200
    for path in ("/api/auth/signup", "/api/auth/forgot"):
        assert (
            client.post(
                path, json={"email": "unknown@example.test", "password": PASSWORD}
            ).status_code
            == 404
        )
    assert len(accounts.list_accounts()) == 1


def test_reviewer_cannot_manage_accounts_or_promote_self(workspace):
    client, accounts = workspace
    activate(accounts)
    login(client)
    assert client.get("/api/admin/accounts").status_code == 403
    assert (
        client.post(
            "/api/admin/accounts",
            json={"action": "invite", "email": ADMIN, "admin": True},
        ).status_code
        == 403
    )


def test_admin_can_invite_reviewers_and_disable_access(workspace):
    client, accounts = workspace
    activate(accounts, ADMIN, admin=True)
    assert login(client, ADMIN).json()["role"] == "admin"
    reply = client.post(
        "/api/admin/accounts", json={"action": "invite", "email": EMAIL, "admin": True}
    )
    assert reply.status_code == 200
    link = parse_qs(urlsplit(reply.json()["link"]).fragment)
    assert link["type"] == ["invite"]
    assert not urlsplit(reply.json()["link"]).query
    token = link["token"][0]
    assert accounts.set_password(accounts.confirm(token, "invite"), PASSWORD)
    assert accounts.role(EMAIL) == "reviewer"
    assert {a["email"] for a in client.get("/api/admin/accounts").json()} == {
        ADMIN,
        EMAIL,
    }
    reviewer_session = accounts.login(EMAIL, PASSWORD)
    assert (
        client.post(
            "/api/admin/accounts", json={"action": "disable", "email": EMAIL}
        ).status_code
        == 200
    )
    assert accounts.session_email(reviewer_session) is None
    assert accounts.login(EMAIL, PASSWORD) is None
    assert accounts.recovery(EMAIL) is None
    # Web admins cannot accidentally disable the admin account that bootstraps access.
    assert (
        client.post(
            "/api/admin/accounts", json={"action": "disable", "email": ADMIN}
        ).status_code
        == 400
    )
    accounts.invite("pending-admin@example.test", admin=True)
    assert (
        client.post(
            "/api/admin/accounts",
            json={"action": "disable", "email": "pending-admin@example.test"},
        ).status_code
        == 400
    )


def test_recovery_requires_operator_and_revokes_sessions(workspace):
    client, accounts = workspace
    activate(accounts)
    login(client)
    old_session = client.cookies.get("__Host-warren-session")
    token = accounts.recovery(EMAIL)
    assert accounts.confirm(token, "invite") is None
    assert (
        client.post(
            "/api/auth/confirm", json={"kind": "recovery", "token": token}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/reset", json={"password": "replacement-password"}
        ).status_code
        == 200
    )
    assert accounts.session_email(old_session) is None
    assert accounts.confirm(token, "recovery") is None
    assert (
        client.post("/api/auth/reset", json={"password": PASSWORD}).status_code == 400
    )
    assert login(client).status_code == 401
    assert login(client, password="replacement-password").status_code == 200


def test_expired_links_and_sessions_are_rejected(workspace):
    client, accounts = workspace
    token = accounts.invite(EMAIL)
    with accounts.database.connect(write=True) as db:
        db.execute("UPDATE account_tokens SET expires_at=0")
    assert accounts.confirm(token, "invite") is None
    activate(accounts)
    login(client)
    with accounts.database.connect(write=True) as db:
        db.execute("UPDATE account_tokens SET expires_at=0")
    assert client.get("/api/records").status_code == 401


def test_tokens_and_passwords_are_hashed_at_rest(workspace):
    _, accounts = workspace
    activate(accounts)
    session = accounts.login(EMAIL, PASSWORD)
    with accounts.database.connect() as db:
        stored = db.execute("SELECT password_hash FROM accounts").fetchone()[0]
        tokens = db.execute("SELECT token_hash FROM account_tokens").fetchall()
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored
    assert tokens == [(account_module.digest(session),)]
    assert session not in tokens[0][0]


def test_simultaneous_redemption_and_password_change_are_single_use(workspace):
    _, accounts = workspace
    token = accounts.invite(EMAIL)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _: accounts.confirm(token, "invite"), range(2))
        )
    assert sum(result is not None for result in results) == 1
    setup = next(result for result in results if result)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _: accounts.set_password(setup, PASSWORD), range(2))
        )
    assert results.count(True) == 1


def test_cross_origin_missing_origin_and_forged_cookie(workspace):
    client, _ = workspace
    assert (
        client.request(
            "DELETE",
            "/api/documents/sample",
            json={"confirmation": "a" * 64},
            headers={"Origin": "https://evil.test"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            headers={"Origin": "https://evil.test"},
        ).status_code
        == 403
    )
    del client.headers["Origin"]
    assert login(client).status_code == 403
    client.cookies.set("__Host-warren-session", "forged-token")
    assert client.get("/api/records").status_code == 401
    assert client.get("/api/auth/session").json() == {
        "enabled": True,
        "email": None,
        "mode": "accounts",
        "role": None,
    }


def test_auth_validation_does_not_echo_passwords_and_frames_are_blocked(workspace):
    client, _ = workspace
    response = client.post("/api/auth/reset", json={"password": "short"})
    assert response.status_code == 422
    assert "short" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_auth_attempt_budget(workspace, monkeypatch):
    from reviewer import api

    clock = [100.0]
    monkeypatch.setattr(api, "monotonic", lambda: clock[0])
    client, _ = workspace
    for _ in range(30):
        assert login(client).status_code == 401
    reply = login(client)
    assert reply.status_code == 429
    assert reply.headers["retry-after"] == "60"
    clock[0] += 61
    assert login(client).status_code == 401


def test_local_http_auth_and_restart(tmp_path, monkeypatch):
    origin = "http://127.0.0.1:8000"
    monkeypatch.setenv("WARREN_PUBLIC_URL", origin)
    with TestClient(
        create_app(tmp_path), base_url=origin, headers={"Origin": origin}
    ) as client:
        activate(client.app.state.accounts)
        reply = login(client)
        assert "HttpOnly" in reply.headers["set-cookie"]
        token = client.cookies.get("warren-session")
        assert client.get("/api/records").status_code == 200
        assert (
            client.get("/api/records", headers={"Host": "other.test"}).status_code
            == 400
        )
    with TestClient(
        create_app(tmp_path), base_url=origin, headers={"Origin": origin}
    ) as client:
        client.cookies.set("warren-session", token)
        assert client.get("/api/records").status_code == 200


def test_local_startup_requires_explicit_auth_choice(tmp_path, monkeypatch):
    monkeypatch.delenv("WARREN_ALLOW_UNAUTHENTICATED")
    with pytest.raises(RuntimeError, match="authentication is required"):
        create_app(tmp_path)
    monkeypatch.setenv("WARREN_ALLOW_UNAUTHENTICATED", "1")
    assert auth.AuthConfig.from_env() is None


def test_railway_requires_auth_database_and_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "synthetic")
    with pytest.raises(RuntimeError, match="authentication is required"):
        create_app(tmp_path)
    monkeypatch.setenv("WARREN_PUBLIC_URL", "http://127.0.0.1:8000")
    with pytest.raises(RuntimeError, match="HTTPS"):
        create_app(tmp_path)
    monkeypatch.setenv("WARREN_PUBLIC_URL", ORIGIN)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/test")
    monkeypatch.setenv("WARREN_DATA_DIR", str(tmp_path))
    with pytest.raises(RuntimeError, match="Attach an app volume"):
        auth.AuthConfig.from_env()
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))
    assert auth.AuthConfig.from_env().secure


def test_obsolete_provider_settings_fail_closed(monkeypatch):
    monkeypatch.setenv("WARREN_SUPABASE_URL", "https://obsolete.supabase.co")
    with pytest.raises(RuntimeError, match="obsolete"):
        auth.AuthConfig.from_env()


def test_operator_bootstrap_uses_same_database(tmp_path, monkeypatch, capsys):
    from reviewer.manage_accounts import main

    monkeypatch.setenv("WARREN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WARREN_PUBLIC_URL", ORIGIN)
    monkeypatch.setattr("sys.argv", ["manage_accounts", "invite", ADMIN, "--admin"])
    main()
    link = capsys.readouterr().out.splitlines()[-1]
    token = parse_qs(urlsplit(link).fragment)["token"][0]
    with TestClient(
        create_app(tmp_path), base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as client:
        accounts = client.app.state.accounts
        assert accounts.set_password(accounts.confirm(token, "invite"), PASSWORD)
        assert login(client, ADMIN).json()["role"] == "admin"
