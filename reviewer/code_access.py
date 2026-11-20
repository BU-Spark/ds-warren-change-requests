"""Shared access code with expiring, revocable server-side session tokens."""

import secrets
import time

from .accounts import digest


class CodeAccess:
    def __init__(self, database, code):
        self.database = database
        self.code = code
        self.version = digest(code)
        with database.connect(write=True) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS code_sessions (token_hash TEXT PRIMARY KEY, code_version TEXT NOT NULL, expires_at BIGINT NOT NULL)"
            )
            db.execute(
                "DELETE FROM code_sessions WHERE code_version<>? OR expires_at<=?",
                (self.version, int(time.time())),
            )

    def login(self, code):
        if not secrets.compare_digest(code.encode(), self.code.encode()):
            return None
        token = secrets.token_urlsafe(32)
        with self.database.connect(write=True) as db:
            db.execute(
                "DELETE FROM code_sessions WHERE expires_at<=?", (int(time.time()),)
            )
            db.execute(
                "INSERT INTO code_sessions VALUES (?,?,?)",
                (digest(token), self.version, int(time.time()) + 3600),
            )
        return token

    def session_email(self, token):
        if not token or len(token) > 128:
            return None
        with self.database.connect() as db:
            row = db.execute(
                "SELECT token_hash FROM code_sessions WHERE token_hash=? AND code_version=? AND expires_at>?",
                (digest(token), self.version, int(time.time())),
            ).fetchone()
        return "Shared workspace" if row else None

    def logout(self, token):
        if token:
            with self.database.connect(write=True) as db:
                db.execute(
                    "DELETE FROM code_sessions WHERE token_hash=?", (digest(token),)
                )
