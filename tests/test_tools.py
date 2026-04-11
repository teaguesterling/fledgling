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


# ── Delta 1: MCP registry vs catalog discovery ───────────────────────
#
# Tests here use raw `duckdb.connect()` with inline CREATE MACRO so they
# don't depend on the fledgling module list (which loads code.sql and can
# fail in environments without sitting_duck's ast_select). They isolate
# the discovery logic itself.


class TestCatalogFallback:
    """Tools falls back to duckdb_functions() scan when the MCP registry
    isn't available (older duckdb_mcp, not loaded, or no publications)."""

    def test_fallback_discovers_table_macros(self):
        raw = duckdb.connect()
        raw.execute("CREATE MACRO t_public_alpha() AS TABLE SELECT 1 AS x")
        raw.execute("CREATE MACRO t_public_beta() AS TABLE SELECT 2 AS y")
        tools = Tools(raw)
        assert tools._source == "catalog"
        assert "t_public_alpha" in tools._macros
        assert "t_public_beta" in tools._macros

    def test_fallback_excludes_underscore_prefix(self):
        raw = duckdb.connect()
        raw.execute("CREATE MACRO t_public() AS TABLE SELECT 1")
        raw.execute("CREATE MACRO _t_internal() AS TABLE SELECT 2")
        tools = Tools(raw)
        assert "t_public" in tools._macros
        assert "_t_internal" not in tools._macros

    def test_fallback_has_no_descriptions(self):
        raw = duckdb.connect()
        raw.execute("CREATE MACRO t_undocumented() AS TABLE SELECT 1")
        tools = Tools(raw)
        assert tools._descriptions == {}

    def test_fallback_wrapper_docstring_basic(self):
        raw = duckdb.connect()
        raw.execute("CREATE MACRO t_bare() AS TABLE SELECT 1")
        tools = Tools(raw)
        call = tools.t_bare
        # No description → baseline docstring
        assert "Call t_bare" in call.__doc__
        assert "DuckDBPyRelation" in call.__doc__

    def test_list_method_includes_description_key(self):
        """The list() method returns dicts with a 'description' key
        (may be None in fallback mode)."""
        raw = duckdb.connect()
        raw.execute("CREATE MACRO t_listed() AS TABLE SELECT 1")
        tools = Tools(raw)
        items = tools.list()
        # DuckDB's builtin table macros (duckdb_logs_parsed, histogram,
        # histogram_values) also appear in the main schema, so we assert
        # on the presence of our macro rather than the total count.
        by_name = {item["name"]: item for item in items}
        assert "t_listed" in by_name
        item = by_name["t_listed"]
        assert "description" in item
        assert item["description"] is None


class TestMCPRegistryDetection:
    """Feature detection for the MCP publication registry path.

    The curated path requires duckdb_mcp >= b1eb63d (no-arg mcp_list_tools()
    table function). In the current Python environment the installed build
    is f77fb34 (DuckDB 1.4.4), which does NOT have that overload, so these
    tests verify the detection correctly returns False and falls back.
    """

    def test_detection_returns_none_without_duckdb_mcp(self):
        raw = duckdb.connect()
        raw.execute("CREATE MACRO t_x() AS TABLE SELECT 1")
        tools = Tools(raw)
        # duckdb_mcp not loaded → feature detection returns None
        assert tools._try_mcp_registry() is None
        assert tools._source == "catalog"

    def test_detection_returns_none_with_scalar_only_mcp_list_tools(self):
        """When duckdb_mcp is loaded but only has scalar mcp_list_tools(VARCHAR)
        overloads (no no-arg table function), feature detection returns None."""
        raw = duckdb.connect()
        try:
            raw.execute("LOAD duckdb_mcp")
        except Exception:
            pytest.skip("duckdb_mcp not installed")

        # Confirm the environment matches expectations: no zero-arg overload
        has_noarg = raw.execute(
            "SELECT 1 FROM duckdb_functions() "
            "WHERE function_name = 'mcp_list_tools' AND len(parameters) = 0 "
            "LIMIT 1"
        ).fetchone()
        if has_noarg is not None:
            pytest.skip(
                "environment has no-arg mcp_list_tools(); this test exercises "
                "the pre-b1eb63d path"
            )

        raw.execute("CREATE MACRO t_x() AS TABLE SELECT 1")
        tools = Tools(raw)
        assert tools._try_mcp_registry() is None
        assert tools._source == "catalog"


class TestMacroCallDescription:
    """_MacroCall carries a description into __doc__ when supplied."""

    def test_description_in_docstring(self):
        from fledgling.tools import _MacroCall
        raw = duckdb.connect()
        raw.execute("CREATE MACRO t_described() AS TABLE SELECT 1")
        call = _MacroCall(
            raw,
            "t_described",
            [],
            description="Find all the things.",
        )
        assert "Find all the things" in call.__doc__
        assert "Call t_described" in call.__doc__

    def test_no_description_baseline_docstring(self):
        from fledgling.tools import _MacroCall
        raw = duckdb.connect()
        raw.execute("CREATE MACRO t_plain() AS TABLE SELECT 1")
        call = _MacroCall(raw, "t_plain", [])
        assert "Call t_plain" in call.__doc__
        # No extra description text before "Call"
        assert call.__doc__.lstrip().startswith("Call")


class TestMacroNameExtraction:
    """_extract_macro_name parses tool sql_template → macro name."""

    def test_simple_select_from(self):
        from fledgling.tools import _extract_macro_name
        sql = "SELECT * FROM find_definitions($file, $name)"
        assert _extract_macro_name(sql) == "find_definitions"

    def test_multiline_with_whitespace(self):
        from fledgling.tools import _extract_macro_name
        sql = """SELECT * FROM
                    code_structure(
                        $file_pattern
                    )"""
        assert _extract_macro_name(sql) == "code_structure"

    def test_cte_before_from_extracts_first_match(self):
        """When a template uses CTEs with FROM clauses, the first FROM wins.
        This is acceptable for fledgling's tool publications which are
        almost always a plain SELECT * FROM macro(...) pattern."""
        from fledgling.tools import _extract_macro_name
        sql = """WITH a AS (SELECT * FROM base_macro(x))
                 SELECT * FROM wrapper_macro(y)"""
        assert _extract_macro_name(sql) == "base_macro"

    def test_case_insensitive(self):
        from fledgling.tools import _extract_macro_name
        sql = "select * from MyMacro()"
        assert _extract_macro_name(sql) == "MyMacro"

    def test_no_from_returns_none(self):
        from fledgling.tools import _extract_macro_name
        assert _extract_macro_name("SELECT 1 AS x") is None

    def test_empty_returns_none(self):
        from fledgling.tools import _extract_macro_name
        assert _extract_macro_name("") is None
        assert _extract_macro_name(None) is None
