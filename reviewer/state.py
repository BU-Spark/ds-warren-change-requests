"""Small local metadata store; accepted ingestion CSV and evidence remain independent."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .database import Database


class State:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "reviewer.sqlite3"
        self.database = Database(self.path)
        order_field = ", created_order BIGSERIAL" if self.database.url else ""
        with self.connect() as db:
            db.execute(
                f"CREATE TABLE IF NOT EXISTS entities (kind TEXT, id TEXT, payload TEXT NOT NULL{order_field}, PRIMARY KEY(kind,id))"
            )

    def connect(self):
        return self.database.connect()

    def get(self, kind, identifier, default=None):
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM entities WHERE kind=? AND id=?", (kind, identifier)
            ).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, kind, identifier, payload):
        with self.connect() as db:
            db.execute(
                "INSERT INTO entities(kind,id,payload) VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload",
                (kind, identifier, json.dumps(payload)),
            )
        return payload

    def put_many(self, kind, values):
        with self.connect() as db:
            db.executemany(
                "INSERT INTO entities(kind,id,payload) VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload",
                [
                    (kind, identifier, json.dumps(payload))
                    for identifier, payload in values.items()
                ],
            )

    def delete(self, kind, identifier):
        with self.connect() as db:
            db.execute("DELETE FROM entities WHERE kind=? AND id=?", (kind, identifier))

    def list(self, kind):
        order = "created_order" if self.database.url else "rowid"
        with self.connect() as db:
            return [
                json.loads(row[0])
                for row in db.execute(
                    f"SELECT payload FROM entities WHERE kind=? ORDER BY {order} DESC",
                    (kind,),
                )
            ]


def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    """Canonical fingerprint shared by review tokens and comparison snapshots."""
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
