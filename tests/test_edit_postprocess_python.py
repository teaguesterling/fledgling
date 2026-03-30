# tests/test_edit_postprocess_python.py
"""Tests for Python post-processor (pure Python, no DuckDB)."""

import textwrap
import pytest
from fledgling.edit.postprocess import PostProcessor, get_postprocessor
from fledgling.edit.postprocess.python import PythonPostProcessor
from fledgling.edit.region import Region


class TestPythonIndentation:
    def test_dedent_method_to_function(self):
        """Moving a method out of a class should strip one indent level."""
        pp = PythonPostProcessor()
        content = "    def helper(self):\n        return 1\n"
        # Target context: top-level (depth 0)
        target = Region.at("utils.py", 1, 1)
        result = pp.adjust_indentation(content, target)
        assert result == "def helper(self):\n    return 1\n"

    def test_indent_function_to_method(self):
        """Moving a function into a class should add one indent level."""
        pp = PythonPostProcessor()
        content = "def helper():\n    return 1\n"
        # Target context: inside a class (depth 1, indented)
        target = Region(file_path="cls.py", start_line=5, end_line=5,
                        content="    def existing(self):\n")
        result = pp.adjust_indentation(content, target)
        assert result == "    def helper():\n        return 1\n"

    def test_no_change_when_already_correct(self):
        pp = PythonPostProcessor()
        content = "def helper():\n    return 1\n"
        target = Region.at("top.py", 1, 1)
        result = pp.adjust_indentation(content, target)
        assert result == content

    def test_deeply_nested_dedent(self):
        pp = PythonPostProcessor()
        content = "        def inner():\n            pass\n"
        target = Region.at("top.py", 1, 1)
        result = pp.adjust_indentation(content, target)
        assert result == "def inner():\n    pass\n"


class TestPostProcessorRegistry:
    def test_get_python(self):
        pp = get_postprocessor("python")
        assert isinstance(pp, PythonPostProcessor)

    def test_get_unknown_returns_none(self):
        assert get_postprocessor("brainfuck") is None

    def test_protocol_compliance(self):
        pp = PythonPostProcessor()
        assert isinstance(pp, PostProcessor)
