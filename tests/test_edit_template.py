# tests/test_edit_template.py
"""Tests for template substitution engine (pure Python, no DuckDB)."""

import pytest
from fledgling.edit.region import MatchRegion, CapturedNode
from fledgling.edit.template import template_replace


def _cap(name, peek, **kw):
    """Shorthand for CapturedNode construction."""
    return CapturedNode(
        name=name, peek=peek,
        node_id=kw.get("node_id", 0),
        type=kw.get("type", "identifier"),
        start_line=kw.get("start_line", 1),
        end_line=kw.get("end_line", 1),
    )


class TestTemplateReplace:
    def test_simple_substitution(self):
        mr = MatchRegion(captures={"F": _cap("F", "old_func")})
        result = template_replace(mr, "__F__()")
        assert result == "old_func()"

    def test_multiple_captures(self):
        mr = MatchRegion(captures={
            "F": _cap("F", "my_func"),
            "ARGS": _cap("ARGS", "x, y, z"),
        })
        result = template_replace(mr, "new_func(__ARGS__)")
        assert result == "new_func(x, y, z)"

    def test_capture_used_twice(self):
        mr = MatchRegion(captures={"X": _cap("X", "val")})
        result = template_replace(mr, "__X__ + __X__")
        assert result == "val + val"

    def test_no_captures_returns_template_unchanged(self):
        mr = MatchRegion(captures={})
        result = template_replace(mr, "literal code")
        assert result == "literal code"

    def test_unmatched_wildcard_raises(self):
        mr = MatchRegion(captures={"F": _cap("F", "func")})
        with pytest.raises(KeyError, match="MISSING"):
            template_replace(mr, "__MISSING__()")

    def test_empty_template(self):
        mr = MatchRegion(captures={"F": _cap("F", "func")})
        result = template_replace(mr, "")
        assert result == ""

    def test_multiline_capture(self):
        body = "    x = 1\n    y = 2\n    return x + y"
        mr = MatchRegion(captures={"BODY": _cap("BODY", body)})
        result = template_replace(mr, "def wrapper():\n__BODY__")
        assert result == "def wrapper():\n    x = 1\n    y = 2\n    return x + y"

    def test_preserves_non_wildcard_dunders(self):
        """Python __init__ should NOT be treated as a wildcard."""
        mr = MatchRegion(captures={})
        result = template_replace(mr, "self.__init__()")
        assert result == "self.__init__()"
