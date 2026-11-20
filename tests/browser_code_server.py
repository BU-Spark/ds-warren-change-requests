"""Disposable shared-code UI test server; never uses production data."""

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
        "WARREN_AUTH_MODE",
        "WARREN_ACCESS_CODE",
    ):
        os.environ.pop(name, None)
    os.environ["WARREN_PUBLIC_URL"] = "http://127.0.0.1:8002"
    with tempfile.TemporaryDirectory(prefix="warren-code-browser-") as folder:
        uvicorn.run(
            create_app(Path(folder)), host="127.0.0.1", port=8002, proxy_headers=False
        )
