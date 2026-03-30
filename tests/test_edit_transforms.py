# tests/test_edit_transforms.py
"""Tests for stateless transform functions (pure Python, no DuckDB)."""

from fledgling.edit.region import Region
from fledgling.edit.ops import (
    Remove, Replace, InsertBefore, InsertAfter, Wrap, Move,
)
from fledgling.edit.transforms import (
    remove, replace_body, insert_before, insert_after, wrap, move, rename_in,
)


class TestRemoveTransform:
    def test_remove_returns_remove_op(self):
        r = Region.at("f.py", 10, 20, name="foo")
        op = remove(r)
        assert isinstance(op, Remove)
        assert op.region is r


class TestReplaceBody:
    def test_replace_body_returns_replace_op(self):
        r = Region.at("f.py", 10, 20)
        op = replace_body(r, "def new_func(): pass\n")
        assert isinstance(op, Replace)
        assert op.new_content == "def new_func(): pass\n"


class TestInsertBefore:
    def test_insert_before_returns_op(self):
        r = Region.at("f.py", 10, 10)
        op = insert_before(r, "# Added comment\n")
        assert isinstance(op, InsertBefore)
        assert op.content == "# Added comment\n"


class TestInsertAfter:
    def test_insert_after_returns_op(self):
        r = Region.at("f.py", 10, 10)
        op = insert_after(r, "\n# Trailing\n")
        assert isinstance(op, InsertAfter)
        assert op.content == "\n# Trailing\n"


class TestWrap:
    def test_wrap_returns_op(self):
        r = Region.at("f.py", 10, 15)
        op = wrap(r, "try:\n", "\nexcept Exception: pass")
        assert isinstance(op, Wrap)
        assert op.before == "try:\n"
        assert op.after == "\nexcept Exception: pass"


class TestMove:
    def test_move_returns_op(self):
        src = Region.at("a.py", 10, 20, name="helper")
        dst = Region.at("b.py", 1, 1)
        op = move(src, dst)
        assert isinstance(op, Move)
        assert op.region is src
        assert op.destination is dst


class TestRenameIn:
    def test_rename_in_produces_replace(self):
        r = Region(file_path="f.py", start_line=1, end_line=1,
                   content="def old_name(): pass\n")
        op = rename_in(r, "old_name", "new_name")
        assert isinstance(op, Replace)
        assert op.new_content == "def new_name(): pass\n"

    def test_rename_in_replaces_all_occurrences(self):
        r = Region(file_path="f.py", start_line=1, end_line=2,
                   content="x = old_name()\nold_name.attr\n")
        op = rename_in(r, "old_name", "new_name")
        assert op.new_content == "x = new_name()\nnew_name.attr\n"

    def test_rename_in_does_not_replace_substrings(self):
        r = Region(file_path="f.py", start_line=1, end_line=1,
                   content="old_name_extended = 1\n")
        op = rename_in(r, "old_name", "new_name")
        # Should only replace whole words, not substrings
        assert "new_name_extended" not in op.new_content
        assert "old_name_extended" in op.new_content
