"""Optional real PostgreSQL integration; isolated schema, never real app data."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from reviewer.api import create_app
from reviewer.state import State


@pytest.fixture
def postgres(tmp_path, monkeypatch):
    url = os.getenv("WARREN_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set WARREN_TEST_POSTGRES_URL to a disposable PostgreSQL server.")
    import psycopg
    from psycopg import sql

    schema = "warren_test_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    separator = "&" if "?" in url else "?"
    monkeypatch.setenv(
        "DATABASE_URL", url + separator + "options=" + quote("-csearch_path=" + schema)
    )
    try:
        yield tmp_path
    finally:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


def test_postgres_state_upserts_atomic_bulk_and_restarts(postgres):
    state = State(postgres / "reviewer")
    state.put("session", "first", {"status": "one"})
    state.put("session", "first", {"status": "two"})
    state.put_many(
        "session", {"first": {"status": "three"}, "second": {"status": "four"}}
    )
    state = State(postgres / "different-local-directory")
    assert len(state.list("session")) == 2
    assert state.get("session", "first") == {"status": "three"}
    state.delete("session", "first")
    assert state.get("session", "first") is None


def test_postgres_auth_api_and_atomic_redemption(postgres, monkeypatch):
    origin = "https://review.example.test"
    monkeypatch.setenv("WARREN_PUBLIC_URL", origin)
    monkeypatch.setenv("WARREN_DATA_DIR", str(postgres))
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(postgres))
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "synthetic")
    with TestClient(
        create_app(postgres), base_url=origin, headers={"Origin": origin}
    ) as client:
        accounts = client.app.state.accounts
        email, password = "admin@example.test", "synthetic-password"
        token = accounts.invite(email, admin=True)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(lambda _: accounts.confirm(token, "invite"), range(2))
            )
        assert sum(result is not None for result in results) == 1
        setup = next(result for result in results if result)
        assert accounts.set_password(setup, password)
        assert client.get("/api/records").status_code == 401
        assert (
            client.post(
                "/api/auth/login", json={"email": email, "password": password}
            ).status_code
            == 200
        )
        session = client.cookies.get("__Host-warren-session")
        assert client.get("/api/admin/accounts").status_code == 200
        assert (
            client.get(
                "/api/health", headers={"Host": "healthcheck.railway.app"}
            ).status_code
            == 200
        )
        assert client.post("/api/auth/logout").status_code == 200
        assert accounts.session_email(session) is None
        token = accounts.recovery(email)
        setup = accounts.confirm(token, "recovery")
        assert accounts.set_password(setup, "new-synthetic-password")
        assert accounts.login(email, password) is None
        accounts.disable(email)
        assert accounts.login(email, "new-synthetic-password") is None
