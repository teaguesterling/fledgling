"""Tests for fledgling.tools — Python function wrappers for SQL macros."""

import os
import pytest
import duckdb

import fledgling
from fledgling.tools import Tools, _to_sql_literal

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def con():
    """Fledgling connection for tools testing."""
    return fledgling.connect(init=False)


# ── SQL literal conversion ───────────────────────────────────────────


class TestToSqlLiteral:
    def test_none(self):
        assert _to_sql_literal(None) == "NULL"

    def test_string(self):
        assert _to_sql_literal("hello") == "'hello'"

    def test_string_with_quotes(self):
        assert _to_sql_literal("it's") == "'it''s'"

    def test_int(self):
        assert _to_sql_literal(42) == "42"

    def test_float(self):
        assert _to_sql_literal(3.14) == "3.14"

    def test_bool(self):
        assert _to_sql_literal(True) == "true"
        assert _to_sql_literal(False) == "false"

    def test_list(self):
        assert _to_sql_literal(["a", "b"]) == "['a', 'b']"

    def test_empty_list(self):
        assert _to_sql_literal([]) == "[]"


# ── Tools discovery ──────────────────────────────────────────────────


class TestToolsDiscovery:
    def test_discovers_macros(self, con):
        assert len(con._tools._macros) > 10

    def test_known_macros_present(self, con):
        macros = con._tools._macros
        assert "find_definitions" in macros
        assert "list_files" in macros
        assert "recent_changes" in macros
        assert "doc_outline" in macros

    def test_excludes_internal_macros(self, con):
        macros = con._tools._macros
        assert "_resolve" not in macros
        assert "_session_root" not in macros
        assert "_is_code_file" not in macros

    def test_list_method(self, con):
        items = con._tools.list()
        assert len(items) > 10
        names = [i["name"] for i in items]
        assert "find_definitions" in names

    def test_dir_includes_macros(self, con):
        attrs = dir(con._tools)
        assert "find_definitions" in attrs
        assert "recent_changes" in attrs

    def test_unknown_macro_raises(self, con):
        with pytest.raises(AttributeError, match="No macro"):
            con._tools.nonexistent_macro


# ── Connection-level macro access ────────────────────────────────────


class TestConnectionMacros:
    def test_macro_as_method(self, con):
        rel = con.find_definitions(f"{PROJECT_ROOT}/tests/conftest.py")
        assert hasattr(rel, "fetchall")
        assert hasattr(rel, "show")
        assert hasattr(rel, "df")

    def test_returns_relation(self, con):
        rel = con.list_files(f"{PROJECT_ROOT}/tests/*.py")
        # DuckDBPyRelation attributes
        assert hasattr(rel, "columns")
        assert hasattr(rel, "shape")
        assert "file_path" in rel.columns

    def test_relation_chaining(self, con):
        count = con.list_files(f"{PROJECT_ROOT}/tests/*.py").aggregate(
            "count(*) AS n"
        ).fetchone()[0]
        assert count > 5

    def test_fetchall_returns_tuples(self, con):
        rows = con.recent_changes(2).fetchall()
        assert isinstance(rows, list)
        assert len(rows) == 2
        assert isinstance(rows[0], tuple)

    def test_shape(self, con):
        shape = con.recent_changes(3).shape
        assert shape[0] == 3  # 3 rows
        assert shape[1] == 4  # hash, author, date, message

    def test_columns(self, con):
        cols = con.find_definitions(f"{PROJECT_ROOT}/tests/conftest.py").columns
        assert "name" in cols
        assert "file_path" in cols
        assert "kind" in cols

    def test_sql_still_works(self, con):
        """Standard DuckDB .sql() still works through the wrapper."""
        rel = con.sql("SELECT 42 AS answer")
        assert rel.fetchone()[0] == 42

    def test_execute_still_works(self, con):
        """Standard DuckDB .execute() still works through the wrapper."""
        result = con.execute("SELECT 42 AS answer")
        assert result.fetchone()[0] == 42

    def test_dir_includes_both(self, con):
        attrs = dir(con)
        # DuckDB connection methods
        assert "execute" in attrs
        assert "sql" in attrs
        # Fledgling macros
        assert "find_definitions" in attrs
        assert "recent_changes" in attrs


# ── Keyword arguments ────────────────────────────────────────────────


class TestKeywordArgs:
    def test_named_parameter(self, con):
        rows = con.doc_outline(
            f"{PROJECT_ROOT}/SKILL.md",
            max_lvl=2,
        ).fetchall()
        levels = [r[3] for r in rows]  # level column
        assert all(l <= 2 for l in levels)

    def test_search_parameter(self, con):
        all_rows = con.doc_outline(f"{PROJECT_ROOT}/SKILL.md").fetchall()
        filtered = con.doc_outline(
            f"{PROJECT_ROOT}/SKILL.md",
            search="macro",
        ).fetchall()
        assert len(filtered) > 0
        assert len(filtered) < len(all_rows)

    def test_mixed_positional_and_named(self, con):
        rows = con.find_definitions(
            f"{PROJECT_ROOT}/tests/conftest.py",
            name_pattern="load%",
        ).fetchall()
        names = [r[1] for r in rows]
        assert "load_sql" in names


# ── Repr and debugging ───────────────────────────────────────────────


class TestRepr:
    def test_macro_repr(self, con):
        r = repr(con._tools.find_definitions)
        assert "fledgling.find_definitions" in r

    def test_relation_has_sql_query(self, con):
        """The returned relation exposes the underlying SQL."""
        rel = con.find_definitions(f"{PROJECT_ROOT}/tests/conftest.py")
        sql = rel.sql_query()
        assert "find_definitions" in sql


# ── Module-level API ─────────────────────────────────────────────────


class TestModuleLevel:
    def test_import_and_call(self):
        from fledgling.tools import list_files
        rel = list_files(f"{PROJECT_ROOT}/sql/*.sql")
        assert rel.shape[0] > 5

    def test_unknown_raises(self):
        with pytest.raises(AttributeError):
            from fledgling import tools
            tools.nonexistent_macro_xyz
