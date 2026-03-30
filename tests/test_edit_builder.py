# tests/test_edit_builder.py
"""Tests for fluent Editor/Builder API (integration, requires DuckDB)."""

import os
import pytest
import duckdb

from conftest import load_sql

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from fledgling.edit.builder import Editor
from fledgling.edit.changeset import Changeset


@pytest.fixture
def editor(tmp_path):
    """Editor with a fledgling-enabled connection and test files."""
    con = duckdb.connect(":memory:")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD read_lines")
    for f in ["source.sql", "code.sql"]:
        load_sql(con, f)

    # Create test files
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text(
        "def old_func():\n"
        "    return 1\n"
        "\n"
        "def keep_me():\n"
        "    return 2\n"
    )
    (src / "utils.py").write_text("# utilities\n")

    return Editor(con), str(tmp_path)



class TestEditorDefinitions:
    def test_definitions_returns_selection(self, editor):
        ed, base = editor
        fp = os.path.join(base, "src", "main.py")
        sel = ed.definitions(fp, "old_func")
        assert sel is not None

    def test_remove_returns_changeset(self, editor):
        ed, base = editor
        fp = os.path.join(base, "src", "main.py")
        cs = ed.definitions(fp, "old_func").remove()
        assert isinstance(cs, Changeset)

    def test_remove_diff_shows_removal(self, editor):
        ed, base = editor
        fp = os.path.join(base, "src", "main.py")
        diff = ed.definitions(fp, "old_func").remove().diff()
        assert "-def old_func" in diff

    def test_rename_diff(self, editor):
        ed, base = editor
        fp = os.path.join(base, "src", "main.py")
        diff = ed.definitions(fp, "old_func").rename("new_func").diff()
        assert "+def new_func" in diff
        assert "-def old_func" in diff


class TestEditorComposition:
    def test_add_changesets(self, editor):
        ed, base = editor
        fp = os.path.join(base, "src", "main.py")
        cs1 = ed.definitions(fp, "old_func").remove()
        cs2 = ed.definitions(fp, "keep_me").remove()
        combined = cs1 + cs2
        assert len(combined.ops) == 2
