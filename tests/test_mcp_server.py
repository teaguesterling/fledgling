"""Tests for MCP server tool publication and execution.

Tests the MCP transport layer: tool discovery, parameter handling, and
end-to-end tool execution via memory transport. Underlying macro behavior
is covered by tier-specific tests (test_source.py, test_code.py, etc.).

Uses the repo itself as test data (dog-fooding).
"""

import json
import os

import pytest

from conftest import CONFTEST_PATH, PROJECT_ROOT, SPEC_PATH

# sitting_duck test data for multi-language coverage.
# Set SITTING_DUCK_DATA env var to override the default path.
SITTING_DUCK_DATA = os.environ.get(
    "SITTING_DUCK_DATA",
    os.path.expanduser("~/Projects/sitting_duck/main/test/data"),
)
JS_SIMPLE = os.path.join(SITTING_DUCK_DATA, "javascript/simple.js")
JS_IMPORTS = os.path.join(SITTING_DUCK_DATA, "javascript/imports.js")
RUST_SIMPLE = os.path.join(SITTING_DUCK_DATA, "rust/simple.rs")
RUST_IMPORTS = os.path.join(SITTING_DUCK_DATA, "rust/imports.rs")
GO_SIMPLE = os.path.join(SITTING_DUCK_DATA, "go/simple.go")
PY_SIMPLE = os.path.join(SITTING_DUCK_DATA, "python/simple.py")
PY_IMPORTS = os.path.join(SITTING_DUCK_DATA, "python/imports.py")

_has_sitting_duck_data = os.path.isdir(SITTING_DUCK_DATA)

# The 16 V1 tools that should be published
V1_TOOLS = [
    "ListFiles",
    "ReadLines",
    "ReadAsTable",
    "FindDefinitions",
    "FindCalls",
    "FindImports",
    "CodeStructure",
    "MDOutline",
    "MDSection",
    "GitChanges",
    "GitBranches",
    "Help",
    "ChatSessions",
    "ChatSearch",
    "ChatToolUsage",
    "ChatDetail",
]


# -- Helpers --


def mcp_request(con, method, params=None):
    """Send a JSON-RPC request to the MCP memory transport server."""
    request = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    })
    raw = con.execute(
        "SELECT mcp_server_send_request(?)", [request]
    ).fetchone()[0]
    return json.loads(raw)


def list_tools(con):
    """Return the list of tool descriptors from the MCP server."""
    resp = mcp_request(con, "tools/list")
    return resp["result"]["tools"]


_mcp_schemas_cache = {}


def call_tool(con, tool_name, arguments=None):
    """Call an MCP tool and return the text content.

    Automatically fills missing optional parameters with null to work
    around duckdb_mcp#19 (omitted params aren't substituted with NULL).
    Tool SQL templates use NULLIF($param, 'null') to convert back.
    """
    args = dict(arguments or {})

    # Auto-fill missing params with null using cached tool schemas.
    # Keyed on connection id so multiple connections don't cross-pollinate.
    con_id = id(con)
    if con_id not in _mcp_schemas_cache:
        _mcp_schemas_cache[con_id] = {
            t["name"]: t["inputSchema"] for t in list_tools(con)
        }
    schema = _mcp_schemas_cache[con_id].get(tool_name, {})
    for prop in schema.get("properties", {}):
        if prop not in args:
            args[prop] = None

    resp = mcp_request(con, "tools/call", {
        "name": tool_name,
        "arguments": args,
    })
    assert "error" not in resp, (
        f"Tool {tool_name} error: {resp['error']['message']}"
    )
    return resp["result"]["content"][0]["text"]


def md_row_count(text):
    """Count data rows in a markdown table (excludes header + separator)."""
    lines = [l for l in text.strip().split("\n") if l.strip().startswith("|")]
    return max(0, len(lines) - 2)


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


class TestListFiles:
    def test_lists_files_by_glob(self, mcp_server):
        pattern = os.path.join(PROJECT_ROOT, "sql/*.sql")
        text = call_tool(mcp_server, "ListFiles", {"pattern": pattern})
        assert "source.sql" in text
        assert "code.sql" in text

    def test_lists_git_files(self, mcp_server):
        text = call_tool(mcp_server, "ListFiles", {
            "pattern": "sql/%",
            "commit": "HEAD",
        })
        assert "source.sql" in text

    def test_no_matches_returns_empty(self, mcp_server):
        pattern = os.path.join(PROJECT_ROOT, "nonexistent_xyz_/*.foo")
        text = call_tool(mcp_server, "ListFiles", {"pattern": pattern})
        assert md_row_count(text) == 0


class TestReadLines:
    def test_reads_whole_file(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {"file_path": CONFTEST_PATH})
        assert "import pytest" in text
        assert md_row_count(text) > 50

    def test_reads_line_range(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {
            "file_path": CONFTEST_PATH,
            "lines": "1-5",
        })
        assert md_row_count(text) == 5

    def test_reads_with_context(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {
            "file_path": CONFTEST_PATH,
            "lines": "10",
            "ctx": "2",
        })
        assert md_row_count(text) == 5  # line 10 ± 2

    def test_reads_with_match(self, mcp_server):
        text = call_tool(mcp_server, "ReadLines", {
            "file_path": CONFTEST_PATH,
            "match": "import",
        })
        rows = md_row_count(text)
        assert rows > 0
        # Every data row should contain the match term
        data_lines = text.strip().split("\n")[2:]
        for line in data_lines:
            if line.strip().startswith("|"):
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
        rows = md_row_count(text)
        assert rows > 0
        assert rows < 20


class TestReadAsTable:
    def test_reads_csv(self, mcp_server, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("name,value\nalpha,1\nbeta,2\ngamma,3\n")
        text = call_tool(mcp_server, "ReadAsTable", {
            "file_path": str(csv_file),
        })
        assert "alpha" in text
        assert md_row_count(text) == 3

    def test_reads_json(self, mcp_server, tmp_path):
        json_file = tmp_path / "test.json"
        json_file.write_text('[{"x": 1, "y": "a"}, {"x": 2, "y": "b"}]\n')
        text = call_tool(mcp_server, "ReadAsTable", {
            "file_path": str(json_file),
        })
        assert md_row_count(text) == 2

    def test_limit_parameter(self, mcp_server, tmp_path):
        csv_file = tmp_path / "big.csv"
        lines = ["id,val"] + [f"{i},{i*10}" for i in range(200)]
        csv_file.write_text("\n".join(lines) + "\n")
        text = call_tool(mcp_server, "ReadAsTable", {
            "file_path": str(csv_file),
            "limit": "5",
        })
        assert md_row_count(text) == 5


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


class TestFindCalls:
    def test_finds_function_calls(self, mcp_server):
        text = call_tool(mcp_server, "FindCalls", {
            "file_pattern": CONFTEST_PATH,
        })
        assert md_row_count(text) > 0


class TestFindImports:
    def test_finds_imports(self, mcp_server):
        text = call_tool(mcp_server, "FindImports", {
            "file_pattern": CONFTEST_PATH,
        })
        assert "pytest" in text
        assert "duckdb" in text


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

    def test_find_calls(self, mcp_server):
        text = call_tool(mcp_server, "FindCalls", {
            "file_pattern": JS_SIMPLE,
        })
        assert md_row_count(text) > 0
        assert "log" in text

    def test_find_imports(self, mcp_server):
        text = call_tool(mcp_server, "FindImports", {
            "file_pattern": JS_IMPORTS,
        })
        assert "react" in text

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

    def test_find_calls(self, mcp_server):
        text = call_tool(mcp_server, "FindCalls", {
            "file_pattern": RUST_SIMPLE,
        })
        assert md_row_count(text) > 0
        assert "validate_email" in text

    def test_find_imports(self, mcp_server):
        text = call_tool(mcp_server, "FindImports", {
            "file_pattern": RUST_IMPORTS,
        })
        assert "HashMap" in text

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

    def test_find_calls(self, mcp_server):
        text = call_tool(mcp_server, "FindCalls", {
            "file_pattern": GO_SIMPLE,
        })
        assert md_row_count(text) > 0

    def test_find_imports(self, mcp_server):
        text = call_tool(mcp_server, "FindImports", {
            "file_pattern": GO_SIMPLE,
        })
        assert "fmt" in text

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

    def test_find_calls(self, mcp_server):
        text = call_tool(mcp_server, "FindCalls", {
            "file_pattern": PY_SIMPLE,
        })
        assert md_row_count(text) > 0

    def test_find_imports(self, mcp_server):
        text = call_tool(mcp_server, "FindImports", {
            "file_pattern": PY_IMPORTS,
        })
        assert "os" in text

    def test_code_structure(self, mcp_server):
        text = call_tool(mcp_server, "CodeStructure", {
            "file_pattern": PY_SIMPLE,
        })
        assert "MyClass" in text
        assert md_row_count(text) > 0


# -- Docs --


class TestMDOutline:
    def test_returns_headings(self, mcp_server):
        text = call_tool(mcp_server, "MDOutline", {
            "file_pattern": SPEC_PATH,
        })
        assert md_row_count(text) > 5

    def test_max_level_filter(self, mcp_server):
        text_l1 = call_tool(mcp_server, "MDOutline", {
            "file_pattern": SPEC_PATH,
            "max_level": "1",
        })
        text_l3 = call_tool(mcp_server, "MDOutline", {
            "file_pattern": SPEC_PATH,
            "max_level": "3",
        })
        assert md_row_count(text_l1) < md_row_count(text_l3)


class TestMDSection:
    def test_reads_specific_section(self, mcp_server):
        text = call_tool(mcp_server, "MDSection", {
            "file_path": SPEC_PATH,
            "section_id": "architecture",
        })
        assert "architecture" in text.lower()


# -- Git --


class TestGitChanges:
    def test_returns_recent_commits(self, mcp_server):
        text = call_tool(mcp_server, "GitChanges", {})
        assert md_row_count(text) > 0

    def test_count_parameter(self, mcp_server):
        text = call_tool(mcp_server, "GitChanges", {"count": "3"})
        assert 1 <= md_row_count(text) <= 3

    def test_messages_are_single_line(self, mcp_server):
        text = call_tool(mcp_server, "GitChanges", {})
        # Data rows only (skip header + separator)
        data_lines = [
            l for l in text.strip().split("\n")
            if l.strip().startswith("|")
        ][2:]
        for line in data_lines:
            # Each message cell should have no embedded newlines
            cells = line.split("|")
            message = cells[4].strip() if len(cells) > 4 else ""
            assert "\n" not in message


class TestGitBranches:
    def test_lists_branches(self, mcp_server):
        text = call_tool(mcp_server, "GitBranches", {})
        assert md_row_count(text) > 0


# -- Help --


class TestHelp:
    def test_outline_returns_sections(self, mcp_server):
        text = call_tool(mcp_server, "Help", {})
        assert md_row_count(text) > 5

    def test_section_returns_content(self, mcp_server):
        text = call_tool(mcp_server, "Help", {"section": "workflows"})
        assert "workflows" in text.lower()
        assert md_row_count(text) >= 1


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
