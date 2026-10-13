"""Persistence behind a small interface (swap SQLite for Postgres, etc. without touching services)."""
from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from typing import Optional

from .domain import Attempt, AttemptStatus, NotFoundError


class AttemptRepository(ABC):
    @abstractmethod
    def save(self, attempt: Attempt) -> None: ...

    @abstractmethod
    def get(self, attempt_id: str) -> Attempt: ...

    @abstractmethod
    def list(self, learner_id: str, problem_id: Optional[str] = None) -> list: ...

    @abstractmethod
    def list_by_status(self, status: AttemptStatus) -> list: ...


class InMemoryRepository(AttemptRepository):
    def __init__(self):
        self._data: dict[str, dict] = {}
        self._lock = threading.Lock()

    def save(self, attempt):
        with self._lock:
            self._data[attempt.id] = attempt.to_dict()

    def get(self, attempt_id):
        with self._lock:
            d = self._data.get(attempt_id)
        if d is None:
            raise NotFoundError(f"Attempt '{attempt_id}' not found.")
        return Attempt.from_dict(d)

    def list(self, learner_id, problem_id=None):
        with self._lock:
            rows = [d for d in self._data.values() if d["learner_id"] == learner_id
                    and (problem_id is None or d["problem_id"] == problem_id)]
        return sorted((Attempt.from_dict(d) for d in rows), key=lambda a: (a.created_at, a.number))

    def list_by_status(self, status):
        with self._lock:
            return [Attempt.from_dict(d) for d in self._data.values() if d["status"] == status.value]


class SQLiteRepository(AttemptRepository):
    def __init__(self, path: str = ":memory:"):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, learner_id TEXT, problem_id TEXT,"
                " status TEXT, created_at TEXT, number INTEGER, data TEXT NOT NULL)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS ix_attempts_learner ON attempts(learner_id, problem_id)")
            self._conn.commit()

    def save(self, a):
        with self._lock:
            self._conn.execute(
                "INSERT INTO attempts(id, learner_id, problem_id, status, created_at, number, data) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, data=excluded.data",
                (a.id, a.learner_id, a.problem_id, a.status.value, a.created_at, a.number, json.dumps(a.to_dict())))
            self._conn.commit()

    def get(self, attempt_id):
        with self._lock:
            row = self._conn.execute("SELECT data FROM attempts WHERE id=?", (attempt_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Attempt '{attempt_id}' not found.")
        return Attempt.from_dict(json.loads(row[0]))

    def list(self, learner_id, problem_id=None):
        q, args = "SELECT data FROM attempts WHERE learner_id=?", [learner_id]
        if problem_id:
            q, args = q + " AND problem_id=?", args + [problem_id]
        with self._lock:
            rows = self._conn.execute(q + " ORDER BY created_at, number", args).fetchall()
        return [Attempt.from_dict(json.loads(r[0])) for r in rows]

    def list_by_status(self, status):
        with self._lock:
            rows = self._conn.execute("SELECT data FROM attempts WHERE status=?", (status.value,)).fetchall()
        return [Attempt.from_dict(json.loads(r[0])) for r in rows]
