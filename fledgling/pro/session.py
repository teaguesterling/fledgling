"""Fledgling Pro: Session state — caching and access logging.

Tracks tool usage in a SQL table and caches macro results to avoid
redundant computation within a session.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field


@dataclass
class CachedResult:
    """A cached tool output with metadata."""
    text: str
    row_count: int
    timestamp: float
    ttl: float
    file_mtimes: dict[str, float] = field(default_factory=dict)

    def age_seconds(self) -> float:
        return time.time() - self.timestamp

    def is_expired(self) -> bool:
        if self.ttl <= 0:
            return False  # session lifetime
        return time.time() - self.timestamp > self.ttl


class SessionCache:
    """In-memory cache for formatted tool output.

    Key: (tool_name, frozen_args). Value: CachedResult.
    TTL-based expiry with optional file mtime invalidation.
    """

    def __init__(self):
        self._entries: dict[tuple, CachedResult] = {}

    @staticmethod
    def _make_key(tool_name: str, arguments: dict) -> tuple:
        frozen = tuple(sorted(
            (k, v) for k, v in arguments.items() if v is not None
        ))
        return (tool_name, frozen)

    def get(self, tool_name: str, arguments: dict) -> CachedResult | None:
        key = self._make_key(tool_name, arguments)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._entries[key]
            return None
        if entry.file_mtimes and not self._files_unchanged(entry.file_mtimes):
            del self._entries[key]
            return None
        return entry

    @staticmethod
    def _files_unchanged(file_mtimes: dict[str, float]) -> bool:
        """Check whether all tracked files still have their cached mtime."""
        for path, cached_mtime in file_mtimes.items():
            try:
                if os.path.getmtime(path) != cached_mtime:
                    return False
            except OSError:
                return False  # file deleted or inaccessible
        return True

    def put(self, tool_name: str, arguments: dict,
            text: str, row_count: int, ttl: float,
            file_mtimes: dict[str, float] | None = None) -> None:
        key = self._make_key(tool_name, arguments)
        self._entries[key] = CachedResult(
            text=text,
            row_count=row_count,
            timestamp=time.time(),
            ttl=ttl,
            file_mtimes=file_mtimes or {},
        )

    def entry_count(self) -> int:
        return len(self._entries)


class AccessLog:
    """Records tool calls in a DuckDB table for session observability.

    The table is queryable via SQL, enabling pattern detection by
    downstream consumers (e.g., kibitzer).
    """

    def __init__(self, con):
        self._con = con
        con.execute("""
            CREATE TABLE IF NOT EXISTS session_access_log (
                call_id     INTEGER PRIMARY KEY,
                timestamp   DOUBLE,
                tool_name   VARCHAR,
                arguments   JSON,
                result_rows INTEGER,
                cached      BOOLEAN,
                elapsed_ms  DOUBLE
            )
        """)
        row = con.execute("SELECT COALESCE(MAX(call_id), 0) FROM session_access_log").fetchone()
        self._next_id = row[0] + 1

    def record(self, tool_name: str, arguments: dict,
               row_count: int, cached: bool, elapsed_ms: float) -> int:
        """Record a tool call. Returns the call_id."""
        call_id = self._next_id
        self._next_id += 1
        self._con.execute(
            "INSERT INTO session_access_log VALUES (?, ?, ?, ?, ?, ?, ?)",
            [call_id, time.time(), tool_name, json.dumps(arguments),
             row_count, cached, elapsed_ms],
        )
        return call_id

    def summary(self) -> dict:
        """Return aggregate stats for the session."""
        row = self._con.execute("""
            SELECT count(*) AS total_calls,
                   count(*) FILTER (WHERE cached) AS cached_calls
            FROM session_access_log
        """).fetchone()
        return {"total_calls": row[0], "cached_calls": row[1]}
