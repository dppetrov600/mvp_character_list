from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class SQLiteCache:
    def __init__(self, db_path: Path, ttl_seconds: int | None = 60 * 60 * 24):
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """)
            self._conn.commit()

    @staticmethod
    def _make_key(url: str, params: dict[str, Any] | None) -> str:
        payload = {"url": url, "params": params or {}}
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def get(
        self, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any] | None:
        key = self._make_key(url, params)
        with self._lock:
            row = self._conn.execute(
                "SELECT value, created_at FROM cache WHERE key = ?", (key,)
            ).fetchone()

        if not row:
            return None

        value, created_at = row
        if self.ttl_seconds is not None and (int(time.time()) - int(created_at)) > self.ttl_seconds:
            with self._lock:
                self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                self._conn.commit()
            return None

        return json.loads(value)

    def set(
        self, url: str, params: dict[str, Any] | None, payload: dict[str, Any] | list[Any]
    ) -> None:
        key = self._make_key(url, params)
        encoded = json.dumps(payload, separators=(",", ":"))
        created_at = int(time.time())
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache(key, value, created_at) VALUES(?, ?, ?)",
                (key, encoded, created_at),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
