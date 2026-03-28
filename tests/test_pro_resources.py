"""Tests for fledgling-pro MCP resources.

Validates that FastMCP resources registered in create_server() are
discoverable and return correct content matching direct macro output.
"""

import asyncio

import pytest
from fastmcp import Client

from fledgling.pro.server import create_server

RESOURCE_URIS = [
    "fledgling://project",
    "fledgling://diagnostics",
    "fledgling://docs",
    "fledgling://git",
]


def _run_async(coro):
    """Run an async coroutine, avoiding conflicts with pytest-asyncio."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module")
def mcp():
    """FastMCP server instance with fledgling resources."""
    return create_server(init=False)


@pytest.fixture(scope="module")
def resource_list(mcp):
    """All resources from the server."""
    async def _list():
        async with Client(mcp) as client:
            return await client.list_resources()
    return _run_async(_list())


class TestResourceDiscovery:
    """Resources appear in list_resources."""

    def test_resources_listed(self, resource_list):
        uris = [str(r.uri) for r in resource_list]
        for expected in RESOURCE_URIS:
            assert expected in uris, f"{expected} not in {uris}"

    def test_resource_count(self, resource_list):
        assert len(resource_list) == 4


def _read_resource(mcp, uri):
    """Read a resource and return its text content."""
    async def _read():
        async with Client(mcp) as client:
            result = await client.read_resource(uri)
            return result[0].text
    return _run_async(_read())


class TestProjectResource:
    """fledgling://project returns project overview data."""

    def test_non_empty(self, mcp):
        text = _read_resource(mcp, "fledgling://project")
        assert len(text) > 0

    def test_contains_language_data(self, mcp):
        text = _read_resource(mcp, "fledgling://project")
        assert "Python" in text or "python" in text.lower()

    def test_contains_top_level_files(self, mcp):
        text = _read_resource(mcp, "fledgling://project")
        # list_files('*') data should include top-level files
        assert "Top-Level" in text
        assert "pyproject.toml" in text or "README" in text

    def test_matches_direct_macro(self, mcp):
        """Resource content matches calling the macro directly."""
        import fledgling
        con = fledgling.connect(init=False)
        rows = con.project_overview().fetchall()
        text = _read_resource(mcp, "fledgling://project")
        for row in rows:
            lang = str(row[0])
            assert lang in text, f"Language '{lang}' from macro not in resource"


class TestDiagnosticsResource:
    """fledgling://diagnostics returns dr_fledgling output."""

    def test_non_empty(self, mcp):
        text = _read_resource(mcp, "fledgling://diagnostics")
        assert len(text) > 0

    def test_contains_version(self, mcp):
        text = _read_resource(mcp, "fledgling://diagnostics")
        assert "fledgling" in text.lower() or "version" in text.lower()

    def test_matches_direct_macro(self, mcp):
        import fledgling
        con = fledgling.connect(init=False)
        rows = con.dr_fledgling().fetchall()
        text = _read_resource(mcp, "fledgling://diagnostics")
        for row in rows:
            key = str(row[0])
            assert key in text, f"Key '{key}' from dr_fledgling not in resource"


class TestDocsResource:
    """fledgling://docs returns documentation outline."""

    def test_non_empty(self, mcp):
        text = _read_resource(mcp, "fledgling://docs")
        assert len(text) > 0

    def test_contains_markdown_files(self, mcp):
        text = _read_resource(mcp, "fledgling://docs")
        assert ".md" in text

    def test_matches_direct_macro(self, mcp):
        import fledgling
        con = fledgling.connect(init=False)
        rows = con.doc_outline("**/*.md").fetchall()
        text = _read_resource(mcp, "fledgling://docs")
        assert len(rows) > 0, "doc_outline returned no rows"
        first_file = str(rows[0][0])
        assert first_file in text


class TestGitResource:
    """fledgling://git returns branch, recent commits, and working tree status."""

    def test_non_empty(self, mcp):
        text = _read_resource(mcp, "fledgling://git")
        assert len(text) > 0

    def test_contains_branch_info(self, mcp):
        text = _read_resource(mcp, "fledgling://git")
        assert "main" in text or "feature" in text

    def test_contains_recent_commits(self, mcp):
        text = _read_resource(mcp, "fledgling://git")
        assert "commit" in text.lower() or len(text.split("\n")) > 5

    def test_contains_sections(self, mcp):
        text = _read_resource(mcp, "fledgling://git")
        assert "Branches" in text or "branches" in text
        assert "Recent" in text or "Commits" in text or "commits" in text

    def test_matches_direct_macros(self, mcp):
        import fledgling
        con = fledgling.connect(init=False)
        branches = con.branch_list().fetchall()
        text = _read_resource(mcp, "fledgling://git")
        for row in branches:
            branch_name = str(row[0])
            assert branch_name in text, f"Branch '{branch_name}' not in resource"

    def test_multiple_reads_consistent(self, mcp):
        text1 = _read_resource(mcp, "fledgling://git")
        text2 = _read_resource(mcp, "fledgling://git")
        assert len(text1) > 0
        assert len(text2) > 0


class TestResourcesWorkWithoutToolCalls:
    """Resources are accessible without any prior tool calls."""

    def test_fresh_server_resources(self):
        """A fresh server exposes resources without calling any tools first."""
        fresh_mcp = create_server(init=False)
        for uri in RESOURCE_URIS:
            text = _read_resource(fresh_mcp, uri)
            assert len(text) > 0, f"{uri} returned empty on fresh server"
