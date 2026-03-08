"""Tests for conversation intelligence MCP tools.

Tests the standalone conversation MCP server: tool publication, parameter
handling, and end-to-end execution. Underlying macro behavior is covered
by test_conversations.py.
"""

import json
import os

import duckdb
import pytest

from conftest import (
    CONVERSATION_RECORDS, PROJECT_ROOT,
    call_tool, load_sql, md_row_count,
)


@pytest.fixture(scope="module")
def conversations_mcp_server(tmp_path_factory):
    """Standalone conversation MCP server via memory transport."""
    # Write synthetic conversation data
    base_dir = tmp_path_factory.mktemp("conv_mcp")
    conv_dir = base_dir / ".claude" / "projects" / "mcp-test-project"
    conv_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = conv_dir / "conversations.jsonl"
    with open(jsonl_path, "w") as f:
        for record in CONVERSATION_RECORDS:
            f.write(json.dumps(record) + "\n")

    con = duckdb.connect(":memory:")
    con.execute("LOAD duckdb_mcp")
    # Bootstrap conversation data
    con.execute(f"""
        CREATE TABLE raw_conversations AS
        SELECT *, filename AS _source_file
        FROM read_json_auto(
            '{jsonl_path}', union_by_name=true,
            maximum_object_size=33554432, filename=true
        )
    """)
    load_sql(con, "conversations.sql")
    load_sql(con, "tools/conversations.sql")
    # Start server (analyst-like: enable built-in tools)
    con.execute("""
        SET VARIABLE mcp_server_options = '{
            "tool_options": {"enable_query": true,
                             "enable_describe": true,
                             "enable_list_tables": true}
        }'
    """)
    con.execute(
        "SELECT mcp_server_start('memory',"
        " getvariable('mcp_server_options'))"
    )
    yield con
    con.close()


class TestChatSessions:
    def test_returns_sessions(self, conversations_mcp_server):
        text = call_tool(conversations_mcp_server, "ChatSessions", {})
        assert md_row_count(text) == 2

    def test_limit_parameter(self, conversations_mcp_server):
        text = call_tool(conversations_mcp_server, "ChatSessions", {"limit": "1"})
        assert md_row_count(text) == 1

    def test_project_filter(self, conversations_mcp_server):
        text = call_tool(conversations_mcp_server, "ChatSessions", {"project": "mcp-test"})
        assert md_row_count(text) == 2

    def test_project_filter_no_match(self, conversations_mcp_server):
        text = call_tool(conversations_mcp_server, "ChatSessions", {
            "project": "nonexistent-xyz",
        })
        assert md_row_count(text) == 0

    def test_days_filter_wide_window(self, conversations_mcp_server):
        """Large days value includes all synthetic data (2025 timestamps)."""
        text = call_tool(conversations_mcp_server, "ChatSessions", {"days": "9999"})
        assert md_row_count(text) == 2

    def test_days_filter_narrow_window(self, conversations_mcp_server):
        """Narrow days value excludes old synthetic data."""
        text = call_tool(conversations_mcp_server, "ChatSessions", {"days": "1"})
        assert md_row_count(text) == 0


class TestChatSearch:
    def test_finds_messages(self, conversations_mcp_server):
        text = call_tool(conversations_mcp_server, "ChatSearch", {"query": "fix the bug"})
        assert md_row_count(text) >= 1
        assert "fix" in text.lower()

    def test_role_filter(self, conversations_mcp_server):
        text = call_tool(conversations_mcp_server, "ChatSearch", {
            "query": "auth",
            "role": "assistant",
        })
        rows = md_row_count(text)
        assert rows >= 1
        data_lines = [
            l for l in text.strip().split("\n")
            if l.strip().startswith("|")
        ][2:]
        for line in data_lines:
            assert "assistant" in line

    def test_no_results(self, conversations_mcp_server):
        text = call_tool(conversations_mcp_server, "ChatSearch", {
            "query": "xyznonexistent999",
        })
        assert md_row_count(text) == 0

    def test_days_filter(self, conversations_mcp_server):
        text_wide = call_tool(conversations_mcp_server, "ChatSearch", {
            "query": "auth", "days": "9999",
        })
        text_narrow = call_tool(conversations_mcp_server, "ChatSearch", {
            "query": "auth", "days": "1",
        })
        assert md_row_count(text_wide) >= 1
        assert md_row_count(text_narrow) == 0


class TestChatToolUsage:
    def test_returns_tool_counts(self, conversations_mcp_server):
        text = call_tool(conversations_mcp_server, "ChatToolUsage", {})
        assert md_row_count(text) >= 2
        assert "Bash" in text
        assert "Read" in text

    def test_session_filter(self, conversations_mcp_server):
        text = call_tool(conversations_mcp_server, "ChatToolUsage", {
            "session_id": "sess-001",
        })
        assert md_row_count(text) >= 1
        assert "Bash" in text
        assert "Read" in text

    def test_days_filter(self, conversations_mcp_server):
        text_wide = call_tool(conversations_mcp_server, "ChatToolUsage", {"days": "9999"})
        text_narrow = call_tool(conversations_mcp_server, "ChatToolUsage", {"days": "1"})
        assert md_row_count(text_wide) >= 2
        assert md_row_count(text_narrow) == 0


class TestChatDetail:
    def test_returns_session_detail(self, conversations_mcp_server):
        text = call_tool(conversations_mcp_server, "ChatDetail", {
            "session_id": "sess-001",
        })
        assert md_row_count(text) >= 1
        assert "fix-auth" in text

    def test_includes_tool_breakdown(self, conversations_mcp_server):
        text = call_tool(conversations_mcp_server, "ChatDetail", {
            "session_id": "sess-001",
        })
        assert "Bash" in text
        assert "Read" in text
