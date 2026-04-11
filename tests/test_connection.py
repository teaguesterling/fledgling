"""Tests for fledgling.connect() Python API.

Tests all three configuration modes:
  1. Explicit init file path
  2. Auto-discover .fledgling-init.sql
  3. Load from SQL source files (init=False)

Uses the repo itself as test data (dog-fooding).
"""

import os
import duckdb
import pytest

import fledgling
from fledgling.connection import (
    _split_sql, _find_sql_dir, _execute_init_file, _DEFAULT_MODULES,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(PROJECT_ROOT, "sql")


# ── SQL splitting ────────────────────────────────────────────────────


class TestSplitSQL:
    def test_simple_statements(self):
        stmts = _split_sql("SELECT 1; SELECT 2;")
        assert stmts == ["SELECT 1", "SELECT 2"]

    def test_strips_comment_lines(self):
        sql = "-- comment\nSELECT 1;\n-- another\nSELECT 2;"
        stmts = _split_sql(sql)
        assert stmts == ["SELECT 1", "SELECT 2"]

    def test_preserves_inline_content(self):
        sql = "SELECT 'hello -- world';"
        stmts = _split_sql(sql)
        assert len(stmts) == 1
        assert "hello -- world" in stmts[0]

    def test_empty_input(self):
        assert _split_sql("") == []
        assert _split_sql("-- just a comment") == []

    def test_dot_commands_extracted(self):
        sql = ".mode csv\nSELECT 1;\n.output /dev/null"
        stmts = _split_sql(sql)
        assert ".mode csv" in stmts
        assert ".output /dev/null" in stmts
        assert "SELECT 1" in stmts

    def test_multiline_statement(self):
        sql = "CREATE TABLE t AS\n  SELECT 1 AS x,\n  2 AS y;"
        stmts = _split_sql(sql)
        assert len(stmts) == 1
        assert "CREATE TABLE" in stmts[0]


# ── SQL directory discovery ──────────────────────────────────────────


class TestFindSQLDir:
    def test_finds_sql_dir(self):
        sql_dir = _find_sql_dir()
        assert sql_dir is not None
        assert (sql_dir / "sandbox.sql").exists()
        assert (sql_dir / "source.sql").exists()


# ── Mode 1: Explicit init file ──────────────────────────────────────


class TestExplicitInit:
    """connect(init='path') executes the given init file."""

    @pytest.fixture
    def init_file(self, tmp_path):
        """Create a minimal init file for testing."""
        init = tmp_path / ".fledgling-init.sql"
        init.write_text(f"""
LOAD read_lines;
LOAD sitting_duck;
LOAD markdown;
LOAD duck_tails;
SET VARIABLE fledgling_version = '0.3.0-test';
SET VARIABLE fledgling_profile = 'test';
SET VARIABLE fledgling_modules = ['source'];
SET VARIABLE _help_path = '{os.path.join(PROJECT_ROOT, "SKILL.md")}';
CREATE OR REPLACE MACRO _resolve(p) AS
    CASE WHEN p IS NULL THEN NULL
         WHEN p[1] = '/' THEN p
         ELSE '{PROJECT_ROOT}/' || p
    END;
CREATE OR REPLACE MACRO _session_root() AS '{PROJECT_ROOT}';
""")
        # Load sandbox and source macros inline
        for f in ["sandbox.sql", "source.sql"]:
            sql = open(os.path.join(SQL_DIR, f)).read()
            lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
            init.open("a").write("\n".join(lines) + ";\n")
        return str(init)

    def test_connects_from_init(self, init_file):
        con = fledgling.connect(init=init_file)
        rows = con.execute("SELECT 1 AS x").fetchone()
        assert rows[0] == 1

    def test_macros_available(self, init_file):
        con = fledgling.connect(init=init_file)
        rows = con.execute(
            f"SELECT count(*) FROM list_files('{PROJECT_ROOT}/tests/*.py')"
        ).fetchone()
        assert rows[0] > 0

    def test_skips_dot_commands(self, tmp_path):
        """Dot commands in init file don't cause errors."""
        init = tmp_path / "test.sql"
        init.write_text("""
.headers off
.mode csv
.output /dev/null
LOAD read_lines;
.output stdout
""")
        con = fledgling.connect(init=str(init))
        # Should not error — dot commands are skipped
        rows = con.execute("SELECT 1").fetchone()
        assert rows[0] == 1

    def test_skips_mcp_server_start(self, tmp_path):
        """mcp_server_start in init file is skipped."""
        init = tmp_path / "test.sql"
        init.write_text("""
LOAD duckdb_mcp;
SELECT CASE WHEN 'stdio' <> 'none' THEN mcp_server_start('stdio', '{}') END;
""")
        con = fledgling.connect(init=str(init))
        # Should not block on stdio — mcp_server_start is skipped
        assert con.execute("SELECT 1").fetchone()[0] == 1

    def test_skips_publish_tool(self, tmp_path):
        """PRAGMA mcp_publish_tool in init file is skipped."""
        init = tmp_path / "test.sql"
        init.write_text("""
LOAD duckdb_mcp;
PRAGMA mcp_publish_tool('Test', 'test', 'SELECT 1', '{}', '[]', 'markdown');
""")
        con = fledgling.connect(init=str(init))
        assert con.execute("SELECT 1").fetchone()[0] == 1

    def test_skips_getenv(self, tmp_path):
        """Statements with getenv() are skipped (CLI-only function)."""
        init = tmp_path / "test.sql"
        init.write_text("""
SET VARIABLE session_root = COALESCE(getvariable('session_root'), getenv('PWD'));
""")
        con = fledgling.connect(init=str(init))
        # Should not error — getenv line is skipped
        # session_root is pre-set by _execute_init_file
        assert con.execute("SELECT 1").fetchone()[0] == 1


# ── Mode 2: Auto-discover init file ─────────────────────────────────


class TestAutoDiscover:
    """connect() finds .fledgling-init.sql in the project root."""

    def test_discovers_init_in_cwd(self, tmp_path, monkeypatch):
        """When .fledgling-init.sql exists in root, it's applied as overlay.

        Sources load first (sandbox + source is enough to verify), then the
        project-local init file is applied. A minimal module set is used so
        the test doesn't depend on code.sql / sitting_duck features.
        """
        init = tmp_path / ".fledgling-init.sql"
        init.write_text("SET VARIABLE overlay_marker = 'applied';\n")
        con = fledgling.connect(
            root=str(tmp_path),
            modules=["sandbox", "source"],
        )
        # Sources loaded (source module brings in list_files, etc.)
        assert con.execute("SELECT 1").fetchone()[0] == 1
        # Overlay applied after sources
        marker = con.execute("SELECT getvariable('overlay_marker')").fetchone()[0]
        assert marker == "applied"

    def test_falls_through_to_sources(self, tmp_path):
        """When no init file exists, falls through to source loading."""
        # tmp_path has no .fledgling-init.sql
        con = fledgling.connect(root=str(tmp_path), init=False, modules=["sandbox"])
        assert con.execute("SELECT 1").fetchone()[0] == 1

    def test_real_init_file(self):
        """The actual .fledgling-init.sql in the repo works."""
        init_path = os.path.join(PROJECT_ROOT, ".fledgling-init.sql")
        if not os.path.exists(init_path):
            pytest.skip("No .fledgling-init.sql in repo root")
        con = fledgling.connect(root=PROJECT_ROOT)
        rows = con.execute(
            "SELECT value FROM dr_fledgling() WHERE key = 'version'"
        ).fetchone()
        assert rows[0] is not None


# ── Mode 3: Load from SQL sources ───────────────────────────────────


class TestFromSources:
    """connect(init=False) loads from SQL source files."""

    def test_all_modules(self):
        con = fledgling.connect(init=False)
        rows = con.execute("SELECT * FROM dr_fledgling()").fetchall()
        assert len(rows) == 5

    def test_specific_modules(self):
        con = fledgling.connect(init=False, modules=["sandbox", "source"])
        rows = con.execute(
            f"SELECT count(*) FROM list_files('{PROJECT_ROOT}/tests/*.py')"
        ).fetchone()
        assert rows[0] > 0

    def test_code_module(self):
        con = fledgling.connect(init=False, modules=["sandbox", "code"])
        rows = con.execute(
            f"SELECT count(*) FROM find_definitions('{PROJECT_ROOT}/tests/conftest.py')"
        ).fetchone()
        assert rows[0] > 10

    def test_repo_module(self):
        con = fledgling.connect(init=False, modules=["sandbox", "repo"])
        rows = con.execute("SELECT count(*) FROM recent_changes(3)").fetchone()
        assert rows[0] == 3

    def test_docs_module(self):
        con = fledgling.connect(init=False, modules=["sandbox", "docs"])
        rows = con.execute(
            f"SELECT count(*) FROM doc_outline('{PROJECT_ROOT}/SKILL.md')"
        ).fetchone()
        assert rows[0] > 5

    def test_help_module(self):
        con = fledgling.connect(init=False)
        rows = con.execute("SELECT * FROM help()").fetchall()
        assert len(rows) > 5

    def test_session_root_set(self):
        con = fledgling.connect(init=False, root="/tmp/test-root")
        val = con.execute("SELECT getvariable('session_root')").fetchone()[0]
        assert val == "/tmp/test-root"

    def test_resolve_macro(self):
        con = fledgling.connect(init=False, root="/tmp/test-root")
        val = con.execute("SELECT _resolve('foo.py')").fetchone()[0]
        assert val == "/tmp/test-root/foo.py"

    def test_resolve_absolute(self):
        con = fledgling.connect(init=False, root="/tmp/test-root")
        val = con.execute("SELECT _resolve('/absolute/path.py')").fetchone()[0]
        assert val == "/absolute/path.py"

    def test_resolve_null(self):
        con = fledgling.connect(init=False, root="/tmp/test-root")
        val = con.execute("SELECT _resolve(NULL)").fetchone()[0]
        assert val is None

    def test_session_root_macro(self):
        con = fledgling.connect(init=False, root="/tmp/test-root")
        val = con.execute("SELECT _session_root()").fetchone()[0]
        assert val == "/tmp/test-root"

    def test_profile_variable(self):
        con = fledgling.connect(init=False, profile="core")
        val = con.execute("SELECT getvariable('fledgling_profile')").fetchone()[0]
        assert val == "core"

    def test_default_profile(self):
        con = fledgling.connect(init=False)
        val = con.execute("SELECT getvariable('fledgling_profile')").fetchone()[0]
        assert val == "analyst"

    def test_version_set(self):
        con = fledgling.connect(init=False)
        val = con.execute("SELECT getvariable('fledgling_version')").fetchone()[0]
        assert val == fledgling.__version__

    def test_missing_module_skipped(self):
        """Requesting a nonexistent module doesn't error."""
        con = fledgling.connect(init=False, modules=["sandbox", "nonexistent_module"])
        assert con.execute("SELECT 1").fetchone()[0] == 1


# ── Error handling ───────────────────────────────────────────────────


class TestErrors:
    def test_explicit_init_not_found(self):
        with pytest.raises(FileNotFoundError):
            fledgling.connect(init="/nonexistent/path/init.sql")

    def test_no_sources_no_init(self, tmp_path, monkeypatch):
        """When no init file and no SQL sources, raises FileNotFoundError."""
        # Patch _find_sql_dir to return None
        monkeypatch.setattr(
            "fledgling.connection._find_sql_dir", lambda: None
        )
        with pytest.raises(FileNotFoundError, match="No fledgling SQL sources"):
            fledgling.connect(root=str(tmp_path), init=False)


# ── Integration ──────────────────────────────────────────────────────


class TestIntegration:
    """End-to-end tests with real macro execution."""

    def test_find_definitions_and_callers(self):
        con = fledgling.connect(init=False)
        # Find definitions
        defs = con.execute(
            f"SELECT name FROM find_definitions('{PROJECT_ROOT}/tests/conftest.py', 'load%')"
        ).fetchall()
        names = [r[0] for r in defs]
        assert "load_sql" in names

    def test_cross_module_query(self):
        """Query combining source + code modules."""
        con = fledgling.connect(init=False)
        rows = con.execute(f"""
            SELECT f.file_path, count(*) AS def_count
            FROM find_definitions('{PROJECT_ROOT}/tests/*.py') f
            GROUP BY f.file_path
            ORDER BY def_count DESC
            LIMIT 3
        """).fetchall()
        assert len(rows) > 0
        assert rows[0][1] > 5  # conftest.py has many definitions

    def test_git_macros(self):
        con = fledgling.connect(init=False)
        rows = con.execute("SELECT hash, message FROM recent_changes(1)").fetchall()
        assert len(rows) == 1
        assert len(rows[0][0]) == 8  # short hash

    def test_multiple_connections(self):
        """Multiple independent connections work."""
        con1 = fledgling.connect(init=False, root="/tmp/a", modules=["sandbox"])
        con2 = fledgling.connect(init=False, root="/tmp/b", modules=["sandbox"])
        r1 = con1.execute("SELECT _session_root()").fetchone()[0]
        r2 = con2.execute("SELECT _session_root()").fetchone()[0]
        assert r1 == "/tmp/a"
        assert r2 == "/tmp/b"


# ── Compose helpers (Delta 4) ────────────────────────────────────────


class TestComposeHelpers:
    """Standalone building-block functions: load_extensions, set_session_root,
    load_macros, apply_local_init."""

    def test_load_extensions_default(self):
        """load_extensions() loads the default extension set."""
        raw = duckdb.connect(":memory:")
        fledgling.load_extensions(raw)
        loaded = raw.execute(
            "SELECT extension_name FROM duckdb_extensions() "
            "WHERE extension_name IN ('read_lines','sitting_duck','markdown','duck_tails') "
            "AND loaded"
        ).fetchall()
        assert len(loaded) == 4

    def test_load_extensions_custom_list(self):
        """load_extensions() accepts an explicit list."""
        raw = duckdb.connect(":memory:")
        fledgling.load_extensions(raw, extensions=["read_lines"])
        row = raw.execute(
            "SELECT loaded FROM duckdb_extensions() WHERE extension_name = 'read_lines'"
        ).fetchone()
        assert row[0] is True

    def test_set_session_root_variables(self):
        """set_session_root() sets session_root and conversations_root variables."""
        raw = duckdb.connect(":memory:")
        fledgling.set_session_root(raw, root="/tmp/custom-root")
        val = raw.execute("SELECT getvariable('session_root')").fetchone()[0]
        assert val == "/tmp/custom-root"

    def test_set_session_root_macros(self):
        """set_session_root() bakes _resolve and _session_root macros."""
        raw = duckdb.connect(":memory:")
        fledgling.set_session_root(raw, root="/tmp/baked-root")
        assert raw.execute("SELECT _session_root()").fetchone()[0] == "/tmp/baked-root"
        assert raw.execute("SELECT _resolve('foo.py')").fetchone()[0] == "/tmp/baked-root/foo.py"
        assert raw.execute("SELECT _resolve('/abs.py')").fetchone()[0] == "/abs.py"
        assert raw.execute("SELECT _resolve(NULL)").fetchone()[0] is None

    def test_load_macros_subset(self):
        """load_macros() loads the requested modules only."""
        raw = duckdb.connect(":memory:")
        fledgling.load_extensions(raw, extensions=["read_lines"])
        fledgling.set_session_root(raw, root=PROJECT_ROOT)
        fledgling.load_macros(raw, modules=["sandbox", "source"])
        # source.sql brings list_files
        count = raw.execute(
            f"SELECT count(*) FROM list_files('{PROJECT_ROOT}/tests/*.py')"
        ).fetchone()[0]
        assert count > 0

    def test_load_macros_missing_sql_dir_errors(self, monkeypatch):
        """load_macros() raises FileNotFoundError when sql_dir is not discoverable."""
        monkeypatch.setattr(
            "fledgling.connection._find_sql_dir", lambda: None
        )
        raw = duckdb.connect(":memory:")
        with pytest.raises(FileNotFoundError, match="No fledgling SQL sources"):
            fledgling.load_macros(raw)

    def test_apply_local_init_returns_false_when_missing(self, tmp_path):
        """apply_local_init() returns False when no init file exists."""
        raw = duckdb.connect(":memory:")
        result = fledgling.apply_local_init(raw, root=str(tmp_path))
        assert result is False

    def test_apply_local_init_returns_true_when_applied(self, tmp_path):
        """apply_local_init() returns True and executes the overlay when present."""
        init = tmp_path / ".fledgling-init.sql"
        init.write_text("SET VARIABLE overlay_test = 'ran';\n")
        raw = duckdb.connect(":memory:")
        result = fledgling.apply_local_init(raw, root=str(tmp_path))
        assert result is True
        val = raw.execute("SELECT getvariable('overlay_test')").fetchone()[0]
        assert val == "ran"

    def test_apply_local_init_explicit_path(self, tmp_path):
        """apply_local_init() accepts an explicit init_path."""
        init = tmp_path / "custom-init.sql"
        init.write_text("SET VARIABLE custom_marker = 'x';\n")
        raw = duckdb.connect(":memory:")
        result = fledgling.apply_local_init(
            raw, root=str(tmp_path), init_path=str(init)
        )
        assert result is True
        assert raw.execute("SELECT getvariable('custom_marker')").fetchone()[0] == "x"


# ── configure() mid-level verb (Delta 5) ─────────────────────────────


class TestConfigure:
    """fledgling.configure() applies configuration to an existing connection."""

    def test_configure_basic(self, tmp_path):
        """configure() loads extensions, macros, and sets variables."""
        raw = duckdb.connect(":memory:")
        fledgling.configure(
            raw,
            root=str(tmp_path),
            modules=["sandbox", "source"],
        )
        assert raw.execute("SELECT getvariable('session_root')").fetchone()[0] == str(tmp_path)
        assert raw.execute("SELECT _session_root()").fetchone()[0] == str(tmp_path)
        # list_files is available from source module
        count = raw.execute(
            f"SELECT count(*) FROM list_files('{PROJECT_ROOT}/tests/*.py')"
        ).fetchone()[0]
        assert count > 0

    def test_configure_overlay_enabled(self, tmp_path):
        """configure(overlay=True) applies .fledgling-init.sql after sources."""
        init = tmp_path / ".fledgling-init.sql"
        init.write_text("SET VARIABLE overlay_flag = 'yes';\n")
        raw = duckdb.connect(":memory:")
        fledgling.configure(
            raw,
            root=str(tmp_path),
            modules=["sandbox", "source"],
            overlay=True,
        )
        assert raw.execute("SELECT getvariable('overlay_flag')").fetchone()[0] == "yes"

    def test_configure_overlay_disabled(self, tmp_path):
        """configure(overlay=False) does not apply project init file."""
        init = tmp_path / ".fledgling-init.sql"
        init.write_text("SET VARIABLE overlay_flag = 'should-not-run';\n")
        raw = duckdb.connect(":memory:")
        fledgling.configure(
            raw,
            root=str(tmp_path),
            modules=["sandbox", "source"],
            overlay=False,
        )
        val = raw.execute("SELECT getvariable('overlay_flag')").fetchone()[0]
        assert val is None

    def test_configure_profile_variable(self, tmp_path):
        """configure() writes the profile into the session variable."""
        raw = duckdb.connect(":memory:")
        fledgling.configure(
            raw,
            root=str(tmp_path),
            profile="core",
            modules=["sandbox"],
        )
        val = raw.execute("SELECT getvariable('fledgling_profile')").fetchone()[0]
        assert val == "core"

    def test_configure_extensions_false(self, tmp_path):
        """configure(extensions=False) skips extension loading."""
        raw = duckdb.connect(":memory:")
        fledgling.load_extensions(raw, extensions=["read_lines"])
        # extensions=False: should not re-load (the sandbox module has no
        # extension deps, so this combination is valid)
        fledgling.configure(
            raw,
            root=str(tmp_path),
            modules=["sandbox"],
            extensions=False,
        )
        assert raw.execute("SELECT _session_root()").fetchone()[0] == str(tmp_path)


# ── attach() (Delta 3) ───────────────────────────────────────────────


class TestAttach:
    """fledgling.attach() configures an existing DuckDBPyConnection."""

    def test_attach_returns_connection_proxy(self, tmp_path):
        """attach() returns a Connection proxy wrapping the given connection."""
        raw = duckdb.connect(":memory:")
        con = fledgling.attach(
            raw,
            root=str(tmp_path),
            modules=["sandbox", "source"],
        )
        assert isinstance(con, fledgling.Connection)
        assert con._con is raw

    def test_attach_preserves_existing_state(self):
        """attach() does not clobber existing tables on the connection."""
        raw = duckdb.connect(":memory:")
        raw.execute("CREATE TABLE pre_existing (x INT)")
        raw.execute("INSERT INTO pre_existing VALUES (42)")
        fledgling.attach(
            raw,
            modules=["sandbox"],
            overlay=False,
        )
        val = raw.execute("SELECT x FROM pre_existing").fetchone()[0]
        assert val == 42

    def test_attach_applies_overlay(self, tmp_path):
        """attach() applies .fledgling-init.sql overlay when present."""
        init = tmp_path / ".fledgling-init.sql"
        init.write_text("SET VARIABLE attach_overlay = 'ok';\n")
        raw = duckdb.connect(":memory:")
        fledgling.attach(
            raw,
            root=str(tmp_path),
            modules=["sandbox", "source"],
        )
        val = raw.execute("SELECT getvariable('attach_overlay')").fetchone()[0]
        assert val == "ok"


# ── lockdown() (Delta 3) ─────────────────────────────────────────────


class TestLockdown:
    """fledgling.lockdown() applies filesystem and config lockdown."""

    def test_lockdown_sets_allowed_dirs_from_session_root(self, tmp_path):
        """lockdown() with no allowed_dirs reads session_root from the connection."""
        raw = duckdb.connect(":memory:")
        fledgling.configure(
            raw,
            root=str(tmp_path),
            modules=["sandbox"],
        )
        fledgling.lockdown(raw, lock_config=False)
        # DuckDB returns allowed_directories as a LIST with trailing-slash
        # normalization on paths and scheme flattening ('git://' → 'git:/').
        row = raw.execute("SELECT current_setting('allowed_directories')").fetchone()
        dirs = row[0]
        assert any(str(tmp_path) in d for d in dirs), f"expected tmp_path in {dirs}"
        assert any("git:" in d for d in dirs), f"expected git scheme in {dirs}"

    def test_lockdown_explicit_dirs(self, tmp_path):
        """lockdown() accepts an explicit allowed_dirs list."""
        raw = duckdb.connect(":memory:")
        fledgling.configure(
            raw,
            root=str(tmp_path),
            modules=["sandbox"],
        )
        fledgling.lockdown(
            raw,
            allowed_dirs=["/tmp/only-here"],
            lock_config=False,
        )
        row = raw.execute("SELECT current_setting('allowed_directories')").fetchone()
        dirs = row[0]
        assert any("/tmp/only-here" in d for d in dirs), f"expected /tmp/only-here in {dirs}"

    def test_lockdown_disables_external_access(self, tmp_path):
        """lockdown() sets enable_external_access = false."""
        raw = duckdb.connect(":memory:")
        fledgling.configure(
            raw,
            root=str(tmp_path),
            modules=["sandbox"],
        )
        fledgling.lockdown(raw, lock_config=False)
        val = raw.execute("SELECT current_setting('enable_external_access')").fetchone()[0]
        # DuckDB returns strings for boolean settings
        assert str(val).lower() in ("false", "0")

    def test_lockdown_lock_config_default(self, tmp_path):
        """lockdown() with default lock_config=True locks the configuration."""
        raw = duckdb.connect(":memory:")
        fledgling.configure(
            raw,
            root=str(tmp_path),
            modules=["sandbox"],
        )
        fledgling.lockdown(raw)
        # After lockdown with lock_config=True, changing settings should fail
        with pytest.raises(duckdb.Error):
            raw.execute("SET memory_limit = '1GB'")


# ── Top-level re-exports ─────────────────────────────────────────────


class TestReExports:
    """The new verbs and helpers are importable from the fledgling package."""

    def test_connect_exported(self):
        assert callable(fledgling.connect)

    def test_attach_exported(self):
        assert callable(fledgling.attach)

    def test_configure_exported(self):
        assert callable(fledgling.configure)

    def test_lockdown_exported(self):
        assert callable(fledgling.lockdown)

    def test_compose_helpers_exported(self):
        assert callable(fledgling.load_extensions)
        assert callable(fledgling.set_session_root)
        assert callable(fledgling.load_macros)
        assert callable(fledgling.apply_local_init)

    def test_connection_class_exported(self):
        assert fledgling.Connection is not None
