"""Invite-only accounts and hashed, revocable, single-use authentication tokens."""

import hashlib
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

HASHER = PasswordHasher()
# Verify unknown accounts too, so password work is not skipped for unknown emails.
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    def __init__(self, database):
        self.database = database
        with database.connect(write=True) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS accounts (email TEXT PRIMARY KEY, password_hash TEXT NOT NULL DEFAULT '', activated INTEGER NOT NULL DEFAULT 0, disabled INTEGER NOT NULL DEFAULT 0, role TEXT NOT NULL DEFAULT 'reviewer')"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS account_tokens (token_hash TEXT PRIMARY KEY, email TEXT NOT NULL REFERENCES accounts(email), kind TEXT NOT NULL, expires_at BIGINT NOT NULL)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS account_tokens_email ON account_tokens(email)"
            )

    def _token(self, db, email, kind, seconds):
        token = secrets.token_urlsafe(32)
        db.execute(
            "DELETE FROM account_tokens WHERE expires_at <= ?", (int(time.time()),)
        )
        db.execute(
            "INSERT INTO account_tokens VALUES (?,?,?,?)",
            (digest(token), email, kind, int(time.time()) + seconds),
        )
        return token

    def invite(self, email, *, admin=False):
        with self.database.connect(write=True) as db:
            db.execute(
                "INSERT INTO accounts(email) VALUES (?) ON CONFLICT(email) DO NOTHING",
                (email,),
            )
            row = db.execute(
                "SELECT activated,disabled FROM accounts WHERE email=?" + db.for_update,
                (email,),
            ).fetchone()
            if row[0] or row[1]:
                raise ValueError(
                    "This account is already active or disabled. Use recovery or enable it explicitly."
                )
            db.execute("DELETE FROM account_tokens WHERE email=?", (email,))
            if admin:
                db.execute("UPDATE accounts SET role='admin' WHERE email=?", (email,))
            return self._token(db, email, "invite", 24 * 3600)

    def login(self, email, password):
        with self.database.connect() as db:
            row = db.execute(
                "SELECT password_hash,activated,disabled FROM accounts WHERE email=?",
                (email,),
            ).fetchone()
        try:
            valid = HASHER.verify(row[0] if row and row[0] else DUMMY_HASH, password)
        except (VerificationError, InvalidHashError):
            valid = False
        if not row or not valid or not row[1] or row[2]:
            return None
        with self.database.connect(write=True) as db:
            # A concurrent password change/disable must invalidate this login attempt.
            current = db.execute(
                "SELECT password_hash,activated,disabled FROM accounts WHERE email=?"
                + db.for_update,
                (email,),
            ).fetchone()
            if current != row:
                return None
            if HASHER.check_needs_rehash(row[0]):
                db.execute(
                    "UPDATE accounts SET password_hash=? WHERE email=?",
                    (HASHER.hash(password), email),
                )
            return self._token(db, email, "session", 3600)

    def session_email(self, token):
        if not token or len(token) > 128:
            return None
        with self.database.connect() as db:
            row = db.execute(
                "SELECT a.email FROM account_tokens t JOIN accounts a ON a.email=t.email WHERE t.token_hash=? AND t.kind='session' AND t.expires_at>? AND a.activated=1 AND a.disabled=0",
                (digest(token), int(time.time())),
            ).fetchone()
            return row[0] if row else None

    def recovery(self, email):
        with self.database.connect(write=True) as db:
            row = db.execute(
                "SELECT activated,disabled FROM accounts WHERE email=?" + db.for_update,
                (email,),
            ).fetchone()
            if not row or not row[0] or row[1]:
                return None
            db.execute(
                "DELETE FROM account_tokens WHERE email=? AND kind='recovery'", (email,)
            )
            return self._token(db, email, "recovery", 15 * 60)

    def confirm(self, token, kind):
        with self.database.connect(write=True) as db:
            # DELETE RETURNING makes redemption atomic across simultaneous requests.
            row = db.execute(
                "DELETE FROM account_tokens WHERE token_hash=? AND kind=? AND expires_at>? RETURNING email",
                (digest(token), kind, int(time.time())),
            ).fetchone()
            if not row:
                return None
            email = row[0]
            account = db.execute(
                "SELECT disabled FROM accounts WHERE email=?", (email,)
            ).fetchone()
            if account[0]:
                return None
            return self._token(db, email, "setup", 600)

    def set_password(self, token, password):
        password_hash = HASHER.hash(password)
        with self.database.connect(write=True) as db:
            row = db.execute(
                "DELETE FROM account_tokens WHERE token_hash=? AND kind='setup' AND expires_at>? RETURNING email",
                (digest(token), int(time.time())),
            ).fetchone()
            if not row:
                return False
            email = row[0]
            result = db.execute(
                "UPDATE accounts SET password_hash=?,activated=1 WHERE email=? AND disabled=0",
                (password_hash, email),
            )
            db.execute("DELETE FROM account_tokens WHERE email=?", (email,))
            return result.rowcount == 1

    def logout(self, token):
        if token:
            with self.database.connect(write=True) as db:
                db.execute(
                    "DELETE FROM account_tokens WHERE token_hash=?", (digest(token),)
                )

    def disable(self, email):
        with self.database.connect(write=True) as db:
            db.execute("UPDATE accounts SET disabled=1 WHERE email=?", (email,))
            db.execute("DELETE FROM account_tokens WHERE email=?", (email,))

    def role(self, email):
        with self.database.connect() as db:
            row = db.execute(
                "SELECT role FROM accounts WHERE email=? AND disabled=0",
                (email,),
            ).fetchone()
            return row[0] if row else None

    def list_accounts(self):
        with self.database.connect() as db:
            return [
                dict(zip(("email", "activated", "disabled", "role"), row))
                for row in db.execute(
                    "SELECT email,activated,disabled,role FROM accounts ORDER BY email"
                ).fetchall()
            ]

    def promote(self, email):
        with self.database.connect(write=True) as db:
            result = db.execute(
                "UPDATE accounts SET role='admin' WHERE email=? AND disabled=0",
                (email,),
            )
            if result.rowcount != 1:
                raise ValueError("No enabled account exists for that address.")
