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


class TestConnectLockdown:
    """Regression tests for issue #49.

    The shipped CLI server (duckdb -init init-fledgling-*.sql) locks the
    filesystem down at startup. The Python ``connect()`` path historically
    did not, so library users and ``python -m fledgling.pro.server`` got an
    unsandboxed connection. These tests pin the fixed behavior: connect()
    applies lockdown() by default, with an explicit ``sandbox=False``
    opt-out, and the sandbox does not lock fledgling out of its own index.
    """

    @pytest.fixture
    def project(self, tmp_path):
        """A minimal throwaway project root (so /etc et al. are outside it)."""
        (tmp_path / "hello.py").write_text("def hello():\n    return 1\n")
        (tmp_path / "README.md").write_text("# Demo\n\nA demo project.\n")
        return tmp_path

    def _connect(self, project, **kwargs):
        import fledgling
        return fledgling.connect(
            init=False,
            root=str(project),
            modules=["sandbox", "source", "code"],
            **kwargs,
        )

    def test_connect_is_sandboxed_by_default(self, project):
        con = self._connect(project)
        ext, locked = con.execute(
            "SELECT current_setting('enable_external_access'),"
            "       current_setting('lock_configuration')"
        ).fetchone()
        assert ext is False
        assert locked is True
        # And the lock is real: config cannot be re-opened.
        with pytest.raises(duckdb.Error):
            con.execute("SET enable_external_access = true")

    def test_read_outside_root_refused(self, project):
        """The original finding: read_source('/etc/hostname') must be refused."""
        con = self._connect(project)
        with pytest.raises(duckdb.Error):
            con.read_source("/etc/hostname").fetchall()

    def test_index_still_works_after_lockdown(self, project):
        """Positive guard: lockdown must not break access to the index root."""
        con = self._connect(project)
        rows = con.read_source(str(project / "hello.py")).fetchall()
        assert any("def hello" in str(r) for r in rows)
        files = con.list_files(str(project / "**/*.py")).fetchall()
        assert files
        defs = con.find_definitions(str(project / "**/*.py")).fetchall()
        assert any("hello" in str(r) for r in defs)

    def test_sandbox_opt_out_is_explicit(self, project):
        """sandbox=False is the documented escape hatch (e.g. for indexing
        arbitrary directories); it must remain available and explicit."""
        con = self._connect(project, sandbox=False)
        rows = con.execute(
            "SELECT content FROM read_lines(?, '1') LIMIT 1", [CONFTEST_PATH]
        ).fetchall()
        assert len(rows) == 1

    def test_explicit_init_file_sandboxed(self, project):
        """Mode 1 (explicit init file) also ends locked down."""
        import fledgling
        init = project / "init.sql"
        init.write_text("CREATE OR REPLACE MACRO answer() AS 42;\n")
        con = fledgling.connect(init=str(init), root=str(project))
        assert con.execute("SELECT answer()").fetchone()[0] == 42
        ext = con.execute(
            "SELECT current_setting('enable_external_access')"
        ).fetchone()[0]
        assert ext is False

    def test_readonly_reader_sandboxed(self, project):
        """A read-only cache reader must not be able to read outside files."""
        import fledgling
        (project / ".fledgling").mkdir()
        db = str(project / ".fledgling" / "cache.duckdb")
        builder = fledgling.connect(
            init=False, root=str(project), modules=["sandbox"], persist=db
        )
        builder.close()
        ro = fledgling.connect(persist=db, read_only=True, root=str(project))
        ext = ro.execute(
            "SELECT current_setting('enable_external_access')"
        ).fetchone()[0]
        assert ext is False
        with pytest.raises(duckdb.Error):
            ro.execute("SELECT content FROM read_text('/etc/hostname')").fetchall()

    def test_pro_connection_factory_sandboxed(self, project):
        """The fledgling.pro connection factory inherits the default sandbox."""
        from fledgling.pro.db import create_connection
        con = create_connection(init=False, root=str(project), modules=["sandbox"])
        ext = con.execute(
            "SELECT current_setting('enable_external_access')"
        ).fetchone()[0]
        assert ext is False

    def test_lockdown_is_idempotent(self, project):
        """Applying lockdown() to an already-locked connection is a no-op,
        not an error (init files may lock the connection themselves)."""
        import fledgling
        con = self._connect(project)
        fledgling.lockdown(con.con)
