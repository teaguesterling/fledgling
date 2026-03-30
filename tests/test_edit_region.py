# tests/test_edit_region.py
"""Tests for Region and MatchRegion data classes (pure Python, no DuckDB)."""

import pytest
from fledgling.edit.region import Region, MatchRegion, CapturedNode


class TestRegionConstruction:
    def test_region_all_none_by_default(self):
        r = Region()
        assert r.file_path is None
        assert r.content is None
        assert r.start_line is None

    def test_region_at_convenience(self):
        r = Region.at("src/main.py", 10, 25)
        assert r.file_path == "src/main.py"
        assert r.start_line == 10
        assert r.end_line == 25
        assert r.content is None

    def test_region_at_with_kwargs(self):
        r = Region.at("src/main.py", 10, 25, name="foo", kind="function")
        assert r.name == "foo"
        assert r.kind == "function"

    def test_region_of_convenience(self):
        r = Region.of("def hello(): pass")
        assert r.content == "def hello(): pass"
        assert r.file_path is None

    def test_region_of_with_kwargs(self):
        r = Region.of("import os", language="python")
        assert r.language == "python"

    def test_region_is_frozen(self):
        r = Region.at("f.py", 1, 5)
        with pytest.raises(AttributeError):
            r.file_path = "other.py"


class TestRegionPredicates:
    def test_is_located(self):
        assert Region.at("f.py", 1, 5).is_located
        assert not Region.of("code").is_located
        assert not Region().is_located

    def test_is_resolved(self):
        r = Region(file_path="f.py", start_line=1, end_line=5, content="code")
        assert r.is_resolved
        assert not Region.at("f.py", 1, 5).is_resolved

    def test_is_standalone(self):
        assert Region.of("code").is_standalone
        assert not Region.at("f.py", 1, 5).is_standalone


class TestRegionResolve:
    def test_resolve_reads_file(self, tmp_path):
        p = tmp_path / "test.py"
        p.write_text("line1\nline2\nline3\nline4\nline5\n")
        r = Region.at(str(p), 2, 4)
        resolved = r.resolve()
        assert resolved.is_resolved
        assert resolved.content == "line2\nline3\nline4\n"

    def test_resolve_noop_if_already_resolved(self):
        r = Region(file_path="f.py", start_line=1, end_line=1, content="x")
        assert r.resolve() is r

    def test_resolve_with_custom_reader(self):
        reader = lambda fp, sl, el: "custom content"
        r = Region.at("f.py", 1, 5)
        resolved = r.resolve(reader=reader)
        assert resolved.content == "custom content"

    def test_resolve_with_columns(self, tmp_path):
        p = tmp_path / "test.py"
        p.write_text("x = foo(bar)\n")
        r = Region(file_path=str(p), start_line=1, end_line=1,
                   start_column=5, end_column=13)
        resolved = r.resolve()
        assert resolved.content == "foo(bar)"


class TestRegionHashable:
    def test_region_in_set(self):
        r1 = Region.at("f.py", 1, 5)
        r2 = Region.at("f.py", 1, 5)
        assert r1 == r2
        assert len({r1, r2}) == 1


class TestMatchRegion:
    def test_match_region_has_captures(self):
        cap = CapturedNode(
            name="F", node_id=42, type="identifier",
            peek="my_func", start_line=10, end_line=10,
        )
        mr = MatchRegion(
            file_path="f.py", start_line=10, end_line=12,
            captures={"F": cap},
        )
        assert mr.captures["F"].peek == "my_func"
        assert mr.is_located

    def test_match_region_is_region(self):
        mr = MatchRegion(file_path="f.py", start_line=1, end_line=2)
        assert isinstance(mr, Region)

    def test_captured_node_fields(self):
        c = CapturedNode(
            name="X", node_id=7, type="string",
            peek='"hello"', start_line=5, end_line=5,
        )
        assert c.name == "X"
        assert c.node_id == 7
        assert c.peek == '"hello"'
