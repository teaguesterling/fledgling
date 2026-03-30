# tests/test_edit_mcp.py
"""Tests for MCP tool registration (integration)."""

import asyncio
import os
import pytest

# Skip if fastmcp not available
fastmcp = pytest.importorskip("fastmcp")

from fledgling.edit.mcp import register_edit_tools


@pytest.fixture
def mcp_server(tmp_path):
    """FastMCP server with edit tools registered."""
    import duckdb
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    con = duckdb.connect(":memory:")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD read_lines")
    sql_dir = os.path.join(PROJECT_ROOT, "sql")
    for f in ["source.sql", "code.sql"]:
        _load_sql(con, os.path.join(sql_dir, f))

    mcp = fastmcp.FastMCP("test-edit")
    register_edit_tools(mcp, con)
    return mcp


def _load_sql(con, path):
    with open(path) as f:
        sql = f.read()
    lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
    cleaned = "\n".join(lines)
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt + ";")


class TestEditToolsRegistered:
    def test_tools_are_registered(self, mcp_server):
        tool_names = [t.name for t in asyncio.run(mcp_server.list_tools())]
        assert "EditDefinition" in tool_names
        assert "RemoveDefinition" in tool_names
        assert "MoveDefinition" in tool_names
        assert "RenameSymbol" in tool_names
        assert "MatchReplace" in tool_names
