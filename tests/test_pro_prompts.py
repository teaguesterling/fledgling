"""Tests for fledgling-pro MCP prompt templates.

Validates that FastMCP prompts registered in create_server() are
discoverable, return non-empty content with workflow instructions and
live project data, and handle missing data gracefully.
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


def _run_async(coro):
    """Run an async coroutine, avoiding conflicts with pytest-asyncio."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module")
def mcp():
    """FastMCP server instance with fledgling prompts."""
    pytest.importorskip("fastmcp")
    from fledgling.pro.server import create_server
    return create_server(root=PROJECT_ROOT, init=False)


def _list_prompts(mcp):
    """List all prompts from the server."""
    async def _list():
        from fastmcp import Client
        async with Client(mcp) as client:
            return await client.list_prompts()
    return _run_async(_list())


def _get_prompt(mcp, name, arguments=None):
    """Get a prompt result and return the text content."""
    async def _get():
        from fastmcp import Client
        async with Client(mcp) as client:
            result = await client.get_prompt(name, arguments or {})
            return result.messages[0].content.text
    return _run_async(_get())


# ── Discovery tests ───────────────────────────────────────────────


@requires_fastmcp
class TestPromptDiscovery:
    """Prompts appear in list_prompts with correct metadata."""

    @pytest.fixture(scope="class")
    def prompts(self, mcp):
        return _list_prompts(mcp)

    def test_explore_listed(self, prompts):
        names = [p.name for p in prompts]
        assert "explore" in names

    def test_investigate_listed(self, prompts):
        names = [p.name for p in prompts]
        assert "investigate" in names

    def test_review_listed(self, prompts):
        names = [p.name for p in prompts]
        assert "review" in names

    def test_explore_has_optional_path_arg(self, prompts):
        p = next(p for p in prompts if p.name == "explore")
        args = {a.name: a.required for a in (p.arguments or [])}
        assert "path" in args
        assert args["path"] is False

    def test_investigate_has_required_symptom_arg(self, prompts):
        p = next(p for p in prompts if p.name == "investigate")
        args = {a.name: a.required for a in (p.arguments or [])}
        assert "symptom" in args
        assert args["symptom"] is True

    def test_review_has_optional_rev_args(self, prompts):
        p = next(p for p in prompts if p.name == "review")
        args = {a.name: a.required for a in (p.arguments or [])}
        assert "from_rev" in args
        assert args["from_rev"] is False
        assert "to_rev" in args
        assert args["to_rev"] is False

    def test_prompts_have_descriptions(self, prompts):
        for p in prompts:
            assert p.description and len(p.description) > 10


# ── explore prompt tests ──────────────────────────────────────────


@requires_fastmcp
class TestExplorePrompt:
    """explore prompt returns workflow instructions with live data."""

    @pytest.fixture(scope="class")
    def text(self, mcp):
        return _get_prompt(mcp, "explore")

    def test_non_empty(self, text):
        assert len(text) > 100

    def test_contains_workflow_instructions(self, text):
        assert "Phase 1" in text or "Landscape" in text
        assert "Phase 2" in text or "Architecture" in text

    def test_contains_live_data(self, text):
        # fledgling is a Python project — live data should show it
        assert "Languages" in text
        assert "Python" in text

    def test_contains_tool_suggestions(self, text):
        assert "CodeStructure" in text or "FindDefinitions" in text

    def test_with_path_argument(self, mcp):
        text = _get_prompt(mcp, "explore", {"path": "fledgling"})
        assert len(text) > 100
        assert "fledgling" in text


# ── investigate prompt tests ──────────────────────────────────────


@requires_fastmcp
class TestInvestigatePrompt:
    """investigate prompt returns workflow with pre-found data."""

    @pytest.fixture(scope="class")
    def text(self, mcp):
        return _get_prompt(mcp, "investigate", {"symptom": "create_server"})

    def test_non_empty(self, text):
        assert len(text) > 100

    def test_contains_workflow_instructions(self, text):
        assert "Step 1" in text or "Locate" in text
        assert "Step 2" in text or "Understand" in text

    def test_contains_live_data(self, text):
        assert "create_server" in text
        assert "Definition" in text

    def test_contains_symptom_in_header(self, text):
        assert "create_server" in text

    def test_unknown_symptom_returns_instructions(self, mcp):
        text = _get_prompt(mcp, "investigate", {"symptom": "xyznonexistent999"})
        assert len(text) > 50
        # Should still have workflow steps even if no definition found
        assert "Step 1" in text or "Locate" in text or "no definition found" in text.lower()


# ── review prompt tests ───────────────────────────────────────────


@requires_fastmcp
class TestReviewPrompt:
    """review prompt returns checklist with change data."""

    @pytest.fixture(scope="class")
    def text(self, mcp):
        return _get_prompt(mcp, "review")

    def test_non_empty(self, text):
        assert len(text) > 100

    def test_contains_workflow_instructions(self, text):
        assert "Step 1" in text or "File-Level" in text
        assert "Step 2" in text or "Function-Level" in text

    def test_contains_live_data(self, text):
        assert "Changed Files" in text or "Changed Functions" in text

    def test_contains_rev_range(self, text):
        assert "HEAD" in text

    def test_with_rev_arguments(self, mcp):
        text = _get_prompt(mcp, "review", {
            "from_rev": "HEAD~3",
            "to_rev": "HEAD",
        })
        assert len(text) > 100
        assert "HEAD~3" in text


# ── Graceful degradation tests ────────────────────────────────────


@requires_fastmcp
class TestGracefulDegradation:
    """Prompts return instructions even with partial module sets."""

    @pytest.fixture(scope="class")
    def partial_mcp(self):
        """Server with only source + code modules (no git, no docs)."""
        from fledgling.pro.server import create_server
        return create_server(root=PROJECT_ROOT, init=False,
                             modules=["source", "code"])

    def test_explore_without_git_or_docs(self, partial_mcp):
        text = _get_prompt(partial_mcp, "explore")
        assert len(text) > 100
        # Workflow instructions present even without full data
        assert "Phase 1" in text or "Landscape" in text

    def test_review_without_git(self, partial_mcp):
        text = _get_prompt(partial_mcp, "review")
        assert len(text) > 100
        assert "Step 1" in text or "File-Level" in text
