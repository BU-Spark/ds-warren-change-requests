"""Keep synthetic tests independent of real account configuration."""

import pytest


@pytest.fixture(autouse=True)
def isolated_auth_environment(monkeypatch):
    for name in (
        "WARREN_SUPABASE_URL",
        "WARREN_SUPABASE_PUBLISHABLE_KEY",
        "WARREN_PUBLIC_URL",
        "WARREN_ALLOWED_EMAILS",
        "RAILWAY_ENVIRONMENT_ID",
        "RAILWAY_PUBLIC_DOMAIN",
        "DATABASE_URL",
        "WARREN_DATA_DIR",
        "RAILWAY_VOLUME_MOUNT_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WARREN_ALLOW_UNAUTHENTICATED", "1")
