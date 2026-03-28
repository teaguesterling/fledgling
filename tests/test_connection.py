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
        """When .fledgling-init.sql exists in root, it's used."""
        init = tmp_path / ".fledgling-init.sql"
        init.write_text("LOAD read_lines;\n")
        con = fledgling.connect(root=str(tmp_path))
        # Should load without error
        assert con.execute("SELECT 1").fetchone()[0] == 1

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
        with pytest.raises(FileNotFoundError, match="No fledgling init file"):
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
