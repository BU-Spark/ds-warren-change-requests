"""Disposable account-enabled UI test server; no real account or document data."""

import os
import tempfile
from pathlib import Path

import uvicorn

from reviewer.api import create_app

if __name__ == "__main__":
    for name in (
        "DATABASE_URL",
        "WARREN_DATA_DIR",
        "WARREN_SUPABASE_URL",
        "WARREN_SUPABASE_PUBLISHABLE_KEY",
        "RAILWAY_ENVIRONMENT_ID",
        "RAILWAY_PUBLIC_DOMAIN",
    ):
        os.environ.pop(name, None)
    os.environ["WARREN_AUTH_MODE"] = "accounts"
    os.environ["WARREN_PUBLIC_URL"] = "http://127.0.0.1:8001"
    with tempfile.TemporaryDirectory(prefix="warren-auth-browser-") as folder:
        app = create_app(Path(folder))
        accounts = app.state.accounts
        token = accounts.invite("admin@example.test", admin=True)
        accounts.set_password(
            accounts.confirm(token, "invite"), "synthetic-admin-password"
        )
        uvicorn.run(app, host="127.0.0.1", port=8001, proxy_headers=False)
