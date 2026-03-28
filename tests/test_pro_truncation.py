"""Tests for fledgling-pro token-aware output truncation.

Tests the truncation logic in fledgling.pro.server: head/tail display,
omission messages, max_lines/max_results parameters, and range-param bypass.
"""

import os
import pytest

from fledgling.pro.server import (
    _truncate_rows,
    _format_markdown_table,
    _HEAD_TAIL,
    _MAX_LINES,
    _MAX_ROWS,
    _HINTS,
    _TEXT_FORMAT,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import fastmcp  # noqa: F401
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False

requires_fastmcp = pytest.mark.skipif(
    not HAS_FASTMCP, reason="fastmcp not installed"
)


# ── Unit tests for _truncate_rows ───────────────────────────────────


class TestTruncateRows:
    """Test the core truncation helper."""

    def test_no_truncation_when_under_limit(self):
        rows = list(range(10))
        result, omission = _truncate_rows(rows, 20, "read_source")
        assert result == rows
        assert omission is None

    def test_no_truncation_at_exact_limit(self):
        rows = list(range(50))
        result, omission = _truncate_rows(rows, 50, "find_definitions")
        assert result == rows
        assert omission is None

    def test_truncation_shows_head_and_tail(self):
        rows = list(range(100))
        result, omission = _truncate_rows(rows, 50, "read_source")
        assert result[:_HEAD_TAIL] == list(range(5))
        assert result[-_HEAD_TAIL:] == list(range(95, 100))
        assert len(result) == 2 * _HEAD_TAIL

    def test_omission_message_has_counts(self):
        rows = list(range(100))
        _, omission = _truncate_rows(rows, 50, "read_source")
        assert "90 of 100" in omission

    def test_omission_message_has_hint(self):
        rows = list(range(100))
        _, omission = _truncate_rows(rows, 50, "read_source")
        assert _HINTS["read_source"] in omission

    def test_no_hint_for_unknown_macro(self):
        rows = list(range(20))
        _, omission = _truncate_rows(rows, 10, "unknown_macro")
        assert "omitted" in omission
        # No hint line after the omission message
        assert omission.count("\n") == 0

    def test_zero_limit_means_no_truncation(self):
        rows = list(range(500))
        result, omission = _truncate_rows(rows, 0, "read_source")
        assert result == rows
        assert omission is None

    def test_negative_limit_means_no_truncation(self):
        rows = list(range(500))
        result, omission = _truncate_rows(rows, -1, "read_source")
        assert result == rows
        assert omission is None

    def test_small_total_below_head_tail_threshold(self):
        """When total <= 2 * HEAD_TAIL, return all rows (no overlap)."""
        rows = list(range(8))
        result, omission = _truncate_rows(rows, 5, "read_source")
        assert result == rows
        assert omission is None

    def test_total_exactly_double_head_tail(self):
        """total == 2 * HEAD_TAIL → no truncation (nothing to omit)."""
        rows = list(range(2 * _HEAD_TAIL))
        result, omission = _truncate_rows(rows, 5, "read_source")
        assert result == rows
        assert omission is None

    def test_total_just_above_double_head_tail(self):
        """total == 2 * HEAD_TAIL + 1 → truncation with 1 omitted."""
        rows = list(range(2 * _HEAD_TAIL + 1))
        result, omission = _truncate_rows(rows, 5, "read_source")
        assert len(result) == 2 * _HEAD_TAIL
        assert "1 of 11" in omission


# ── Format constants ────────────────────────────────────────────────


class TestFormatConstants:
    """Verify configuration consistency."""

    def test_file_at_version_is_text_format(self):
        assert "file_at_version" in _TEXT_FORMAT

    def test_all_max_lines_tools_have_hints(self):
        for name in _MAX_LINES:
            assert name in _HINTS, f"{name} missing from _HINTS"

    def test_all_max_rows_tools_have_hints(self):
        for name in _MAX_ROWS:
            assert name in _HINTS, f"{name} missing from _HINTS"


# ── Integration tests via FastMCP server ────────────────────────────


@pytest.fixture(scope="module")
def mcp():
    """Create a fledgling-pro FastMCP server for testing."""
    pytest.importorskip("fastmcp")
    from fledgling.pro.server import create_server
    return create_server(root=PROJECT_ROOT, init=False)


@requires_fastmcp
class TestToolRegistration:
    """Verify truncation parameters appear in tool schemas."""

    def test_read_source_has_max_lines(self, mcp):
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        tool = tools["read_source"]
        param_names = list(tool.parameters.keys())
        assert "max_lines" in param_names

    def test_find_definitions_has_max_results(self, mcp):
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        tool = tools["find_definitions"]
        param_names = list(tool.parameters.keys())
        assert "max_results" in param_names

    def test_help_has_no_truncation_param(self, mcp):
        """Tools not in _MAX_LINES or _MAX_ROWS get no truncation param."""
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        tool = tools["help"]
        param_names = list(tool.parameters.keys())
        assert "max_lines" not in param_names
        assert "max_results" not in param_names


@requires_fastmcp
class TestTextTruncation:
    """Test truncation of text-format tools."""

    @pytest.mark.anyio
    async def test_read_source_truncates_large_file(self, mcp):
        """A file larger than 200 lines gets truncated."""
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        fn = tools["read_source"].fn
        # conftest.py is well over 200 lines
        result = await fn(file_path=f"{PROJECT_ROOT}/tests/conftest.py")
        assert "--- omitted" in result
        assert _HINTS["read_source"] in result

    @pytest.mark.anyio
    async def test_read_source_small_file_no_truncation(self, mcp):
        """A small file comes through untruncated."""
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        fn = tools["read_source"].fn
        result = await fn(file_path=f"{PROJECT_ROOT}/fledgling/pro/__main__.py")
        assert "--- omitted" not in result

    @pytest.mark.anyio
    async def test_read_source_max_lines_zero_disables(self, mcp):
        """max_lines=0 disables truncation."""
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        fn = tools["read_source"].fn
        result = await fn(
            file_path=f"{PROJECT_ROOT}/tests/conftest.py",
            max_lines=0,
        )
        assert "--- omitted" not in result

    @pytest.mark.anyio
    async def test_read_source_explicit_lines_bypasses(self, mcp):
        """Explicit lines param skips truncation."""
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        fn = tools["read_source"].fn
        result = await fn(
            file_path=f"{PROJECT_ROOT}/tests/conftest.py",
            lines="1-500",
        )
        assert "--- omitted" not in result

    @pytest.mark.anyio
    async def test_read_source_match_bypasses(self, mcp):
        """Explicit match param skips truncation."""
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        fn = tools["read_source"].fn
        result = await fn(
            file_path=f"{PROJECT_ROOT}/tests/conftest.py",
            match="def ",
        )
        assert "--- omitted" not in result

    @pytest.mark.anyio
    async def test_read_source_custom_max_lines(self, mcp):
        """Custom max_lines is respected."""
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        fn = tools["read_source"].fn
        result = await fn(
            file_path=f"{PROJECT_ROOT}/tests/conftest.py",
            max_lines=20,
        )
        assert "--- omitted" in result
        lines = result.strip().split("\n")
        # 5 head + omission msg + hint + 5 tail = 12 lines
        assert len(lines) == 12

    @pytest.mark.anyio
    async def test_truncated_text_has_head_and_tail(self, mcp):
        """Truncated output starts with line 1 and ends with the last line."""
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        fn = tools["read_source"].fn
        result = await fn(
            file_path=f"{PROJECT_ROOT}/tests/conftest.py",
            max_lines=20,
        )
        lines = result.strip().split("\n")
        # First line should be line 1 of the file
        assert lines[0].strip().startswith("1")


@requires_fastmcp
class TestMarkdownTruncation:
    """Test truncation of markdown-format (tabular) tools."""

    @pytest.mark.anyio
    async def test_find_definitions_truncates(self, mcp):
        """find_definitions with a small limit truncates."""
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        fn = tools["find_definitions"].fn
        result = await fn(
            file_pattern=f"{PROJECT_ROOT}/**/*.py",
            max_results=15,
        )
        assert "--- omitted" in result
        assert _HINTS["find_definitions"] in result

    @pytest.mark.anyio
    async def test_find_definitions_name_pattern_bypasses(self, mcp):
        """Explicit name_pattern skips truncation."""
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        fn = tools["find_definitions"].fn
        result = await fn(
            file_pattern=f"{PROJECT_ROOT}/**/*.py",
            name_pattern="load%",
        )
        assert "--- omitted" not in result

    @pytest.mark.anyio
    async def test_list_files_truncates(self, mcp):
        """list_files with a small limit truncates."""
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        fn = tools["list_files"].fn
        result = await fn(
            glob_pattern=f"{PROJECT_ROOT}/**/*",
            max_results=15,
        )
        assert "--- omitted" in result
        assert _HINTS["list_files"] in result

    @pytest.mark.anyio
    async def test_markdown_omission_position(self, mcp):
        """Omission message appears after header + head rows in markdown."""
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        fn = tools["list_files"].fn
        result = await fn(
            glob_pattern=f"{PROJECT_ROOT}/**/*",
            max_results=15,
        )
        assert "--- omitted" in result
        lines = result.strip().split("\n")
        # Header line, separator line, 5 head rows, omission, hint, 5 tail rows
        omission_idx = next(
            i for i, l in enumerate(lines) if "--- omitted" in l
        )
        assert omission_idx == 7  # 0:header, 1:sep, 2-6:head, 7:omission

    @pytest.mark.anyio
    async def test_max_results_zero_disables(self, mcp):
        """max_results=0 disables truncation for discovery tools."""
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        fn = tools["recent_changes"].fn
        result = await fn(max_results=0)
        assert "--- omitted" not in result
