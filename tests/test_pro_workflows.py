"""Tests for fledgling-pro compound workflow tools.

Tests the compound tools (explore, investigate, review, search) that
orchestrate multiple fledgling macros in a single call.
"""

import asyncio
import os

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import fastmcp  # noqa: F401
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False

requires_fastmcp = pytest.mark.skipif(
    not HAS_FASTMCP, reason="fastmcp not installed"
)


# ── Unit tests for helpers ─────────────────────────────────────────


class TestFormatBriefing:
    """Test the _format_briefing helper."""

    def test_produces_markdown_with_title(self):
        from fledgling.pro.workflows import _format_briefing
        result = _format_briefing("My Title", [("Section A", "content a")])
        assert result.startswith("## My Title")

    def test_sections_have_headings(self):
        from fledgling.pro.workflows import _format_briefing
        result = _format_briefing("T", [
            ("Alpha", "aaa"),
            ("Beta", "bbb"),
        ])
        assert "### Alpha" in result
        assert "### Beta" in result
        assert "aaa" in result
        assert "bbb" in result

    def test_empty_sections_list(self):
        from fledgling.pro.workflows import _format_briefing
        result = _format_briefing("Empty", [])
        assert "## Empty" in result

    def test_section_order_preserved(self):
        from fledgling.pro.workflows import _format_briefing
        result = _format_briefing("T", [
            ("First", "111"),
            ("Second", "222"),
            ("Third", "333"),
        ])
        assert result.index("First") < result.index("Second") < result.index("Third")


class TestSection:
    """Test the _section helper."""

    def test_returns_content_on_success(self):
        from fledgling.pro.workflows import _section
        heading, content = _section("Test", lambda: "hello")
        assert heading == "Test"
        assert content == "hello"

    def test_returns_error_note_on_exception(self):
        from fledgling.pro.workflows import _section
        heading, content = _section("Bad", lambda: 1 / 0)
        assert heading == "Bad"
        assert "could not load" in content.lower()

    def test_returns_no_data_when_empty(self):
        from fledgling.pro.workflows import _section
        heading, content = _section("Empty", lambda: "")
        assert heading == "Empty"
        assert "no data" in content.lower()

    def test_returns_no_data_when_none(self):
        from fledgling.pro.workflows import _section
        heading, content = _section("Nil", lambda: None)
        assert heading == "Nil"
        assert "no data" in content.lower()


class TestHasModule:
    """Test the _has_module helper."""

    def test_detects_loaded_module(self, all_macros):
        from fledgling.pro.workflows import _has_module
        # all_macros loads all modules including "source"
        assert _has_module(all_macros, "source") is True

    def test_rejects_missing_module(self, all_macros):
        from fledgling.pro.workflows import _has_module
        assert _has_module(all_macros, "nonexistent") is False


# ── Integration test helpers ───────────────────────────────────────


def _text(result) -> str:
    """Extract text from a FastMCP ToolResult."""
    return result.content[0].text


@pytest.fixture(scope="module")
def mcp():
    """Create a fledgling-pro FastMCP server for testing."""
    pytest.importorskip("fastmcp")
    from fledgling.pro.server import create_server
    return create_server(root=PROJECT_ROOT, init=False)


def _run_async(coro):
    """Run an async coroutine, avoiding conflicts with pytest-asyncio."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _tool_names(mcp):
    """List all tool names from the server."""
    async def _list():
        from fastmcp import Client
        async with Client(mcp) as client:
            tools = await client.list_tools()
            return [t.name for t in tools]
    return _run_async(_list())


# ── Integration tests: explore ─────────────────────────────────────


@requires_fastmcp
class TestExplore:
    """Test the explore compound tool."""

    @pytest.fixture(scope="class")
    def text(self, mcp):
        return _text(_run_async(mcp.call_tool("explore", {})))

    def test_returns_non_empty(self, text):
        assert len(text) > 0

    def test_contains_languages_section(self, text):
        assert "Languages" in text

    def test_contains_definitions_section(self, text):
        assert "Key Definitions" in text

    def test_contains_documentation_section(self, text):
        assert "Documentation" in text

    def test_contains_recent_activity_section(self, text):
        assert "Recent Activity" in text

    def test_contains_python(self, text):
        """Dog-fooding: fledgling is a Python project."""
        assert "Python" in text

    def test_tool_is_registered(self, mcp):
        assert "explore" in _tool_names(mcp)


# ── Integration tests: investigate ─────────────────────────────────


@requires_fastmcp
class TestInvestigate:
    """Test the investigate compound tool."""

    @pytest.fixture(scope="class")
    def text(self, mcp):
        return _text(_run_async(mcp.call_tool("investigate", {
            "name": "create_server",
        })))

    def test_returns_non_empty(self, text):
        assert len(text) > 0

    def test_contains_definition_section(self, text):
        assert "Definition" in text

    def test_contains_source_section(self, text):
        assert "Source" in text

    def test_contains_called_by_section(self, text):
        assert "Called by" in text

    def test_finds_function_name(self, text):
        assert "create_server" in text

    def test_unknown_name_returns_helpful_message(self, mcp):
        text = _text(_run_async(mcp.call_tool("investigate", {
            "name": "xyznonexistent999",
        })))
        assert "no definition found" in text.lower()

    def test_tool_is_registered(self, mcp):
        assert "investigate" in _tool_names(mcp)


# ── Integration tests: review ──────────────────────────────────────


@requires_fastmcp
class TestReview:
    """Test the review compound tool."""

    @pytest.fixture(scope="class")
    def text(self, mcp):
        return _text(_run_async(mcp.call_tool("review", {})))

    def test_returns_non_empty(self, text):
        assert len(text) > 0

    def test_contains_changed_files_section(self, text):
        assert "Changed Files" in text

    def test_contains_changed_functions_section(self, text):
        assert "Changed Functions" in text

    def test_contains_diff_section(self, text):
        assert "Diff" in text

    def test_tool_is_registered(self, mcp):
        assert "review" in _tool_names(mcp)


# ── Integration tests: search ──────────────────────────────────────


@requires_fastmcp
class TestSearch:
    """Test the search compound tool."""

    @pytest.fixture(scope="class")
    def text(self, mcp):
        return _text(_run_async(mcp.call_tool("search", {
            "query": "create_server",
        })))

    def test_returns_non_empty(self, text):
        assert len(text) > 0

    def test_contains_definitions_section(self, text):
        assert "Definitions" in text

    def test_contains_call_sites_section(self, text):
        assert "Call Sites" in text

    def test_contains_documentation_section(self, text):
        assert "Documentation" in text

    def test_finds_search_term(self, text):
        assert "create_server" in text

    def test_no_results_returns_structured_output(self, mcp):
        text = _text(_run_async(mcp.call_tool("search", {
            "query": "xyznonexistent999",
        })))
        assert len(text) > 0
        assert "Search" in text

    def test_tool_is_registered(self, mcp):
        assert "search" in _tool_names(mcp)


# ── Graceful degradation tests ─────────────────────────────────────


@requires_fastmcp
class TestGracefulDegradation:
    """Test that compound tools work with partial module sets."""

    @pytest.fixture(scope="class")
    def partial_mcp(self):
        """Server with only source + code modules (no git, no docs)."""
        from fledgling.pro.server import create_server
        return create_server(root=PROJECT_ROOT, init=False,
                             modules=["source", "code"])

    def test_explore_without_git_or_docs(self, partial_mcp):
        """explore returns partial briefing when git/docs unavailable."""
        text = _text(_run_async(partial_mcp.call_tool("explore", {})))
        assert "Languages" in text
        # Should still have section headings even if content failed
        assert "Explore" in text

    def test_search_without_conversations(self, partial_mcp):
        """search skips conversations section gracefully."""
        text = _text(_run_async(partial_mcp.call_tool("search", {
            "query": "test",
        })))
        assert "Search" in text
        assert "Definitions" in text
