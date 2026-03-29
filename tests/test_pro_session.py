"""Tests for fledgling-pro session state: caching and access logging."""

import time
import pytest
import duckdb


class TestAccessLog:
    """Access log records tool calls in a SQL table."""

    @pytest.fixture
    def con(self):
        conn = duckdb.connect(":memory:")
        yield conn
        conn.close()

    @pytest.fixture
    def log(self, con):
        from fledgling.pro.session import AccessLog
        return AccessLog(con)

    def test_log_creates_table(self, con, log):
        tables = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'session_access_log'"
        ).fetchall()
        assert len(tables) == 1

    def test_log_entry(self, log, con):
        log.record("read_source", {"file_path": "foo.py"}, row_count=10,
                    cached=False, elapsed_ms=23.5)
        row = con.execute(
            "SELECT tool_name, result_rows, cached "
            "FROM session_access_log"
        ).fetchone()
        assert row[0] == "read_source"
        assert row[1] == 10
        assert row[2] is False

    def test_log_increments_call_id(self, log, con):
        log.record("read_source", {"file_path": "a.py"}, 5, False, 10.0)
        log.record("find_definitions", {"file_pattern": "**/*.py"}, 20, False, 50.0)
        ids = con.execute(
            "SELECT call_id FROM session_access_log ORDER BY call_id"
        ).fetchall()
        assert [r[0] for r in ids] == [1, 2]

    def test_log_records_cached_flag(self, log, con):
        log.record("read_source", {"file_path": "a.py"}, 5, True, 0.1)
        cached = con.execute(
            "SELECT cached FROM session_access_log WHERE call_id = 1"
        ).fetchone()[0]
        assert cached is True

    def test_log_summary(self, log):
        log.record("read_source", {"file_path": "a.py"}, 5, False, 10.0)
        log.record("read_source", {"file_path": "a.py"}, 5, True, 0.1)
        log.record("find_definitions", {"file_pattern": "**/*.py"}, 20, False, 50.0)
        summary = log.summary()
        assert summary["total_calls"] == 3
        assert summary["cached_calls"] == 1
