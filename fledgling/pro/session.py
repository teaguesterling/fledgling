"""Fledgling Pro: Session state — caching and access logging.

Tracks tool usage in a SQL table and caches macro results to avoid
redundant computation within a session.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field


class AccessLog:
    """Records tool calls in a DuckDB table for session observability.

    The table is queryable via SQL, enabling pattern detection by
    downstream consumers (e.g., kibitzer).
    """

    def __init__(self, con):
        self._con = con
        self._next_id = 1
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
