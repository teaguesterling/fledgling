# tests/test_edit_ops.py
"""Tests for EditOp hierarchy (pure Python, no DuckDB)."""

import pytest
from fledgling.edit.region import Region
from fledgling.edit.ops import (
    EditOp, Remove, Replace, InsertBefore, InsertAfter, Wrap, Move,
)


class TestRemove:
    def test_remove_has_region(self):
        r = Region.at("f.py", 10, 20, name="foo")
        op = Remove(region=r)
        assert op.region is r
        assert op.file_path == "f.py"
        assert op.start_line == 10

    def test_remove_is_editop(self):
        op = Remove(region=Region.at("f.py", 1, 5))
        assert isinstance(op, EditOp)


class TestReplace:
    def test_replace_has_new_content(self):
        r = Region.at("f.py", 10, 20)
        op = Replace(region=r, new_content="def bar(): pass\n")
        assert op.new_content == "def bar(): pass\n"
        assert op.file_path == "f.py"


class TestInsertBefore:
    def test_insert_before(self):
        r = Region.at("f.py", 10, 10)
        op = InsertBefore(region=r, content="# comment\n")
        assert op.content == "# comment\n"


class TestInsertAfter:
    def test_insert_after(self):
        r = Region.at("f.py", 10, 10)
        op = InsertAfter(region=r, content="\n# end\n")
        assert op.content == "\n# end\n"


class TestWrap:
    def test_wrap_has_before_and_after(self):
        r = Region.at("f.py", 10, 15)
        op = Wrap(region=r, before="try:\n    ", after="\nexcept: pass")
        assert op.before == "try:\n    "
        assert op.after == "\nexcept: pass"


class TestMove:
    def test_move_has_source_and_destination(self):
        src = Region.at("a.py", 10, 20, name="helper")
        dst = Region.at("b.py", 5, 5)
        op = Move(region=src, destination=dst)
        assert op.region is src
        assert op.destination is dst
        assert op.file_path == "a.py"

    def test_move_destination_must_be_located(self):
        src = Region.at("a.py", 10, 20)
        dst = Region.of("standalone content")
        with pytest.raises(ValueError, match="located"):
            Move(region=src, destination=dst)
