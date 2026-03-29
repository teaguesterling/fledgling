"""Tests for fledgling-pro session state: caching and access logging."""

import os
import time
import pytest
import duckdb

try:
    import fastmcp  # noqa: F401
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False

requires_fastmcp = pytest.mark.skipif(
    not HAS_FASTMCP, reason="fastmcp not installed"
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


import os


class TestCacheMtimeInvalidation:
    """Cache entries for single-file tools invalidate on file modification."""

    @pytest.fixture
    def cache(self):
        from fledgling.pro.session import SessionCache
        return SessionCache()

    def test_valid_when_file_unchanged(self, cache, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("original")
        mtime = os.path.getmtime(str(f))
        cache.put("read_source", {"file_path": str(f)},
                  text="original", row_count=1, ttl=300,
                  file_mtimes={str(f): mtime})
        result = cache.get("read_source", {"file_path": str(f)})
        assert result is not None
        assert result.text == "original"

    def test_invalidated_when_file_modified(self, cache, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("original")
        mtime = os.path.getmtime(str(f))
        cache.put("read_source", {"file_path": str(f)},
                  text="original", row_count=1, ttl=300,
                  file_mtimes={str(f): mtime})
        # Modify the file
        time.sleep(0.05)  # ensure mtime changes
        f.write_text("modified")
        result = cache.get("read_source", {"file_path": str(f)})
        assert result is None

    def test_no_mtimes_skips_check(self, cache):
        """Glob-pattern tools have no file_mtimes — TTL only."""
        cache.put("find_definitions", {"file_pattern": "**/*.py"},
                  text="results", row_count=10, ttl=300)
        result = cache.get("find_definitions", {"file_pattern": "**/*.py"})
        assert result is not None

    def test_missing_file_invalidates(self, cache, tmp_path):
        f = tmp_path / "gone.py"
        f.write_text("exists")
        mtime = os.path.getmtime(str(f))
        cache.put("read_source", {"file_path": str(f)},
                  text="exists", row_count=1, ttl=300,
                  file_mtimes={str(f): mtime})
        f.unlink()
        result = cache.get("read_source", {"file_path": str(f)})
        assert result is None


def _text(result) -> str:
    """Extract text from a FastMCP ToolResult."""
    return result.content[0].text


@requires_fastmcp
class TestServerCacheIntegration:
    """Cache and access log are wired into the server tool pipeline."""

    @pytest.fixture(scope="class")
    def mcp(self):
        from fledgling.pro.server import create_server
        return create_server(root=PROJECT_ROOT, init=False)

    @pytest.mark.anyio
    async def test_repeated_call_returns_cached(self, mcp):
        result1 = _text(await mcp.call_tool("project_overview", {}))
        result2 = _text(await mcp.call_tool("project_overview", {}))
        assert "(cached" in result2
        # The actual content should still be present
        assert "python" in result2.lower() or "sql" in result2.lower()

    @pytest.mark.anyio
    async def test_cached_note_shows_age(self, mcp):
        # First call primes the cache
        await mcp.call_tool("project_overview", {})
        result = _text(await mcp.call_tool("project_overview", {}))
        # Should contain "(cached — same as Ns ago)" with some number
        assert "(cached" in result
        assert "ago)" in result

    @pytest.mark.anyio
    async def test_different_args_not_cached(self, mcp):
        r1 = _text(await mcp.call_tool("read_source", {
            "file_path": f"{PROJECT_ROOT}/fledgling/pro/__init__.py",
        }))
        r2 = _text(await mcp.call_tool("read_source", {
            "file_path": f"{PROJECT_ROOT}/fledgling/__init__.py",
        }))
        assert "(cached" not in r1
        assert "(cached" not in r2

    @pytest.mark.anyio
    async def test_uncacheable_tool_never_cached(self, mcp):
        """Tools not in CACHE_POLICY are never cached."""
        r1 = _text(await mcp.call_tool("help", {}))
        r2 = _text(await mcp.call_tool("help", {}))
        assert "(cached" not in r2


@requires_fastmcp
class TestServerAccessLogIntegration:
    """Access log records calls made through the server."""

    @pytest.fixture
    def mcp_with_log(self):
        """Fresh server per test so log is clean."""
        from fledgling.pro.server import create_server
        return create_server(root=PROJECT_ROOT, init=False)

    @pytest.mark.anyio
    async def test_tool_call_logged(self, mcp_with_log):
        mcp = mcp_with_log
        await mcp.call_tool("project_overview", {})
        summary = mcp._access_log.summary()
        assert summary["total_calls"] >= 1

    @pytest.mark.anyio
    async def test_cached_call_logged_as_cached(self, mcp_with_log):
        mcp = mcp_with_log
        await mcp.call_tool("project_overview", {})
        await mcp.call_tool("project_overview", {})
        summary = mcp._access_log.summary()
        assert summary["total_calls"] >= 2
        assert summary["cached_calls"] >= 1

    @pytest.mark.anyio
    async def test_no_results_still_logged(self, mcp_with_log):
        mcp = mcp_with_log
        await mcp.call_tool("read_source", {
            "file_path": f"{PROJECT_ROOT}/nonexistent_file_xyz.py",
        })
        summary = mcp._access_log.summary()
        assert summary["total_calls"] >= 1


import asyncio


@requires_fastmcp
class TestSessionResource:
    """fledgling://session exposes access log summary."""

    @pytest.fixture(scope="class")
    def mcp(self):
        from fledgling.pro.server import create_server
        return create_server(root=PROJECT_ROOT, init=False)

    def test_resource_listed(self, mcp):
        if HAS_FASTMCP:
            from fastmcp import Client

        async def _list():
            async with Client(mcp) as client:
                return await client.list_resources()

        loop = asyncio.new_event_loop()
        try:
            resources = loop.run_until_complete(_list())
        finally:
            loop.close()
        uris = [str(r.uri) for r in resources]
        assert "fledgling://session" in uris

    def test_resource_returns_content(self, mcp):
        if HAS_FASTMCP:
            from fastmcp import Client

        async def _call_tool():
            await mcp.call_tool("project_overview", {})

        async def _read():
            async with Client(mcp) as client:
                result = await client.read_resource("fledgling://session")
                return result[0].text

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_call_tool())
            text = loop.run_until_complete(_read())
        finally:
            loop.close()
        assert "tool calls" in text.lower() or "calls" in text.lower()

    def test_resource_shows_cache_stats(self, mcp):
        if HAS_FASTMCP:
            from fastmcp import Client

        async def _calls():
            await mcp.call_tool("project_overview", {})
            await mcp.call_tool("project_overview", {})

        async def _read():
            async with Client(mcp) as client:
                result = await client.read_resource("fledgling://session")
                return result[0].text

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_calls())
            text = loop.run_until_complete(_read())
        finally:
            loop.close()
        assert "cache" in text.lower()

    def test_resource_shows_recent_calls(self, mcp):
        if HAS_FASTMCP:
            from fastmcp import Client

        async def _call_tool():
            await mcp.call_tool("project_overview", {})

        async def _read():
            async with Client(mcp) as client:
                result = await client.read_resource("fledgling://session")
                return result[0].text

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_call_tool())
            text = loop.run_until_complete(_read())
        finally:
            loop.close()
        assert "project_overview" in text
