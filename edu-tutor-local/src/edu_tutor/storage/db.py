from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .timing import record_timing


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid4().hex


class Store:
    """Short, independent SQLite transactions preserve data across restarts."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.local = self.root / ".local"
        self.local.mkdir(parents=True, exist_ok=True)
        self.path = self.local / "tutor.sqlite3"
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,
                payload TEXT NOT NULL, FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE);
            CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,document_id TEXT NOT NULL,payload TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS photos(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS lessons(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evaluation_reviews(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        started = time.perf_counter()
        db = sqlite3.connect(self.path, timeout=15)
        record_timing("db_connect", started)
        started = time.perf_counter()
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        record_timing("db_connection_setup", started)
        try:
            yield db
            started = time.perf_counter()
            try:
                db.commit()
            finally:
                record_timing("db_commit", started)
        except BaseException:
            started = time.perf_counter()
            try:
                db.rollback()
            finally:
                record_timing("db_rollback", started)
            raise
        finally:
            started = time.perf_counter()
            db.close()
            record_timing("db_close", started)

    @staticmethod
    def _table(table):
        if table not in {"sessions", "messages", "jobs", "documents", "chunks", "photos", "lessons", "datasets", "audit", "evaluation_reviews"}:
            raise ValueError("Invalid store table")
        return table

    def get(self, table: str, ident: str):
        with self.connect() as db:
            started = time.perf_counter()
            row = db.execute(f"SELECT payload FROM {self._table(table)} WHERE id=?", (ident,)).fetchone()
            record_timing("db_read", started)
        started = time.perf_counter()
        value = json.loads(row[0]) if row else None
        record_timing("json_decode", started)
        return value

    def list(self, table: str):
        with self.connect() as db:
            started = time.perf_counter()
            rows = db.execute(f"SELECT payload FROM {self._table(table)} ORDER BY rowid").fetchall()
            record_timing("db_read", started)
        started = time.perf_counter()
        values = [json.loads(row[0]) for row in rows]
        record_timing("json_decode", started)
        return values

    def put(self, table: str, value: dict):
        table = self._table(table)
        extra = {"messages": "session_id", "chunks": "document_id"}.get(table)
        started = time.perf_counter()
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False)
        record_timing("json_encode", started)
        with self.connect() as db:
            started = time.perf_counter()
            if extra:
                db.execute(f"INSERT INTO {table}(id,{extra},payload) VALUES(?,?,?) "
                           f"ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                           (value["id"], value[extra], payload))
            else:
                db.execute(f"INSERT INTO {table}(id,payload) VALUES(?,?) "
                           "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (value["id"], payload))
            record_timing("db_write", started)
        return value

    def delete(self, table: str, ident: str):
        with self.connect() as db:
            db.execute(f"DELETE FROM {self._table(table)} WHERE id=?", (ident,))

    def record(self, action: str, entity_id: str, **details):
        self.put("audit", {"id": new_id(), "action": action, "entity_id": entity_id,
                           "created_at": utcnow(), **details})

    def file(self, category: str, ident: str, suffix: str = "") -> Path:
        if category not in {"uploads", "photos", "assets", "datasets"} or not ident.isalnum():
            raise ValueError("Invalid local file identifier")
        if suffix not in {"", ".txt", ".md", ".pdf", ".png", ".wav", ".jsonl"}:
            raise ValueError("Invalid file suffix")
        parent = self.local / category
        parent.mkdir(exist_ok=True)
        path = (parent / (ident + suffix)).resolve()
        if path.parent != parent.resolve():
            raise ValueError("Unsafe local file path")
        return path
