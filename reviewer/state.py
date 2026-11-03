"""Small local metadata store; accepted ingestion CSV and evidence remain independent."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class State:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "reviewer.sqlite3"
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS entities (kind TEXT, id TEXT, payload TEXT NOT NULL, PRIMARY KEY(kind,id))"
            )

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def get(self, kind, identifier, default=None):
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM entities WHERE kind=? AND id=?", (kind, identifier)
            ).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, kind, identifier, payload):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO entities VALUES (?,?,?)",
                (kind, identifier, json.dumps(payload)),
            )
        return payload

    def put_many(self, kind, values):
        with self.connect() as db:
            db.executemany(
                "INSERT OR REPLACE INTO entities VALUES (?,?,?)",
                [
                    (kind, identifier, json.dumps(payload))
                    for identifier, payload in values.items()
                ],
            )

    def delete(self, kind, identifier):
        with self.connect() as db:
            db.execute("DELETE FROM entities WHERE kind=? AND id=?", (kind, identifier))

    def list(self, kind):
        with self.connect() as db:
            return [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT payload FROM entities WHERE kind=? ORDER BY rowid DESC",
                    (kind,),
                )
            ]


def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    """Canonical fingerprint shared by review tokens and comparison snapshots."""
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
