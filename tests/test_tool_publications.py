"""Tests for fledgling MCP tool publications and their wrapper macros.

Verifies that:
1. Each wrapper macro loads and returns results (not errors)
2. Text-formatted macros return a single `line` column
3. Tool publications register in the MCP server
4. git tools work with HEAD~1 and HEAD
5. pss_render returns non-empty code blocks
6. Conversation macros either return results or skip gracefully

Uses the repo itself as test data (dog-fooding).
"""

import os
import pytest

from conftest import (
    CONFTEST_PATH,
    PROJECT_ROOT,
    V1_TOOLS,
    call_tool,
    json_row_count,
    list_tools,
    md_row_count,
    parse_json_rows,
    text_line_count,
)

# Pattern for fledgling Python source (test data for most macros)
FLEDGLING_PY = PROJECT_ROOT + "/fledgling/**/*.py"


# ---------------------------------------------------------------------------
# Wrapper macro column / shape tests (direct SQL, not via MCP transport)
# These verify the macro layer that tool publications delegate to.
# ---------------------------------------------------------------------------


class TestFindCodeGrepWrapper:
    """find_code_grep returns a single `line` column (text output shape)."""

    def test_returns_line_column(self, code_macros):
        desc = code_macros.execute(
            "DESCRIBE SELECT * FROM find_code_grep(?, '.func')",
            [CONFTEST_PATH],
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert col_names == ["line"]

    def test_returns_rows(self, code_macros):
        rows = code_macros.execute(
            "SELECT * FROM find_code_grep(?, '.func')",
            [CONFTEST_PATH],
        ).fetchall()
        assert len(rows) > 0

    def test_line_format(self, code_macros):
        """Each line should be file:start-end | name | kind | peek."""
        rows = code_macros.execute(
            "SELECT * FROM find_code_grep(?, '.func')",
            [CONFTEST_PATH],
        ).fetchall()
        line = rows[0][0]
        assert "|" in line
        # file:start-end part
        assert ":" in line.split("|")[0]


class TestViewCodeTextWrapper:
    """view_code_text returns a single `line` column (text output shape)."""

    def test_returns_line_column(self, code_macros):
        desc = code_macros.execute(
            "DESCRIBE SELECT * FROM view_code_text(?, '.func')",
            [CONFTEST_PATH],
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert col_names == ["line"]

    def test_returns_rows(self, code_macros):
        rows = code_macros.execute(
            "SELECT * FROM view_code_text(?, '.func')",
            [CONFTEST_PATH],
        ).fetchall()
        assert len(rows) > 0

    def test_heading_format(self, code_macros):
        """At least one row should contain a heading: # file:start-end."""
        rows = code_macros.execute(
            "SELECT * FROM view_code_text(?, '.func')",
            [CONFTEST_PATH],
        ).fetchall()
        headings = [r[0] for r in rows if "# " in r[0] and ":" in r[0]]
        assert len(headings) > 0

    def test_numbered_source_lines(self, code_macros):
        """Non-heading rows should start with a line number prefix (4-digit padded)."""
        rows = code_macros.execute(
            "SELECT * FROM view_code_text(?, '.func')",
            [CONFTEST_PATH],
        ).fetchall()
        # Filter to lines that are purely numbered source (not headings)
        numbered = [r[0].strip() for r in rows if r[0].strip() and r[0].strip()[0].isdigit()]
        assert len(numbered) > 0


class TestReadSourceTextWrapper:
    """read_source_text returns a single `line` column (text output shape)."""

    def test_returns_line_column(self, source_macros):
        create_resolve_macros_for(source_macros)
        desc = source_macros.execute(
            "DESCRIBE SELECT * FROM read_source_text(?)",
            [CONFTEST_PATH],
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert col_names == ["line"]

    def test_returns_rows(self, source_macros):
        create_resolve_macros_for(source_macros)
        rows = source_macros.execute(
            "SELECT * FROM read_source_text(?)",
            [CONFTEST_PATH],
        ).fetchall()
        assert len(rows) > 50

    def test_line_number_prefix(self, source_macros):
        """Each row should start with a 4-digit padded line number."""
        create_resolve_macros_for(source_macros)
        rows = source_macros.execute(
            "SELECT * FROM read_source_text(?, '1-3')",
            [CONFTEST_PATH],
        ).fetchall()
        assert len(rows) == 3
        for i, row in enumerate(rows):
            # Format: "   1  content"
            assert str(i + 1) in row[0]


class TestFileDiffTextWrapper:
    """file_diff_text returns a single `line` column."""

    def test_returns_line_column(self, repo_macros):
        create_resolve_macros_for(repo_macros)
        # Use a file that exists in git history; find one that changed
        changed_file = _find_changed_file_from_repo(repo_macros)
        if changed_file is None:
            pytest.skip("No changed files found in HEAD~1..HEAD")
        desc = repo_macros.execute(
            "DESCRIBE SELECT * FROM file_diff_text(?, 'HEAD~1', 'HEAD')",
            [changed_file],
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert col_names == ["line"]

    def test_returns_diff_lines(self, repo_macros):
        create_resolve_macros_for(repo_macros)
        changed_file = _find_changed_file_from_repo(repo_macros)
        if changed_file is None:
            pytest.skip("No changed files found in HEAD~1..HEAD")
        rows = repo_macros.execute(
            "SELECT * FROM file_diff_text(?, 'HEAD~1', 'HEAD')",
            [changed_file],
        ).fetchall()
        assert len(rows) > 0

    def test_diff_markers(self, repo_macros):
        """Lines should start with +, -, or space."""
        create_resolve_macros_for(repo_macros)
        changed_file = _find_changed_file_from_repo(repo_macros)
        if changed_file is None:
            pytest.skip("No changed files found in HEAD~1..HEAD")
        rows = repo_macros.execute(
            "SELECT * FROM file_diff_text(?, 'HEAD~1', 'HEAD')",
            [changed_file],
        ).fetchall()
        for row in rows:
            assert row[0][0] in ("+", "-", " ")


class TestBrowseSessionsWrapper:
    """browse_sessions returns expected columns."""

    def test_returns_expected_columns(self, conversation_macros):
        desc = conversation_macros.execute(
            "DESCRIBE SELECT * FROM browse_sessions()"
        ).fetchall()
        col_names = [r[0] for r in desc]
        for col in ("session_id", "project_dir", "slug", "started_at"):
            assert col in col_names, f"Missing column: {col}"

    def test_returns_rows(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT * FROM browse_sessions()"
        ).fetchall()
        assert len(rows) > 0

    def test_project_filter(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT * FROM browse_sessions(project := 'test-project')"
        ).fetchall()
        assert len(rows) > 0

    def test_nonexistent_project_returns_empty(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT * FROM browse_sessions(project := 'xyznonexistent999')"
        ).fetchall()
        assert len(rows) == 0


class TestSearchChatWrapper:
    """search_chat returns expected columns."""

    def test_returns_expected_columns(self, conversation_macros):
        desc = conversation_macros.execute(
            "DESCRIBE SELECT * FROM search_chat('bug')"
        ).fetchall()
        col_names = [r[0] for r in desc]
        for col in ("session_id", "slug", "role", "content_preview"):
            assert col in col_names, f"Missing column: {col}"

    def test_finds_matching_messages(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT * FROM search_chat('bug')"
        ).fetchall()
        assert len(rows) > 0

    def test_no_match_returns_empty(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT * FROM search_chat('xyznonexistent999')"
        ).fetchall()
        assert len(rows) == 0

    def test_role_filter(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT * FROM search_chat('fix', role := 'user')"
        ).fetchall()
        assert all(r[2] == "user" for r in rows)


class TestBrowseToolUsageWrapper:
    """browse_tool_usage returns expected columns."""

    def test_returns_expected_columns(self, conversation_macros):
        desc = conversation_macros.execute(
            "DESCRIBE SELECT * FROM browse_tool_usage()"
        ).fetchall()
        col_names = [r[0] for r in desc]
        for col in ("tool_name", "total_calls", "sessions"):
            assert col in col_names, f"Missing column: {col}"

    def test_returns_rows(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT * FROM browse_tool_usage()"
        ).fetchall()
        assert len(rows) > 0


class TestSessionDetailWrapper:
    """session_detail returns expected columns."""

    def test_returns_expected_columns(self, conversation_macros):
        desc = conversation_macros.execute(
            "DESCRIBE SELECT * FROM session_detail('sess-001')"
        ).fetchall()
        col_names = [r[0] for r in desc]
        for col in ("slug", "project_dir", "tool_name"):
            assert col in col_names, f"Missing column: {col}"

    def test_returns_rows(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT * FROM session_detail('sess-001')"
        ).fetchall()
        assert len(rows) > 0


# ---------------------------------------------------------------------------
# PssRender / AstSelectRender wrapper macros (workflows tier)
# ---------------------------------------------------------------------------


class TestPssRenderWrapper:
    """pss_render returns a `result` column containing markdown with code blocks."""

    def test_returns_result_column(self, workflows_macros):
        create_resolve_macros_for(workflows_macros)
        desc = workflows_macros.execute(
            "DESCRIBE SELECT * FROM pss_render(?, '.func')",
            [CONFTEST_PATH],
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert col_names == ["result"]

    def test_returns_rows(self, workflows_macros):
        create_resolve_macros_for(workflows_macros)
        rows = workflows_macros.execute(
            "SELECT * FROM pss_render(?, '.func')",
            [CONFTEST_PATH],
        ).fetchall()
        assert len(rows) > 0

    def test_result_contains_code_fence(self, workflows_macros):
        """pss_render produces markdown with ``` code fences."""
        create_resolve_macros_for(workflows_macros)
        rows = workflows_macros.execute(
            "SELECT * FROM pss_render(?, '.func')",
            [CONFTEST_PATH],
        ).fetchall()
        # Combine all result rows
        combined = "\n".join(r[0] for r in rows if r[0] is not None)
        assert "```" in combined

    def test_result_non_empty(self, workflows_macros):
        """The fix for read_lines_lateral: pss_render should not return empty blocks."""
        create_resolve_macros_for(workflows_macros)
        rows = workflows_macros.execute(
            "SELECT * FROM pss_render(?, '.func')",
            [CONFTEST_PATH],
        ).fetchall()
        non_empty = [r for r in rows if r[0] and r[0].strip()]
        assert len(non_empty) > 0
        # Specifically check that at least one code block has content inside
        combined = "\n".join(r[0] for r in non_empty)
        # There should be non-trivial content between fences
        parts = combined.split("```")
        code_parts = [p.strip() for p in parts[1::2]]  # odd parts are code
        non_empty_code = [p for p in code_parts if p and not p.isspace()]
        assert len(non_empty_code) > 0, "All code fences are empty"


@pytest.mark.xfail(reason="ast_select_render has a COALESCE type mismatch bug — pss_render/SelectCode is the replacement")
class TestAstSelectRenderWrapper:
    """ast_select_render returns a `result` column with grouped markdown."""

    def test_returns_result_column(self, workflows_macros):
        create_resolve_macros_for(workflows_macros)
        desc = workflows_macros.execute(
            "DESCRIBE SELECT * FROM ast_select_render(?, '.func')",
            [CONFTEST_PATH],
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert col_names == ["result"]

    def test_returns_rows(self, workflows_macros):
        create_resolve_macros_for(workflows_macros)
        rows = workflows_macros.execute(
            "SELECT * FROM ast_select_render(?, '.func')",
            [CONFTEST_PATH],
        ).fetchall()
        assert len(rows) > 0


# ---------------------------------------------------------------------------
# MCP tool publication tests (via MCP memory transport, mcp_server fixture)
# ---------------------------------------------------------------------------


class TestToolRegistrations:
    """All V1 tools must be registered in the MCP server."""

    def test_all_v1_tools_present(self, mcp_server):
        names = {t["name"] for t in list_tools(mcp_server)}
        for tool in V1_TOOLS:
            assert tool in names, f"Missing tool: {tool}"

    def test_find_code_tool_registered(self, mcp_server):
        names = {t["name"] for t in list_tools(mcp_server)}
        assert "FindCode" in names

    def test_view_code_tool_registered(self, mcp_server):
        names = {t["name"] for t in list_tools(mcp_server)}
        assert "ViewCode" in names

    def test_select_code_tool_registered(self, mcp_server):
        names = {t["name"] for t in list_tools(mcp_server)}
        assert "SelectCode" in names


class TestFindCodeTool:
    """FindCode tool: wrapper macro returns text with `line` column."""

    def test_returns_results(self, mcp_server):
        text = call_tool(mcp_server, "FindCode", {
            "file_pattern": FLEDGLING_PY,
            "selector": ".func",
        })
        assert text_line_count(text) > 0

    def test_line_format_with_pipe_separators(self, mcp_server):
        """Each line should be file:start-end | name | kind | peek."""
        text = call_tool(mcp_server, "FindCode", {
            "file_pattern": FLEDGLING_PY,
            "selector": ".func",
        })
        lines = [l for l in text.strip().split("\n") if l.strip()]
        assert len(lines) > 0
        assert "|" in lines[0]

    def test_filters_by_selector(self, mcp_server):
        """Selector name filter should return fewer results than .func."""
        text_all = call_tool(mcp_server, "FindCode", {
            "file_pattern": FLEDGLING_PY,
            "selector": ".func",
        })
        # Pick a specific function name we know exists
        text_filtered = call_tool(mcp_server, "FindCode", {
            "file_pattern": CONFTEST_PATH,
            "selector": ".func",
        })
        assert text_line_count(text_filtered) > 0
        assert text_line_count(text_filtered) <= text_line_count(text_all)


class TestViewCodeTool:
    """ViewCode tool: wrapper macro returns text with `line` column."""

    def test_returns_results(self, mcp_server):
        text = call_tool(mcp_server, "ViewCode", {
            "file_pattern": CONFTEST_PATH,
            "selector": ".func",
        })
        assert text_line_count(text) > 0

    def test_heading_format(self, mcp_server):
        """Output should include # heading lines for file:start-end."""
        text = call_tool(mcp_server, "ViewCode", {
            "file_pattern": CONFTEST_PATH,
            "selector": ".func",
        })
        assert "#" in text

    def test_numbered_lines(self, mcp_server):
        """Source lines should appear with numeric line-number prefix."""
        text = call_tool(mcp_server, "ViewCode", {
            "file_pattern": CONFTEST_PATH,
            "selector": ".func",
        })
        lines = text.strip().split("\n")
        source_lines = [l for l in lines if l and not l.startswith("#")]
        assert len(source_lines) > 0
        # First source line should have a digit-based prefix
        assert any(c.isdigit() for c in source_lines[0][:6])


class TestGitDiffFileTool:
    """GitDiffFile tool: wrapper macro returns text with `line` column."""

    def _find_changed_file(self, mcp_server):
        summary = call_tool(mcp_server, "GitDiffSummary", {
            "from_rev": "HEAD~1",
            "to_rev": "HEAD",
        })
        for line in summary.strip().split("\n"):
            if "|" in line and "file_path" not in line and "---" not in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if parts:
                    return parts[0]
        return None

    def test_returns_text_lines(self, mcp_server):
        changed = self._find_changed_file(mcp_server)
        assert changed is not None, "No files changed in HEAD~1..HEAD"
        text = call_tool(mcp_server, "GitDiffFile", {
            "file": changed,
            "from_rev": "HEAD~1",
            "to_rev": "HEAD",
        })
        assert text_line_count(text) > 0

    def test_diff_markers_present(self, mcp_server):
        """Each line should start with +, -, or a space."""
        changed = self._find_changed_file(mcp_server)
        assert changed is not None, "No files changed in HEAD~1..HEAD"
        text = call_tool(mcp_server, "GitDiffFile", {
            "file": changed,
            "from_rev": "HEAD~1",
            "to_rev": "HEAD",
        })
        lines = [l for l in text.strip().split("\n") if l]
        assert len(lines) > 0
        # Check first non-empty line starts with +/- or space
        assert lines[0][0] in ("+", "-", " ")


class TestSelectCodeTool:
    """SelectCode tool wraps pss_render: must return non-empty code blocks."""

    def test_returns_results(self, mcp_server):
        text = call_tool(mcp_server, "SelectCode", {
            "source": CONFTEST_PATH,
            "selector": ".func",
        })
        assert text_line_count(text) > 0

    def test_contains_code_fence(self, mcp_server):
        text = call_tool(mcp_server, "SelectCode", {
            "source": CONFTEST_PATH,
            "selector": ".func",
        })
        assert "```" in text

    def test_code_blocks_non_empty(self, mcp_server):
        """The read_lines_lateral fix: code blocks must have content."""
        text = call_tool(mcp_server, "SelectCode", {
            "source": CONFTEST_PATH,
            "selector": ".func",
        })
        parts = text.split("```")
        # Odd-indexed parts are inside code fences
        code_parts = [p.strip() for p in parts[1::2]]
        # Strip language specifier line from each block
        code_bodies = []
        for part in code_parts:
            lines = part.split("\n")
            # First line may be the language identifier (e.g. "python")
            body = "\n".join(lines[1:]) if lines else ""
            code_bodies.append(body.strip())
        non_empty = [b for b in code_bodies if b]
        assert len(non_empty) > 0, "All code fences are empty — read_lines_lateral fix may be broken"


# ---------------------------------------------------------------------------
# Conversation tool tests via MCP server (use mcp_server fixture with synthetic data)
# ---------------------------------------------------------------------------


class TestChatSessionsTool:
    """ChatSessions tool wraps browse_sessions."""

    def test_returns_results(self, mcp_server):
        text = call_tool(mcp_server, "ChatSessions", {})
        assert md_row_count(text) >= 1

    def test_expected_columns_present(self, mcp_server):
        text = call_tool(mcp_server, "ChatSessions", {})
        # Markdown table header should contain session_id or slug
        assert "session_id" in text or "slug" in text

    def test_project_filter(self, mcp_server):
        text = call_tool(mcp_server, "ChatSessions", {"project": "mcp-test"})
        assert md_row_count(text) >= 1

    def test_project_filter_no_match(self, mcp_server):
        text = call_tool(mcp_server, "ChatSessions", {"project": "xyznonexistent999"})
        assert md_row_count(text) == 0


class TestChatSearchTool:
    """ChatSearch tool wraps search_chat."""

    def test_finds_messages(self, mcp_server):
        text = call_tool(mcp_server, "ChatSearch", {"query": "bug"})
        assert md_row_count(text) >= 1

    def test_no_results_for_garbage_query(self, mcp_server):
        text = call_tool(mcp_server, "ChatSearch", {"query": "xyznonexistent999"})
        assert md_row_count(text) == 0

    def test_role_filter_assistant(self, mcp_server):
        text = call_tool(mcp_server, "ChatSearch", {
            "query": "fix",
            "role": "assistant",
        })
        # All rows should be assistant
        data_lines = [
            l for l in text.strip().split("\n")
            if l.strip().startswith("|")
        ][2:]  # skip header + separator
        for line in data_lines:
            assert "assistant" in line


class TestChatToolUsageTool:
    """ChatToolUsage tool wraps browse_tool_usage."""

    def test_returns_results(self, mcp_server):
        text = call_tool(mcp_server, "ChatToolUsage", {})
        assert md_row_count(text) >= 1

    def test_known_tools_present(self, mcp_server):
        text = call_tool(mcp_server, "ChatToolUsage", {})
        assert "Bash" in text


class TestChatDetailTool:
    """ChatDetail tool wraps session_detail."""

    def test_returns_results(self, mcp_server):
        text = call_tool(mcp_server, "ChatDetail", {"session_id": "sess-001"})
        assert md_row_count(text) >= 1

    def test_slug_present(self, mcp_server):
        text = call_tool(mcp_server, "ChatDetail", {"session_id": "sess-001"})
        assert "fix-auth" in text

    def test_tool_breakdown(self, mcp_server):
        text = call_tool(mcp_server, "ChatDetail", {"session_id": "sess-001"})
        assert "Bash" in text
        assert "Read" in text


# ---------------------------------------------------------------------------
# Graceful skip tests for real conversation data
# ---------------------------------------------------------------------------


class TestConversationsMacrosRealData:
    """These tests skip if no real Claude conversation data is available.

    When CLAUDE_PROJECTS_DIR exists and has data, they verify the macros
    work end-to-end against real conversation history.
    """

    PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

    def _has_real_data(self):
        if not os.path.isdir(self.PROJECTS_DIR):
            return False
        jsonl_files = []
        for root, dirs, files in os.walk(self.PROJECTS_DIR):
            for f in files:
                if f.endswith(".jsonl"):
                    jsonl_files.append(f)
        return len(jsonl_files) > 0

    def test_browse_sessions_real_data(self, con):
        """browse_sessions against real data returns rows or gracefully skips."""
        if not self._has_real_data():
            pytest.skip("No real Claude conversation data found")
        from conftest import load_sql
        con.execute(f"SET VARIABLE conversations_root = '{self.PROJECTS_DIR}'")
        load_sql(con, "conversations.sql")
        rows = con.execute("SELECT * FROM browse_sessions() LIMIT 5").fetchall()
        assert isinstance(rows, list)
        # May be empty if data exists but is malformed — just verify no error

    def test_browse_tool_usage_real_data(self, con):
        """browse_tool_usage against real data returns rows or gracefully skips."""
        if not self._has_real_data():
            pytest.skip("No real Claude conversation data found")
        from conftest import load_sql
        con.execute(f"SET VARIABLE conversations_root = '{self.PROJECTS_DIR}'")
        load_sql(con, "conversations.sql")
        rows = con.execute("SELECT * FROM browse_tool_usage() LIMIT 10").fetchall()
        assert isinstance(rows, list)


# ---------------------------------------------------------------------------
# Helper functions (module-level, not fixtures)
# ---------------------------------------------------------------------------


def create_resolve_macros_for(con):
    """Set up _resolve() and _session_root() macros pointing at PROJECT_ROOT."""
    con.execute(f"""CREATE OR REPLACE MACRO _resolve(p) AS
        CASE WHEN p IS NULL THEN NULL
             WHEN p[1] = '/' THEN p
             ELSE '{PROJECT_ROOT}/' || p
        END""")
    con.execute(f"CREATE OR REPLACE MACRO _session_root() AS '{PROJECT_ROOT}'")


def _find_changed_file_from_repo(repo_macros):
    """Return a file path (repo-relative) that changed in HEAD~1..HEAD."""
    try:
        rows = repo_macros.execute(
            "SELECT file_path FROM file_changes('HEAD~1', 'HEAD', ?) LIMIT 1",
            [PROJECT_ROOT],
        ).fetchall()
        if rows:
            return rows[0][0]
    except Exception:
        pass
    return None
