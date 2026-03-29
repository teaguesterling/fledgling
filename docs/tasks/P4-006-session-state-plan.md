# Session State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add session caching and access logging to fledgling-pro so repeated tool calls return cached results and all tool usage is queryable.

**Architecture:** Python dict-based cache wraps macro calls in server.py's tool pipeline. Access log writes to a SQL table in the pro DuckDB connection. A new `fledgling://session` resource exposes the log. No changes to fledgling core.

**Tech Stack:** Python (dataclasses, time), DuckDB (in-memory table), FastMCP (resource registration)

---

### Task 1: AccessLog — data model and write path

**Files:**
- Create: `fledgling/pro/session.py`
- Create: `tests/test_pro_session.py`

- [ ] **Step 1: Write failing test for AccessLog**

```python
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
        rows = con.execute("SELECT * FROM session_access_log").fetchall()
        assert len(rows) == 1
        assert rows[0][2] == "read_source"  # tool_name
        assert rows[0][4] == 10             # result_rows
        assert rows[0][5] is False          # cached

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_session.py", "-v"])`
Expected: FAIL — `fledgling.pro.session` does not exist

- [ ] **Step 3: Implement AccessLog**

Create `fledgling/pro/session.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_session.py::TestAccessLog", "-v"])`
Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add fledgling/pro/session.py tests/test_pro_session.py
git commit -m "feat(session): add AccessLog with SQL table storage"
```

---

### Task 2: SessionCache — basic TTL caching

**Files:**
- Modify: `fledgling/pro/session.py`
- Modify: `tests/test_pro_session.py`

- [ ] **Step 1: Write failing tests for SessionCache**

Append to `tests/test_pro_session.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_session.py::TestSessionCache", "-v"])`
Expected: FAIL — `SessionCache` not defined

- [ ] **Step 3: Implement SessionCache**

Add to `fledgling/pro/session.py`:

```python
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
        return entry

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_session.py::TestSessionCache", "-v"])`
Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add fledgling/pro/session.py tests/test_pro_session.py
git commit -m "feat(session): add SessionCache with TTL expiry"
```

---

### Task 3: SessionCache — file mtime invalidation

**Files:**
- Modify: `fledgling/pro/session.py`
- Modify: `tests/test_pro_session.py`

- [ ] **Step 1: Write failing tests for mtime invalidation**

Append to `tests/test_pro_session.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_session.py::TestCacheMtimeInvalidation", "-v"])`
Expected: FAIL — `get()` doesn't check mtimes yet

- [ ] **Step 3: Add mtime checking to SessionCache.get()**

Update the `get` method in `fledgling/pro/session.py`:

```python
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
```

Add `import os` at the top of `session.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_session.py::TestCacheMtimeInvalidation", "-v"])`
Expected: all 4 tests PASS

- [ ] **Step 5: Run all session tests**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_session.py", "-v"])`
Expected: all tests PASS (AccessLog + SessionCache + mtime)

- [ ] **Step 6: Commit**

```bash
git add fledgling/pro/session.py tests/test_pro_session.py
git commit -m "feat(session): add file mtime invalidation to cache"
```

---

### Task 4: Integrate cache + log into server.py tool pipeline

**Files:**
- Modify: `fledgling/pro/server.py`
- Modify: `tests/test_pro_session.py`

- [ ] **Step 1: Write failing integration tests**

Append to `tests/test_pro_session.py`:

```python
import asyncio


try:
    import fastmcp  # noqa: F401
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False

requires_fastmcp = pytest.mark.skipif(
    not HAS_FASTMCP, reason="fastmcp not installed"
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_session.py::TestServerCacheIntegration", "-v"])`
Expected: FAIL — no cache integration in server yet

- [ ] **Step 3: Integrate cache and log into server.py**

Add cache policy constant and modify `create_server()` and `_register_tool()` in `server.py`:

At the top of `server.py`, add import:
```python
from fledgling.pro.session import AccessLog, SessionCache, CachedResult
```

Add cache policy after the existing constants:
```python
# ── Session cache policy ───────────────────────────────────────────
# Tools listed here cache their results. TTL in seconds; 0 = session lifetime.

CACHE_POLICY: dict[str, dict] = {
    "project_overview": {"ttl": 0, "keys": ("root",)},
    "find_definitions": {"ttl": 300, "keys": ("file_pattern", "name_pattern")},
    "code_structure":   {"ttl": 300, "keys": ("file_pattern",)},
    "read_source":      {"ttl": 300, "keys": ("file_path", "lines", "match"),
                         "mtime_params": ("file_path",)},
    "read_context":     {"ttl": 300, "keys": ("file_path", "center_line", "ctx"),
                         "mtime_params": ("file_path",)},
    "doc_outline":      {"ttl": 0, "keys": ("file_pattern", "search")},
    "recent_changes":   {"ttl": 30, "keys": ("n",)},
    "working_tree_status": {"ttl": 10, "keys": ()},
}
```

In `create_server()`, after creating `mcp`, initialize session state:
```python
    cache = SessionCache()
    access_log = AccessLog(con._con)
    mcp._session_cache = cache
    mcp._access_log = access_log
```

Pass `cache` and `access_log` to `_register_tool()`:
```python
    _register_tool(mcp, con, macro_name, params, defaults, cache, access_log)
```

Update `_register_tool()` signature and wrap `tool_fn`:
```python
def _register_tool(
    mcp: FastMCP,
    con: Connection,
    macro_name: str,
    params: list[str],
    defaults: ProjectDefaults,
    cache: SessionCache,
    access_log: AccessLog,
):
```

Inside `tool_fn`, wrap the existing logic. The full updated `tool_fn` body:

```python
    async def tool_fn(**kwargs) -> str:
        import time as _time
        t0 = _time.time()

        # Apply smart defaults for None params
        kwargs = apply_defaults(defaults, macro_name, kwargs)

        # Extract truncation parameter before passing to SQL macro
        max_rows = default_limit
        if limit_param and limit_param in kwargs:
            val = kwargs.pop(limit_param)
            if val is not None:
                try:
                    max_rows = int(val)
                except (TypeError, ValueError):
                    pass

        # Skip truncation if user provided a range-narrowing parameter
        if range_params and any(kwargs.get(p) is not None for p in range_params):
            max_rows = 0

        # Remove None values; coerce known numeric params to int.
        filtered = {}
        for k, v in kwargs.items():
            if v is None:
                continue
            if k in _NUMERIC_PARAMS and isinstance(v, str) and v.isdigit():
                filtered[k] = int(v)
            else:
                filtered[k] = v

        # Build cache args (include limit param since it affects output)
        cache_args = dict(filtered)
        if limit_param and max_rows != default_limit:
            cache_args[limit_param] = max_rows

        # Check cache
        policy = CACHE_POLICY.get(macro_name)
        if policy is not None:
            cached = cache.get(macro_name, cache_args)
            if cached is not None:
                elapsed = (_time.time() - t0) * 1000
                access_log.record(macro_name, filtered, cached.row_count,
                                  cached=True, elapsed_ms=elapsed)
                age = int(cached.age_seconds())
                return f"(cached — same as {age}s ago)\n{cached.text}"

        # Call macro
        macro = getattr(con, macro_name)
        try:
            rel = macro(**filtered)
            cols = rel.columns
            rows = rel.fetchall()
        except Exception as e:
            etype = type(e).__name__
            if etype in ("IOException", "InvalidInputException"):
                elapsed = (_time.time() - t0) * 1000
                access_log.record(macro_name, filtered, 0,
                                  cached=False, elapsed_ms=elapsed)
                return "(no results)"
            raise
        if not rows:
            elapsed = (_time.time() - t0) * 1000
            access_log.record(macro_name, filtered, 0,
                              cached=False, elapsed_ms=elapsed)
            return "(no results)"

        row_count = len(rows)

        # Apply truncation
        omission = None
        if limit_param and max_rows > 0:
            rows, omission = _truncate_rows(rows, max_rows, macro_name)

        # Format output
        if is_text:
            if len(cols) == 1:
                lines = [str(r[0]) for r in rows]
            elif "line_number" in cols and "content" in cols:
                ln_idx = cols.index("line_number")
                ct_idx = cols.index("content")
                lines = [f"{r[ln_idx]:4d}  {r[ct_idx]}" for r in rows]
            else:
                lines = []
                for row in rows:
                    parts = [str(v) for v in row if v is not None]
                    lines.append("  ".join(parts))
            if omission:
                lines.insert(_HEAD_TAIL, omission)
            text = "\n".join(lines)
        else:
            text = _format_markdown_table(cols, rows)
            if omission:
                md_lines = text.split("\n")
                insert_at = 2 + _HEAD_TAIL
                md_lines.insert(insert_at, omission)
                text = "\n".join(md_lines)

        elapsed = (_time.time() - t0) * 1000

        # Store in cache
        if policy is not None:
            file_mtimes = {}
            for p in policy.get("mtime_params", ()):
                path = filtered.get(p)
                if path:
                    try:
                        file_mtimes[path] = os.path.getmtime(path)
                    except OSError:
                        pass
            cache.put(macro_name, cache_args, text, row_count,
                      ttl=policy["ttl"], file_mtimes=file_mtimes)

        # Log access
        access_log.record(macro_name, filtered, row_count,
                          cached=False, elapsed_ms=elapsed)

        return text
```

- [ ] **Step 4: Run integration tests**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_session.py::TestServerCacheIntegration", "-v"])`
Expected: all 4 tests PASS

- [ ] **Step 5: Run ALL existing tests to check for regressions**

Run: `mcp__blq_mcp__run(command="test", extra=["-v"])`
Expected: all tests PASS. The cache/log wrapping should be transparent.

- [ ] **Step 6: Commit**

```bash
git add fledgling/pro/server.py tests/test_pro_session.py
git commit -m "feat(session): integrate cache and access log into server pipeline"
```

---

### Task 5: Access log integration tests

**Files:**
- Modify: `tests/test_pro_session.py`

- [ ] **Step 1: Write failing tests for access log in server**

Append to `tests/test_pro_session.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_session.py::TestServerAccessLogIntegration", "-v"])`
Expected: PASS (implementation already done in Task 4)

- [ ] **Step 3: Commit**

```bash
git add tests/test_pro_session.py
git commit -m "test(session): add access log integration tests"
```

---

### Task 6: Session resource

**Files:**
- Modify: `fledgling/pro/server.py`
- Modify: `tests/test_pro_session.py`

- [ ] **Step 1: Write failing tests for session resource**

Append to `tests/test_pro_session.py`:

```python
from fastmcp import Client


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@requires_fastmcp
class TestSessionResource:
    """fledgling://session exposes access log summary."""

    @pytest.fixture(scope="class")
    def mcp(self):
        from fledgling.pro.server import create_server
        return create_server(root=PROJECT_ROOT, init=False)

    def test_resource_listed(self, mcp):
        async def _list():
            async with Client(mcp) as client:
                return await client.list_resources()
        resources = _run_async(_list())
        uris = [str(r.uri) for r in resources]
        assert "fledgling://session" in uris

    def test_resource_returns_content(self, mcp):
        # Make a call first so there's something to report
        _run_async(mcp.call_tool("project_overview", {}))

        async def _read():
            async with Client(mcp) as client:
                result = await client.read_resource("fledgling://session")
                return result[0].text
        text = _run_async(_read())
        assert "tool calls" in text.lower() or "calls" in text.lower()

    def test_resource_shows_cache_stats(self, mcp):
        # Prime cache then hit it
        _run_async(mcp.call_tool("project_overview", {}))
        _run_async(mcp.call_tool("project_overview", {}))

        async def _read():
            async with Client(mcp) as client:
                result = await client.read_resource("fledgling://session")
                return result[0].text
        text = _run_async(_read())
        assert "cache" in text.lower()

    def test_resource_shows_recent_calls(self, mcp):
        _run_async(mcp.call_tool("project_overview", {}))

        async def _read():
            async with Client(mcp) as client:
                result = await client.read_resource("fledgling://session")
                return result[0].text
        text = _run_async(_read())
        assert "project_overview" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_session.py::TestSessionResource", "-v"])`
Expected: FAIL — `fledgling://session` resource doesn't exist

- [ ] **Step 3: Add session resource to server.py**

In `create_server()`, after the existing resources (after `git_resource`), add:

```python
    @mcp.resource("fledgling://session",
                  name="session",
                  description="Session access log — tool call history, cache stats.")
    def session_resource() -> str:
        summary = access_log.summary()
        total = summary["total_calls"]
        cached = summary["cached_calls"]
        pct = int(100 * cached / total) if total > 0 else 0
        entries = cache.entry_count()

        sections = []
        sections.append(
            f"Session: {total} tool calls, {cached} cached ({pct}%)\n"
            f"Cache: {entries} entries"
        )

        # Recent calls table
        recent = con._con.execute("""
            SELECT call_id, tool_name, arguments, result_rows, cached, elapsed_ms
            FROM session_access_log
            ORDER BY call_id DESC
            LIMIT 20
        """).fetchall()

        if recent:
            sections.append("\n## Recent Calls\n")
            cols = ["#", "tool", "args", "rows", "cached", "ms"]
            rows = []
            for r in recent:
                args_str = r[2] if len(str(r[2])) < 60 else str(r[2])[:57] + "..."
                rows.append((
                    r[0], r[1], args_str, r[3],
                    "yes" if r[4] else "no",
                    f"{r[5]:.0f}",
                ))
            sections.append(_format_markdown_table(cols, rows))

        return "\n".join(sections)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_session.py::TestSessionResource", "-v"])`
Expected: all 4 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `mcp__blq_mcp__run(command="test", extra=["-v"])`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add fledgling/pro/server.py tests/test_pro_session.py
git commit -m "feat(session): add fledgling://session resource"
```

---

### Task 7: Update resource tests and final verification

**Files:**
- Modify: `tests/test_pro_resources.py`

- [ ] **Step 1: Update resource discovery test**

In `tests/test_pro_resources.py`, add `"fledgling://session"` to `RESOURCE_URIS`:

```python
RESOURCE_URIS = [
    "fledgling://project",
    "fledgling://diagnostics",
    "fledgling://docs",
    "fledgling://git",
    "fledgling://session",
]
```

Update the count assertion:
```python
    def test_resource_count(self, resource_list):
        assert len(resource_list) == 5
```

- [ ] **Step 2: Run resource tests**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_resources.py", "-v"])`
Expected: all tests PASS

- [ ] **Step 3: Run full test suite one final time**

Run: `mcp__blq_mcp__run(command="test", extra=["-v"])`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_pro_resources.py
git commit -m "test(session): update resource discovery for fledgling://session"
```
