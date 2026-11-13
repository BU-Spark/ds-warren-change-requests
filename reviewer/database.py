"""Transactional PostgreSQL storage with a SQLite option for local development."""

import os
import sqlite3
from contextlib import contextmanager


class Connection:
    def __init__(self, connection, postgres):
        self.raw = connection
        self.postgres = postgres
        self.for_update = " FOR UPDATE" if postgres else ""

    def execute(self, sql, parameters=()):
        return self.raw.execute(
            sql.replace("?", "%s") if self.postgres else sql, parameters
        )

    def executemany(self, sql, rows):
        if self.postgres:
            with self.raw.cursor() as cursor:
                cursor.executemany(sql.replace("?", "%s"), rows)
        else:
            self.raw.executemany(sql, rows)


class Database:
    def __init__(self, path):
        self.path = path
        self.url = os.getenv("DATABASE_URL", "").strip()
        if self.url and not self.url.startswith(("postgres://", "postgresql://")):
            raise RuntimeError("DATABASE_URL must be a PostgreSQL connection URL.")

    @contextmanager
    def connect(self, *, write=False):
        if self.url:
            import psycopg

            with psycopg.connect(self.url, connect_timeout=10) as connection:
                yield Connection(connection, True)
        else:
            connection = sqlite3.connect(self.path, timeout=30)
            try:
                with connection:
                    if write:
                        connection.execute("BEGIN IMMEDIATE")
                    yield Connection(connection, False)
            finally:
                connection.close()
