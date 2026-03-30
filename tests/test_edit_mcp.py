# tests/test_edit_mcp.py
"""Tests for MCP tool registration (integration)."""

import asyncio
import os
import pytest

# Skip if fastmcp not available
fastmcp = pytest.importorskip("fastmcp")

import duckdb
from conftest import load_sql
from fledgling.edit.mcp import register_edit_tools


@pytest.fixture(scope="module")
def _event_loop():
    """Module-scoped event loop to avoid per-test overhead."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mcp_server(tmp_path):
    """FastMCP server with edit tools registered."""
    con = duckdb.connect(":memory:")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD read_lines")
    for f in ["source.sql", "code.sql"]:
        load_sql(con, f)

    mcp = fastmcp.FastMCP("test-edit")
    register_edit_tools(mcp, con)
    return mcp


class TestEditToolsRegistered:
    def test_tools_are_registered(self, mcp_server, _event_loop):
        tool_names = [
            t.name for t in _event_loop.run_until_complete(mcp_server.list_tools())
        ]
        assert "EditDefinition" in tool_names
        assert "RemoveDefinition" in tool_names
        assert "MoveDefinition" in tool_names
        assert "RenameSymbol" in tool_names
        assert "MatchReplace" in tool_names
