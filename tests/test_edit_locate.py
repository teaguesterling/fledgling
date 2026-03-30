"""Tests for targeting bridge (requires fledgling DuckDB connection)."""

import os
import pytest
import duckdb

from tests.conftest import load_sql, PROJECT_ROOT, CONFTEST_PATH

from fledgling.edit.locate import locate
from fledgling.edit.region import Region


@pytest.fixture
def code_con():
    """DuckDB connection with sitting_duck + code macros."""
    con = duckdb.connect(":memory:")
    con.execute("LOAD sitting_duck")
    load_sql(con, "code.sql")
    return con


class TestLocateDefinitions:
    def test_find_function_by_name(self, code_con):
        regions = locate(code_con, CONFTEST_PATH, name="load_sql",
                         kind="function")
        assert len(regions) >= 1
        r = regions[0]
        assert r.is_located
        assert r.name == "load_sql"
        assert r.kind == "function"
        assert r.file_path.endswith("conftest.py")

    def test_find_function_resolves_content(self, code_con):
        regions = locate(code_con, CONFTEST_PATH, name="load_sql",
                         kind="function", resolve=True)
        r = regions[0]
        assert r.is_resolved
        assert "def load_sql" in r.content

    def test_find_function_no_resolve(self, code_con):
        regions = locate(code_con, CONFTEST_PATH, name="load_sql",
                         kind="function", resolve=False)
        r = regions[0]
        assert r.is_located
        assert not r.is_resolved

    def test_find_class_by_kind(self, code_con):
        # fledgling/tools.py has class Tools
        tools_path = os.path.join(PROJECT_ROOT, "fledgling/tools.py")
        regions = locate(code_con, tools_path, kind="class")
        names = [r.name for r in regions]
        assert "Tools" in names

    def test_find_definition_by_name_pattern(self, code_con):
        regions = locate(code_con, CONFTEST_PATH, name="con%",
                         kind="definition")
        names = [r.name for r in regions]
        assert "con" in names

    def test_find_with_columns(self, code_con):
        regions = locate(code_con, CONFTEST_PATH, name="load_sql",
                         kind="function", columns=True)
        r = regions[0]
        assert r.start_column is not None


class TestLocateByKind:
    def test_find_imports(self, code_con):
        regions = locate(code_con, CONFTEST_PATH, kind="import")
        assert len(regions) > 0
        for r in regions:
            assert r.kind == "import"

    def test_find_calls(self, code_con):
        regions = locate(code_con, CONFTEST_PATH, kind="call",
                         name="load_sql")
        assert len(regions) > 0

    def test_unknown_kind_raises(self, code_con):
        with pytest.raises(ValueError, match="kind"):
            locate(code_con, "**/*.py", kind="unknown_thing")


from fledgling.edit.validate import validate_syntax


class TestValidateSyntax:
    def test_valid_python(self, code_con):
        assert validate_syntax("def foo(): pass\n", "python", code_con) is True

    def test_invalid_python(self, code_con):
        assert validate_syntax("def (broken syntax\n", "python", code_con) is False

    def test_empty_content(self, code_con):
        assert validate_syntax("", "python", code_con) is True
