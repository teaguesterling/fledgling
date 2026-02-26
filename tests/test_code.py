"""Tests for code intelligence macros (sitting_duck tier)."""

import pytest
from conftest import CONFTEST_PATH, DUCK_NEST_ROOT


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

    def test_includes_line_count(self, code_macros):
        desc = code_macros.execute(
            "DESCRIBE SELECT * FROM code_structure(?)", [CONFTEST_PATH]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "line_count" in col_names

    def test_line_count_positive(self, code_macros):
        rows = code_macros.execute(
            "SELECT line_count FROM code_structure(?)", [CONFTEST_PATH]
        ).fetchall()
        for row in rows:
            assert row[0] >= 1
