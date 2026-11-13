"""Run with python -m reviewer after building the frontend."""

import os

import uvicorn


def main():
    hosted = bool(
        os.getenv("RAILWAY_ENVIRONMENT_ID") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
    )
    uvicorn.run(
        "reviewer.api:create_app",
        factory=True,
        host="0.0.0.0" if hosted else "127.0.0.1",
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
