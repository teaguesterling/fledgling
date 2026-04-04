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
    text_line_count,
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
    """ReadLines uses text format: each line is '  NN  content'."""

    def test_reads_whole_file(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {"file_path": CONFTEST_PATH})
        assert "import pytest" in text
        assert text_line_count(text) > 50

    def test_reads_line_range(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {
            "file_path": CONFTEST_PATH,
            "lines": "1-5",
        })
        assert text_line_count(text) == 5

    def test_reads_with_context(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {
            "file_path": CONFTEST_PATH,
            "lines": "10",
            "ctx": "2",
        })
        assert text_line_count(text) == 5  # line 10 ± 2

    def test_reads_with_match(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {
            "file_path": CONFTEST_PATH,
            "match": "import",
        })
        lines = [l for l in text.strip().split("\n") if l.strip()]
        assert len(lines) > 0
        for line in lines:
            assert "import" in line.lower()

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
        count = text_line_count(text)
        assert count > 0
        assert count < 20


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


class TestFindInAST:
    """FindInAST uses text format: grep-style file:line  context."""

    def test_finds_calls(self, mcp_server):
        text = call_tool(mcp_server, "FindInAST", {
            "file_pattern": CONFTEST_PATH,
            "kind": "calls",
        })
        assert text_line_count(text) > 0

    def test_finds_imports(self, mcp_server):
        text = call_tool(mcp_server, "FindInAST", {
            "file_pattern": CONFTEST_PATH,
            "kind": "imports",
        })
        assert text_line_count(text) > 0
        assert "import" in text.lower() or "os" in text

    def test_name_filter(self, mcp_server):
        text = call_tool(mcp_server, "FindInAST", {
            "file_pattern": CONFTEST_PATH,
            "kind": "calls",
            "name_pattern": "execute%",
        })
        assert text_line_count(text) > 0
        assert "execute" in text

    def test_grep_style_output(self, mcp_server):
        text = call_tool(mcp_server, "FindInAST", {
            "file_pattern": CONFTEST_PATH,
            "kind": "imports",
        })
        # Each line should be file:line  context
        lines = [l for l in text.strip().split("\n") if l.strip()]
        assert len(lines) > 0
        assert ":" in lines[0]  # file:line format


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


class TestMDOverview:
    def test_default_returns_all_docs(self, mcp_server):
        text = call_tool(mcp_server, "MDOverview", {})
        assert md_row_count(text) > 5
        # Should find markdown files in the project
        assert "README" in text or "SKILL" in text or "CLAUDE" in text

    def test_search_filters(self, mcp_server):
        all_text = call_tool(mcp_server, "MDOverview", {})
        filtered = call_tool(mcp_server, "MDOverview", {"search": "macro"})
        assert md_row_count(filtered) > 0
        assert md_row_count(filtered) < md_row_count(all_text)

    def test_search_no_match(self, mcp_server):
        text = call_tool(mcp_server, "MDOverview", {"search": "xyznonexistent123"})
        assert md_row_count(text) == 0


class TestMDSection:
    """MDSection uses text format: returns raw markdown content."""

    def test_reads_specific_section(self, mcp_server):
        text = call_tool(mcp_server, "MDSection", {
            "file_path": SPEC_PATH,
            "section_id": "architecture",
        })
        # Section content is returned as raw markdown text
        assert len(text.strip()) > 100
        assert "duckdb" in text.lower() or "fledgling" in text.lower()


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


class TestGitDiffFile:
    """GitDiffFile uses text format: unified diff with +/- prefixes."""

    def _find_changed_file(self, mcp_server, from_rev="HEAD~1", to_rev="HEAD"):
        """Find a file that actually changed between two revisions."""
        summary = call_tool(mcp_server, "GitDiffSummary", {
            "from_rev": from_rev,
            "to_rev": to_rev,
        })
        # Parse first data row from markdown table
        for line in summary.strip().split("\n"):
            if "|" in line and "file_path" not in line and "---" not in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if parts:
                    return parts[0]
        return None

    def test_returns_diff_lines(self, mcp_server):
        """Diff of a changed file returns non-empty output."""
        changed = self._find_changed_file(mcp_server)
        assert changed is not None, "No files changed in HEAD~1..HEAD"
        text = call_tool(mcp_server, "GitDiffFile", {
            "file": changed,
            "from_rev": "HEAD~1",
            "to_rev": "HEAD",
        })
        lines = [l for l in text.strip().split("\n") if l.strip()]
        assert len(lines) > 0

    def test_shows_additions_and_removals(self, mcp_server):
        """Diff output contains + or - markers."""
        changed = self._find_changed_file(mcp_server)
        assert changed is not None, "No files changed in HEAD~1..HEAD"
        text = call_tool(mcp_server, "GitDiffFile", {
            "file": changed,
            "from_rev": "HEAD~1",
            "to_rev": "HEAD",
        })
        assert "+" in text or "-" in text


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


# -- Conversations --


class TestChatSessions:
    def test_returns_sessions(self, mcp_server):
        text = call_tool(mcp_server, "ChatSessions", {})
        assert md_row_count(text) == 2

    def test_limit_parameter(self, mcp_server):
        text = call_tool(mcp_server, "ChatSessions", {"limit": "1"})
        assert md_row_count(text) == 1

    def test_project_filter(self, mcp_server):
        text = call_tool(mcp_server, "ChatSessions", {"project": "mcp-test"})
        assert md_row_count(text) == 2

    def test_project_filter_no_match(self, mcp_server):
        text = call_tool(mcp_server, "ChatSessions", {
            "project": "nonexistent-xyz",
        })
        assert md_row_count(text) == 0

    def test_days_filter_wide_window(self, mcp_server):
        """Large days value includes all synthetic data (2025 timestamps)."""
        text = call_tool(mcp_server, "ChatSessions", {"days": "9999"})
        assert md_row_count(text) == 2

    def test_days_filter_narrow_window(self, mcp_server):
        """Narrow days value excludes old synthetic data."""
        text = call_tool(mcp_server, "ChatSessions", {"days": "1"})
        assert md_row_count(text) == 0


class TestChatSearch:
    def test_finds_messages(self, mcp_server):
        text = call_tool(mcp_server, "ChatSearch", {"query": "fix the bug"})
        assert md_row_count(text) >= 1
        assert "fix" in text.lower()

    def test_role_filter(self, mcp_server):
        text = call_tool(mcp_server, "ChatSearch", {
            "query": "auth",
            "role": "assistant",
        })
        rows = md_row_count(text)
        assert rows >= 1
        # All returned rows should be assistant role
        data_lines = [
            l for l in text.strip().split("\n")
            if l.strip().startswith("|")
        ][2:]
        for line in data_lines:
            assert "assistant" in line

    def test_no_results(self, mcp_server):
        text = call_tool(mcp_server, "ChatSearch", {
            "query": "xyznonexistent999",
        })
        assert md_row_count(text) == 0

    def test_days_filter(self, mcp_server):
        text_wide = call_tool(mcp_server, "ChatSearch", {
            "query": "auth", "days": "9999",
        })
        text_narrow = call_tool(mcp_server, "ChatSearch", {
            "query": "auth", "days": "1",
        })
        assert md_row_count(text_wide) >= 1
        assert md_row_count(text_narrow) == 0


class TestChatToolUsage:
    def test_returns_tool_counts(self, mcp_server):
        text = call_tool(mcp_server, "ChatToolUsage", {})
        assert md_row_count(text) >= 2  # At least Bash and Read
        assert "Bash" in text
        assert "Read" in text

    def test_session_filter(self, mcp_server):
        text = call_tool(mcp_server, "ChatToolUsage", {
            "session_id": "sess-001",
        })
        assert md_row_count(text) >= 1
        assert "Bash" in text
        assert "Read" in text

    def test_days_filter(self, mcp_server):
        text_wide = call_tool(mcp_server, "ChatToolUsage", {"days": "9999"})
        text_narrow = call_tool(mcp_server, "ChatToolUsage", {"days": "1"})
        assert md_row_count(text_wide) >= 2
        assert md_row_count(text_narrow) == 0


class TestChatDetail:
    def test_returns_session_detail(self, mcp_server):
        text = call_tool(mcp_server, "ChatDetail", {
            "session_id": "sess-001",
        })
        assert md_row_count(text) >= 1
        assert "fix-auth" in text

    def test_includes_tool_breakdown(self, mcp_server):
        text = call_tool(mcp_server, "ChatDetail", {
            "session_id": "sess-001",
        })
        assert "Bash" in text
        assert "Read" in text
