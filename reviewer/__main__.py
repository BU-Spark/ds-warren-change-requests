"""Run with python -m reviewer after building the frontend."""

import uvicorn


def main():
    uvicorn.run("reviewer.api:create_app", factory=True, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
