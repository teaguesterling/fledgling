"""Tests for code intelligence macros (sitting_duck tier)."""

import pytest
from conftest import CONFTEST_PATH, PROJECT_ROOT, SQL_DIR


class TestFindDefinitions:
    def test_finds_definitions_in_python(self, code_macros):
        rows = code_macros.execute(
            "SELECT * FROM find_definitions(?)", [CONFTEST_PATH]
        ).fetchall()
        assert len(rows) > 0

    def test_definition_columns(self, code_macros):
        desc = code_macros.execute(
            "DESCRIBE SELECT * FROM find_definitions(?)", [CONFTEST_PATH]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "file_path" in col_names
        assert "name" in col_names
        assert "kind" in col_names
        assert "start_line" in col_names
        assert "end_line" in col_names

    def test_finds_named_function(self, code_macros):
        rows = code_macros.execute(
            "SELECT name, kind FROM find_definitions(?, 'load_sql')",
            [CONFTEST_PATH],
        ).fetchall()
        assert len(rows) >= 1
        names = [r[0] for r in rows]
        assert "load_sql" in names

    def test_wildcard_pattern(self, code_macros):
        rows = code_macros.execute(
            "SELECT name FROM find_definitions(?, '%macro%')",
            [CONFTEST_PATH],
        ).fetchall()
        names = [r[0] for r in rows]
        # Fixtures with "macros" in name
        assert any("macro" in n for n in names)

    def test_results_ordered_by_line(self, code_macros):
        rows = code_macros.execute(
            "SELECT start_line FROM find_definitions(?)", [CONFTEST_PATH]
        ).fetchall()
        lines = [r[0] for r in rows]
        assert lines == sorted(lines)


class TestFindCalls:
    def test_finds_calls(self, code_macros):
        rows = code_macros.execute(
            "SELECT * FROM find_calls(?)", [CONFTEST_PATH]
        ).fetchall()
        assert len(rows) > 0

    def test_finds_specific_call(self, code_macros):
        rows = code_macros.execute(
            "SELECT name FROM find_calls(?, 'connect')",
            [CONFTEST_PATH],
        ).fetchall()
        names = [r[0] for r in rows]
        assert "connect" in names

    def test_call_columns(self, code_macros):
        desc = code_macros.execute(
            "DESCRIBE SELECT * FROM find_calls(?)", [CONFTEST_PATH]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "name" in col_names
        assert "call_expression" in col_names


class TestFindImports:
    def test_finds_imports(self, code_macros):
        rows = code_macros.execute(
            "SELECT * FROM find_imports(?)", [CONFTEST_PATH]
        ).fetchall()
        assert len(rows) > 0

    def test_finds_known_imports(self, code_macros):
        # NOTE: sitting_duck has a bug where import names are empty
        # (see https://github.com/teaguesterling/sitting_duck/issues/23)
        # so we check import_statement (peek) instead of name
        rows = code_macros.execute(
            "SELECT import_statement FROM find_imports(?)", [CONFTEST_PATH]
        ).fetchall()
        stmts = [r[0] for r in rows]
        assert any("os" in s for s in stmts)
        assert any("duckdb" in s for s in stmts)


class TestCodeStructure:
    def test_returns_top_level_definitions(self, code_macros):
        rows = code_macros.execute(
            "SELECT * FROM code_structure(?)", [CONFTEST_PATH]
        ).fetchall()
        assert len(rows) > 0

    def test_columns(self, code_macros):
        desc = code_macros.execute(
            "DESCRIBE SELECT * FROM code_structure(?)", [CONFTEST_PATH]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert col_names == [
            "file_path", "name", "kind", "start_line", "end_line",
            "line_count", "descendant_count", "children_count",
            "cyclomatic_complexity",
        ]

    def test_line_count_positive(self, code_macros):
        rows = code_macros.execute(
            "SELECT line_count FROM code_structure(?)", [CONFTEST_PATH]
        ).fetchall()
        for row in rows:
            assert row[0] >= 1

    def test_structural_metrics_present(self, code_macros):
        rows = code_macros.execute(
            "SELECT descendant_count, children_count FROM code_structure(?)",
            [CONFTEST_PATH],
        ).fetchall()
        assert len(rows) > 0
        # descendant_count and children_count must be non-negative integers
        for row in rows:
            assert row[0] >= 0
            assert row[1] >= 0

    def test_cyclomatic_complexity_for_functions(self, code_macros):
        rows = code_macros.execute(
            """SELECT name, kind, cyclomatic_complexity
               FROM code_structure(?)
               WHERE kind = 'DEFINITION_FUNCTION'""",
            [CONFTEST_PATH],
        ).fetchall()
        assert len(rows) > 0
        # Functions should have non-NULL cyclomatic complexity >= 1
        for row in rows:
            assert row[2] is not None
            assert row[2] >= 1

    def test_cyclomatic_null_for_non_functions(self, code_macros):
        rows = code_macros.execute(
            """SELECT name, kind, cyclomatic_complexity
               FROM code_structure(?)
               WHERE kind NOT IN ('DEFINITION_FUNCTION', 'DEFINITION_METHOD')""",
            [CONFTEST_PATH],
        ).fetchall()
        # Non-function definitions should have NULL cyclomatic complexity
        for row in rows:
            assert row[2] is None


class TestComplexityHotspots:
    def test_returns_results(self, code_macros):
        rows = code_macros.execute(
            "SELECT * FROM complexity_hotspots(?)", [CONFTEST_PATH]
        ).fetchall()
        assert len(rows) > 0

    def test_columns(self, code_macros):
        desc = code_macros.execute(
            "DESCRIBE SELECT * FROM complexity_hotspots(?)", [CONFTEST_PATH]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert col_names == [
            "file_path", "name", "lines", "cyclomatic",
            "conditionals", "loops", "return_count", "max_depth",
        ]

    def test_ordered_by_cyclomatic_desc(self, code_macros):
        rows = code_macros.execute(
            "SELECT cyclomatic FROM complexity_hotspots(?)", [CONFTEST_PATH]
        ).fetchall()
        cc = [r[0] for r in rows]
        assert cc == sorted(cc, reverse=True)

    def test_limit(self, code_macros):
        rows = code_macros.execute(
            "SELECT * FROM complexity_hotspots(?, 3)", [CONFTEST_PATH]
        ).fetchall()
        assert len(rows) == 3


class TestFunctionCallers:
    def test_finds_callers(self, code_macros):
        # load_sql is called in conftest.py by fixture functions
        rows = code_macros.execute(
            "SELECT * FROM function_callers(?, 'load_sql')", [CONFTEST_PATH]
        ).fetchall()
        assert len(rows) > 0

    def test_columns(self, code_macros):
        desc = code_macros.execute(
            "DESCRIBE SELECT * FROM function_callers(?, 'load_sql')",
            [CONFTEST_PATH],
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert col_names == [
            "file_path", "call_line", "caller_name", "caller_kind",
        ]

    def test_caller_is_enclosing_function(self, code_macros):
        rows = code_macros.execute(
            "SELECT caller_name FROM function_callers(?, 'load_sql')",
            [CONFTEST_PATH],
        ).fetchall()
        callers = [r[0] for r in rows]
        # load_sql is called from fixture functions like source_macros, code_macros, etc.
        assert any("macros" in c for c in callers if c)

    def test_no_duplicates(self, code_macros):
        rows = code_macros.execute(
            "SELECT file_path, call_line FROM function_callers(?, 'load_sql')",
            [CONFTEST_PATH],
        ).fetchall()
        # Each (file, line) should appear exactly once
        assert len(rows) == len(set(rows))


class TestModuleDependencies:
    """Tests for module_dependencies macro.

    This macro is designed for package-level analysis (e.g. 'blq' imports
    within a blq package). Fledgling's own test files don't form a package,
    so we test column schema and empty-result behavior.
    """

    def test_columns(self, code_macros):
        desc = code_macros.execute(
            "DESCRIBE SELECT * FROM module_dependencies(?, 'nonexistent')",
            [CONFTEST_PATH],
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert col_names == ["source_module", "target_module", "fan_in"]

    def test_no_matches_returns_empty(self, code_macros):
        rows = code_macros.execute(
            "SELECT * FROM module_dependencies(?, 'nonexistent_pkg')",
            [CONFTEST_PATH],
        ).fetchall()
        assert len(rows) == 0
