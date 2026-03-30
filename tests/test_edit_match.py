"""Tests for match() and match_replace() (requires fledgling DuckDB connection)."""

import os
import pytest
import duckdb

from tests.conftest import load_sql, PROJECT_ROOT

from fledgling.edit.locate import match, match_replace
from fledgling.edit.region import MatchRegion


@pytest.fixture
def ast_con(tmp_path):
    """DuckDB connection with sitting_duck, pointed at a temp Python file."""
    con = duckdb.connect(":memory:")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD read_lines")

    # Create a test file with known patterns
    test_file = tmp_path / "example.py"
    test_file.write_text(
        "def greet(name):\n"
        "    print(name)\n"
        "\n"
        "def farewell(name):\n"
        "    print('bye ' + name)\n"
        "\n"
        "greet('world')\n"
        "farewell('world')\n"
    )
    # Load code macros
    load_sql(con, "source.sql")
    load_sql(con, "code.sql")

    return con, str(tmp_path)


class TestMatch:
    def test_match_function_pattern(self, ast_con):
        con, dir_path = ast_con
        fp = os.path.join(dir_path, "example.py")
        regions = match(con, fp, "print(__X__)", "python")
        assert len(regions) >= 2
        for r in regions:
            assert isinstance(r, MatchRegion)
            assert "X" in r.captures

    def test_match_captures_content(self, ast_con):
        con, dir_path = ast_con
        fp = os.path.join(dir_path, "example.py")
        regions = match(con, fp, "greet(__X__)", "python")
        assert len(regions) >= 1
        # The capture should contain the argument
        x_peek = regions[0].captures["X"].peek
        assert "world" in x_peek


class TestMatchReplace:
    def test_match_replace_produces_changeset(self, ast_con):
        con, dir_path = ast_con
        fp = os.path.join(dir_path, "example.py")
        cs = match_replace(con, fp, "greet(__X__)", "hello(__X__)", "python")
        assert len(cs.ops) >= 1
        diff = cs.diff()
        assert "-greet(" in diff or "greet" in diff

    def test_match_replace_empty_template_removes(self, ast_con):
        con, dir_path = ast_con
        fp = os.path.join(dir_path, "example.py")
        cs = match_replace(con, fp, "greet(__X__)", "", "python")
        from fledgling.edit.ops import Remove
        assert any(isinstance(op, Remove) for op in cs.ops)
