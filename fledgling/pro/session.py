"""Fledgling Pro: Session state — caching and access logging.

Tracks tool usage in a SQL table and caches macro results to avoid
redundant computation within a session.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field


SESSION_LIFETIME = 0  # TTL value meaning "never expires within this session"


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
        if self.ttl == SESSION_LIFETIME:
            return False
        return time.time() - self.timestamp > self.ttl


class SessionCache:
    """In-memory cache for formatted tool output.

    Key: (tool_name, frozen_args). Value: CachedResult.
    TTL-based expiry with optional file mtime invalidation.

    Cache keys strip None values, so ``{"a": 1}`` and ``{"a": 1, "b": None}``
    are treated as the same key. This matches the server pipeline which filters
    Nones before building cache_args.
    """

    def __init__(self):
        self._entries: dict[tuple, CachedResult] = {}

    @staticmethod
    def _make_key(tool_name: str, arguments: dict) -> tuple:
        def _freeze(v):
            """Make a value hashable for use as a cache key."""
            if isinstance(v, (str, int, float, bool, type(None))):
                return v
            return json.dumps(v, sort_keys=True)

        frozen = tuple(sorted(
            (k, _freeze(v)) for k, v in arguments.items() if v is not None
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
        """Count of active (non-expired, files unchanged) cache entries."""
        active = 0
        stale_keys = []
        for key, entry in self._entries.items():
            if entry.is_expired():
                stale_keys.append(key)
            elif entry.file_mtimes and not self._files_unchanged(entry.file_mtimes):
                stale_keys.append(key)
            else:
                active += 1
        for key in stale_keys:
            del self._entries[key]
        return active


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

    def recent_calls(self, limit: int = 20) -> list[tuple]:
        """Return the most recent tool calls, newest first."""
        return self._con.execute(
            "SELECT call_id, tool_name, arguments, result_rows, cached, elapsed_ms "
            "FROM session_access_log ORDER BY call_id DESC LIMIT ?",
            [limit],
        ).fetchall()
