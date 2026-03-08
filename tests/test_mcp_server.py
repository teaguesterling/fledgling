"""Tests for MCP server tool publication and execution.

Tests the MCP transport layer: tool discovery, parameter handling, and
end-to-end tool execution via memory transport. Underlying macro behavior
is covered by tier-specific tests (test_source.py, test_code.py, etc.).

Uses the repo itself as test data (dog-fooding).
"""

import os

import pytest

from conftest import (
    CONFTEST_PATH, SPEC_PATH, V1_TOOLS,
    call_tool, json_row_count, list_tools, md_row_count, parse_json_rows,
)

# sitting_duck test data for multi-language coverage.
# Set SITTING_DUCK_DATA env var to override the default path.
SITTING_DUCK_DATA = os.environ.get(
    "SITTING_DUCK_DATA",
    os.path.expanduser("~/Projects/sitting_duck/main/test/data"),
)
JS_SIMPLE = os.path.join(SITTING_DUCK_DATA, "javascript/simple.js")
RUST_SIMPLE = os.path.join(SITTING_DUCK_DATA, "rust/simple.rs")
GO_SIMPLE = os.path.join(SITTING_DUCK_DATA, "go/simple.go")
PY_SIMPLE = os.path.join(SITTING_DUCK_DATA, "python/simple.py")

_has_sitting_duck_data = os.path.isdir(SITTING_DUCK_DATA)


# -- Tool Discovery --


class TestToolDiscovery:
    def test_all_v1_tools_listed(self, mcp_server):
        names = {t["name"] for t in list_tools(mcp_server)}
        for tool in V1_TOOLS:
            assert tool in names, f"Missing tool: {tool}"

    def test_tool_has_description(self, mcp_server):
        for tool in list_tools(mcp_server):
            if tool["name"] in V1_TOOLS:
                assert tool["description"], f"{tool['name']} has empty description"

    def test_tool_has_input_schema(self, mcp_server):
        for tool in list_tools(mcp_server):
            if tool["name"] in V1_TOOLS:
                schema = tool["inputSchema"]
                assert schema["type"] == "object"
                assert "properties" in schema

    def test_query_tool_available(self, mcp_server):
        names = {t["name"] for t in list_tools(mcp_server)}
        assert "query" in names


# -- Files --


class TestReadLines:
    def test_reads_whole_file(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {"file_path": CONFTEST_PATH})
        assert "import pytest" in text
        assert json_row_count(text) > 50

    def test_reads_line_range(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {
            "file_path": CONFTEST_PATH,
            "lines": "1-5",
        })
        assert json_row_count(text) == 5

    def test_reads_with_context(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {
            "file_path": CONFTEST_PATH,
            "lines": "10",
            "ctx": "2",
        })
        assert json_row_count(text) == 5  # line 10 ± 2

    def test_reads_with_match(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {
            "file_path": CONFTEST_PATH,
            "match": "import",
        })
        rows = parse_json_rows(text, ["line_number", "content"])
        assert len(rows) > 0
        # Every returned row should contain the match term
        for row in rows:
            assert "import" in row["content"].lower()

    def test_reads_git_version(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {
            "file_path": "sql/source.sql",
            "commit": "HEAD",
        })
        assert "read_source" in text

    def test_match_and_lines_compose(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {
            "file_path": CONFTEST_PATH,
            "lines": "1-20",
            "match": "import",
        })
        rows = json_row_count(text)
        assert rows > 0
        assert rows < 20


# -- Code --


class TestFindDefinitions:
    def test_finds_python_functions(self, mcp_server):
        text = call_tool(mcp_server, "FindDefinitions", {
            "file_pattern": CONFTEST_PATH,
        })
        assert "load_sql" in text

    def test_filters_by_name(self, mcp_server):
        text_filtered = call_tool(mcp_server, "FindDefinitions", {
            "file_pattern": CONFTEST_PATH,
            "name_pattern": "load%",
        })
        text_all = call_tool(mcp_server, "FindDefinitions", {
            "file_pattern": CONFTEST_PATH,
        })
        assert "load_sql" in text_filtered
        assert md_row_count(text_filtered) < md_row_count(text_all)


class TestCodeStructure:
    def test_returns_overview(self, mcp_server):
        text = call_tool(mcp_server, "CodeStructure", {
            "file_pattern": CONFTEST_PATH,
        })
        assert "load_sql" in text
        assert md_row_count(text) > 0


# -- Code: Multi-language (sitting_duck test data) --

_skip_no_data = pytest.mark.skipif(
    not _has_sitting_duck_data,
    reason="sitting_duck test data not found",
)


@_skip_no_data
class TestCodeToolsJavaScript:
    def test_find_definitions(self, mcp_server):
        text = call_tool(mcp_server, "FindDefinitions", {
            "file_pattern": JS_SIMPLE,
        })
        assert "hello" in text
        assert "Calculator" in text
        assert "fetchData" in text

    def test_code_structure(self, mcp_server):
        text = call_tool(mcp_server, "CodeStructure", {
            "file_pattern": JS_SIMPLE,
        })
        assert "Calculator" in text
        assert md_row_count(text) > 0


@_skip_no_data
class TestCodeToolsRust:
    def test_find_definitions(self, mcp_server):
        text = call_tool(mcp_server, "FindDefinitions", {
            "file_pattern": RUST_SIMPLE,
        })
        assert "User" in text
        assert "create_user" in text

    def test_find_definitions_filter(self, mcp_server):
        text = call_tool(mcp_server, "FindDefinitions", {
            "file_pattern": RUST_SIMPLE,
            "name_pattern": "create%",
        })
        assert "create_user" in text
        assert md_row_count(text) >= 1

    def test_code_structure(self, mcp_server):
        text = call_tool(mcp_server, "CodeStructure", {
            "file_pattern": RUST_SIMPLE,
        })
        assert "User" in text
        assert "Status" in text


@_skip_no_data
class TestCodeToolsGo:
    def test_find_definitions(self, mcp_server):
        text = call_tool(mcp_server, "FindDefinitions", {
            "file_pattern": GO_SIMPLE,
        })
        assert "Hello" in text
        assert "main" in text

    def test_code_structure(self, mcp_server):
        text = call_tool(mcp_server, "CodeStructure", {
            "file_pattern": GO_SIMPLE,
        })
        assert "Hello" in text
        assert md_row_count(text) > 0


@_skip_no_data
class TestCodeToolsPython:
    """Tests using sitting_duck's controlled Python test fixtures."""

    def test_find_definitions(self, mcp_server):
        text = call_tool(mcp_server, "FindDefinitions", {
            "file_pattern": PY_SIMPLE,
        })
        assert "hello" in text
        assert "MyClass" in text

    def test_code_structure(self, mcp_server):
        text = call_tool(mcp_server, "CodeStructure", {
            "file_pattern": PY_SIMPLE,
        })
        assert "MyClass" in text
        assert md_row_count(text) > 0


# -- Docs --


class TestMDSection:
    def test_reads_specific_section(self, mcp_server):
        text = call_tool(mcp_server, "MDSection", {
            "file_path": SPEC_PATH,
            "section_id": "architecture",
        })
        assert "architecture" in text.lower()


# -- Git --


class TestGitShow:
    def test_returns_file_at_head(self, mcp_server):
        text = call_tool(mcp_server, "GitShow", {
            "file": "LICENSE",
            "rev": "HEAD",
        })
        assert json_row_count(text) >= 1
        assert "LICENSE" in text

    def test_returns_metadata_columns(self, mcp_server):
        text = call_tool(mcp_server, "GitShow", {
            "file": "LICENSE",
            "rev": "HEAD",
        })
        # Parse and verify all expected columns are present
        expected_keys = ["file_path", "ref", "size_bytes", "content"]
        rows = parse_json_rows(text, expected_keys)
        assert len(rows) >= 1
        for col in expected_keys:
            assert rows[0][col] is not None

    def test_returns_file_at_prior_revision(self, mcp_server):
        text = call_tool(mcp_server, "GitShow", {
            "file": "LICENSE",
            "rev": "HEAD~1",
        })
        assert json_row_count(text) >= 1
        assert "LICENSE" in text


# -- Help --


class TestHelp:
    def test_outline_returns_sections(self, mcp_server):
        text = call_tool(mcp_server, "Help", {})
        assert md_row_count(text) > 5

    def test_section_returns_content(self, mcp_server):
        text = call_tool(mcp_server, "Help", {"section": "workflows"})
        assert "workflows" in text.lower()
        assert md_row_count(text) >= 1


class TestGitDiffSummary:
    def test_returns_changed_files(self, mcp_server):
        text = call_tool(mcp_server, "GitDiffSummary", {
            "from_rev": "HEAD~1",
            "to_rev": "HEAD",
        })
        assert md_row_count(text) >= 1

    def test_shows_status(self, mcp_server):
        text = call_tool(mcp_server, "GitDiffSummary", {
            "from_rev": "HEAD~1",
            "to_rev": "HEAD",
        })
        assert any(s in text for s in ("added", "deleted", "modified"))
