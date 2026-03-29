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


from unittest.mock import patch


class TestSessionCache:
    """Session cache stores and retrieves formatted tool output."""

    @pytest.fixture
    def cache(self):
        from fledgling.pro.session import SessionCache
        return SessionCache()

    def test_miss_returns_none(self, cache):
        assert cache.get("read_source", {"file_path": "foo.py"}) is None

    def test_put_and_get(self, cache):
        cache.put("read_source", {"file_path": "foo.py"},
                  text="line 1\nline 2", row_count=2, ttl=300)
        result = cache.get("read_source", {"file_path": "foo.py"})
        assert result is not None
        assert result.text == "line 1\nline 2"
        assert result.row_count == 2

    def test_different_args_different_entries(self, cache):
        cache.put("read_source", {"file_path": "a.py"},
                  text="aaa", row_count=1, ttl=300)
        cache.put("read_source", {"file_path": "b.py"},
                  text="bbb", row_count=1, ttl=300)
        assert cache.get("read_source", {"file_path": "a.py"}).text == "aaa"
        assert cache.get("read_source", {"file_path": "b.py"}).text == "bbb"

    def test_ttl_expiry(self, cache):
        cache.put("read_source", {"file_path": "foo.py"},
                  text="old", row_count=1, ttl=10)
        with patch("fledgling.pro.session.time") as mock_time:
            mock_time.time.return_value = time.time() + 11
            assert cache.get("read_source", {"file_path": "foo.py"}) is None

    def test_ttl_not_expired(self, cache):
        cache.put("read_source", {"file_path": "foo.py"},
                  text="fresh", row_count=1, ttl=300)
        result = cache.get("read_source", {"file_path": "foo.py"})
        assert result is not None
        assert result.text == "fresh"

    def test_cache_key_includes_all_args(self, cache):
        """max_lines affects output, so same tool+path with different limits = different entries."""
        cache.put("read_source", {"file_path": "foo.py", "max_lines": 50},
                  text="truncated", row_count=50, ttl=300)
        cache.put("read_source", {"file_path": "foo.py", "max_lines": 200},
                  text="full", row_count=200, ttl=300)
        assert cache.get("read_source", {"file_path": "foo.py", "max_lines": 50}).text == "truncated"
        assert cache.get("read_source", {"file_path": "foo.py", "max_lines": 200}).text == "full"

    def test_entry_count(self, cache):
        cache.put("read_source", {"file_path": "a.py"}, "a", 1, 300)
        cache.put("read_source", {"file_path": "b.py"}, "b", 1, 300)
        assert cache.entry_count() == 2

    def test_cache_age_seconds(self, cache):
        cache.put("read_source", {"file_path": "a.py"}, "a", 1, 300)
        result = cache.get("read_source", {"file_path": "a.py"})
        assert result.age_seconds() < 1.0
