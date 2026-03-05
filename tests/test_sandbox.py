"""Tests for path resolution and filesystem sandboxing.

Verifies that resolve() and _resolve() correctly handle relative/absolute
paths, that _resolve() works in MCP context (where getvariable returns NULL),
and that DuckDB's allowed_directories blocks access outside the project root.
"""

import duckdb
import pytest

from conftest import PROJECT_ROOT, CONFTEST_PATH, load_sql, create_resolve_macros


@pytest.fixture
def sandboxed():
    """Connection with sandbox.sql loaded and filesystem locked down."""
    con = duckdb.connect(":memory:")
    con.execute("LOAD read_lines")
    con.execute(f"SET VARIABLE session_root = '{PROJECT_ROOT}'")
    create_resolve_macros(con)
    load_sql(con, "sandbox.sql")
    # Lock down filesystem
    con.execute(f"SET allowed_directories = ['{PROJECT_ROOT}']")
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    yield con
    con.close()


@pytest.fixture
def unsandboxed():
    """Connection with sandbox.sql loaded but NO filesystem lockdown."""
    con = duckdb.connect(":memory:")
    con.execute("LOAD read_lines")
    con.execute(f"SET VARIABLE session_root = '{PROJECT_ROOT}'")
    create_resolve_macros(con)
    load_sql(con, "sandbox.sql")
    yield con
    con.close()


class TestResolve:
    def test_relative_path_prepends_root(self, unsandboxed):
        result = unsandboxed.execute(
            "SELECT resolve('README.md')"
        ).fetchone()[0]
        assert result == f"{PROJECT_ROOT}/README.md"

    def test_absolute_path_passes_through(self, unsandboxed):
        result = unsandboxed.execute(
            "SELECT resolve('/etc/hostname')"
        ).fetchone()[0]
        assert result == "/etc/hostname"

    def test_null_returns_null(self, unsandboxed):
        result = unsandboxed.execute(
            "SELECT resolve(NULL)"
        ).fetchone()[0]
        assert result is None

    def test_nested_relative_path(self, unsandboxed):
        result = unsandboxed.execute(
            "SELECT resolve('sql/source.sql')"
        ).fetchone()[0]
        assert result == f"{PROJECT_ROOT}/sql/source.sql"

    def test_traversal_preserves_literal(self, unsandboxed):
        """resolve() doesn't normalize ../ — it just prepends the root."""
        result = unsandboxed.execute(
            "SELECT resolve('../../../etc/passwd')"
        ).fetchone()[0]
        assert result == f"{PROJECT_ROOT}/../../../etc/passwd"

    def test_session_root_is_set(self, unsandboxed):
        result = unsandboxed.execute(
            "SELECT getvariable('session_root')"
        ).fetchone()[0]
        assert result == PROJECT_ROOT


class TestLiteralResolve:
    """Tests for _resolve() — literal-backed, works in MCP context."""

    def test_relative_path_prepends_root(self, unsandboxed):
        result = unsandboxed.execute(
            "SELECT _resolve('README.md')"
        ).fetchone()[0]
        assert result == f"{PROJECT_ROOT}/README.md"

    def test_absolute_path_passes_through(self, unsandboxed):
        result = unsandboxed.execute(
            "SELECT _resolve('/etc/hostname')"
        ).fetchone()[0]
        assert result == "/etc/hostname"

    def test_null_returns_null(self, unsandboxed):
        result = unsandboxed.execute(
            "SELECT _resolve(NULL)"
        ).fetchone()[0]
        assert result is None

    def test_works_when_getvariable_is_null(self, unsandboxed):
        """Simulates MCP context where getvariable('session_root') is NULL."""
        unsandboxed.execute("SET VARIABLE session_root = NULL")
        result = unsandboxed.execute(
            "SELECT _resolve('README.md')"
        ).fetchone()[0]
        assert result == f"{PROJECT_ROOT}/README.md"

    def test_session_root_returns_root(self, unsandboxed):
        result = unsandboxed.execute(
            "SELECT _session_root()"
        ).fetchone()[0]
        assert result == PROJECT_ROOT

    def test_session_root_works_when_getvariable_is_null(self, unsandboxed):
        unsandboxed.execute("SET VARIABLE session_root = NULL")
        result = unsandboxed.execute(
            "SELECT _session_root()"
        ).fetchone()[0]
        assert result == PROJECT_ROOT

    def test_coalesce_pattern_omitted_path(self, unsandboxed):
        """COALESCE(_resolve(NULL), _session_root()) returns root."""
        result = unsandboxed.execute(
            "SELECT COALESCE(_resolve(NULL), _session_root())"
        ).fetchone()[0]
        assert result == PROJECT_ROOT

    def test_coalesce_pattern_relative_path(self, unsandboxed):
        """COALESCE(_resolve('subdir'), _session_root()) resolves."""
        result = unsandboxed.execute(
            "SELECT COALESCE(_resolve('subdir'), _session_root())"
        ).fetchone()[0]
        assert result == f"{PROJECT_ROOT}/subdir"


class TestSandboxLockdown:
    def test_resolved_relative_path_allowed(self, sandboxed):
        """Files inside session_root are readable via resolve()."""
        rows = sandboxed.execute(
            "SELECT content FROM read_lines(resolve('README.md'), '1') LIMIT 1"
        ).fetchall()
        assert len(rows) == 1
        assert "fledgling" in rows[0][0].lower()

    def test_absolute_path_inside_root_allowed(self, sandboxed):
        rows = sandboxed.execute(
            "SELECT content FROM read_lines(?, '1') LIMIT 1",
            [CONFTEST_PATH],
        ).fetchall()
        assert len(rows) == 1

    def test_absolute_path_outside_root_blocked(self, sandboxed):
        with pytest.raises(duckdb.PermissionException):
            sandboxed.execute(
                "SELECT content FROM read_lines('/etc/hostname') LIMIT 1"
            )

    def test_traversal_blocked(self, sandboxed):
        with pytest.raises(duckdb.PermissionException):
            sandboxed.execute(
                "SELECT content FROM read_lines("
                "resolve('../../../etc/passwd'), '1') LIMIT 1"
            )

    def test_config_locked(self, sandboxed):
        """Cannot re-enable external access after lockdown."""
        with pytest.raises(duckdb.Error):
            sandboxed.execute("SET enable_external_access = true")

    def test_getenv_blocked(self, sandboxed):
        """getenv() is disabled after lockdown."""
        with pytest.raises(duckdb.Error):
            sandboxed.execute("SELECT getenv('HOME')")
