"""End-to-end integration tests for fledgling + pluckit + squawkit.

Tests each package independently, then the integration points between them.
Does NOT test MCP protocol (no server start, no JSON-RPC). Focuses on the
Python API surface and cross-package macro availability.

Requires all three packages installed:
  pip install fledgling-mcp ast-pluckit
  pip install -e ~/Projects/squawkit  (or pip install squawkit)
"""

import os
import pytest

# The fledgling repo as test data
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFTEST_PATH = os.path.join(PROJECT_ROOT, "tests", "conftest.py")
CONNECTION_PATH = os.path.join(PROJECT_ROOT, "fledgling", "connection.py")


# ════════════════════════════════════════════════════════════════════
# Part 1: fledgling standalone
# ════════════════════════════════════════════════════════════════════


class TestFledglingConnect:
    """fledgling.connect() produces a working macro-enabled connection."""

    def test_connect_returns_connection_proxy(self):
        import fledgling
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        assert type(con).__name__ == "Connection"

    def test_connect_has_macros(self):
        import fledgling
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        macros = con._tools._macros
        assert "find_definitions" in macros
        assert "code_structure" in macros
        assert "recent_changes" in macros

    def test_find_definitions_returns_results(self):
        import fledgling
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        rel = con.find_definitions(CONFTEST_PATH, name_pattern="load%")
        rows = rel.fetchall()
        assert len(rows) >= 1
        names = [r[1] for r in rows]
        assert "load_sql" in names

    def test_code_structure_returns_results(self):
        import fledgling
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        rel = con.code_structure(CONNECTION_PATH)
        rows = rel.fetchall()
        assert len(rows) > 5

    def test_recent_changes_returns_commits(self):
        import fledgling
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        rel = con.recent_changes(3)
        rows = rel.fetchall()
        assert len(rows) == 3
        assert len(rows[0][0]) == 8  # short hash


class TestFledglingAttach:
    """fledgling.attach() configures an existing connection."""

    def test_attach_loads_macros(self):
        import duckdb
        import fledgling
        raw = duckdb.connect()
        con = fledgling.attach(raw, root=PROJECT_ROOT, modules=["sandbox", "source"])
        count = con.execute(
            f"SELECT count(*) FROM list_files('{PROJECT_ROOT}/tests/*.py')"
        ).fetchone()[0]
        assert count > 5

    def test_attach_preserves_existing_data(self):
        import duckdb
        import fledgling
        raw = duckdb.connect()
        raw.execute("CREATE TABLE test_data AS SELECT 42 AS x")
        fledgling.attach(raw, modules=["sandbox"], overlay=False)
        val = raw.execute("SELECT x FROM test_data").fetchone()[0]
        assert val == 42


class TestFledglingWorkflowMacros:
    """The workflow query macros compose other macros correctly."""

    def test_explore_query(self):
        import fledgling
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        row = con.execute(
            "SELECT * FROM explore_query(root := ?)",
            [PROJECT_ROOT],
        ).fetchone()
        result = row[0]
        assert "languages" in result
        assert "structure" in result
        assert "recent" in result
        assert len(result["languages"]) > 0

    def test_investigate_query(self):
        import fledgling
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        row = con.execute(
            "SELECT * FROM investigate_query('load_sql', file_pattern := ?)",
            [CONFTEST_PATH],
        ).fetchone()
        result = row[0]
        assert "definitions" in result
        assert len(result["definitions"]) >= 1

    def test_search_query(self):
        import fledgling
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        row = con.execute(
            "SELECT * FROM search_query('load%', file_pattern := ?)",
            [CONFTEST_PATH],
        ).fetchone()
        result = row[0]
        assert "definitions" in result
        assert "call_sites" in result


class TestFledglingRendering:
    """pss_render (via SelectCode MCP tool) produces valid markdown with full source."""

    def test_pss_render(self):
        import fledgling
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        row = con.execute(
            "SELECT * FROM pss_render(?, '.func')",
            [CONNECTION_PATH],
        ).fetchone()
        md = row[0]
        assert isinstance(md, str)
        assert "# " in md  # heading
        assert "```python" in md  # fenced code

    def test_pss_render_has_full_source(self):
        """pss_render now extracts full function bodies via read_lines_lateral,
        not just peek signatures."""
        import fledgling
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        row = con.execute(
            "SELECT * FROM pss_render(?, '.func#connect')",
            [CONNECTION_PATH],
        ).fetchone()
        md = row[0]
        # Full body should contain 'def connect' AND implementation details
        assert "def connect" in md
        assert "duckdb.connect" in md or "configure" in md


class TestFledglingLockdown:
    """lockdown() restricts filesystem access."""

    def test_lockdown_blocks_external_access(self):
        import duckdb
        import fledgling
        con = duckdb.connect()
        fledgling.configure(con, root="/tmp/test-lockdown", modules=["sandbox"])
        fledgling.lockdown(con, lock_config=False)
        # After lockdown, external access is disabled
        val = con.execute(
            "SELECT current_setting('enable_external_access')"
        ).fetchone()[0]
        assert str(val).lower() in ("false", "0")


# ════════════════════════════════════════════════════════════════════
# Part 2: pluckit standalone
# ════════════════════════════════════════════════════════════════════


class TestPluckitBasic:
    """Plucker creates a connection and finds code."""

    def test_plucker_creates_connection(self):
        from pluckit import Plucker
        p = Plucker(repo=PROJECT_ROOT)
        assert p._ctx.db is not None

    def test_find_functions(self):
        from pluckit import Plucker
        p = Plucker(code=CONNECTION_PATH, repo=PROJECT_ROOT)
        sel = p.find(".func")
        assert sel.count() > 5

    def test_find_classes(self):
        from pluckit import Plucker
        p = Plucker(code=CONNECTION_PATH, repo=PROJECT_ROOT)
        sel = p.find(".cls")
        names = sel.names()
        assert "Connection" in names

    def test_find_by_name(self):
        from pluckit import Plucker
        p = Plucker(code=CONFTEST_PATH, repo=PROJECT_ROOT)
        sel = p.find(".func#load_sql")
        assert sel.count() >= 1


class TestPluckitViewer:
    """AstViewer renders code blocks from CSS selectors."""

    def test_view_functions(self):
        from pluckit import Plucker
        from pluckit.plugins.viewer import AstViewer
        p = Plucker(code=CONNECTION_PATH, repo=PROJECT_ROOT, plugins=[AstViewer])
        output = p.view(".func#connect")
        assert "def connect" in str(output)

    def test_view_class_outline(self):
        from pluckit import Plucker
        from pluckit.plugins.viewer import AstViewer
        p = Plucker(code=CONNECTION_PATH, repo=PROJECT_ROOT, plugins=[AstViewer])
        output = p.view(".cls#Connection")
        md = str(output)
        assert "Connection" in md
        assert "__init__" in md or "__getattr__" in md


class TestPluckitNavigation:
    """Selection navigation (parent, children, etc.)."""

    def test_children(self):
        from pluckit import Plucker
        p = Plucker(code=CONNECTION_PATH, repo=PROJECT_ROOT)
        sel = p.find(".cls#Connection")
        kids = sel.children()
        assert kids.count() > 0


# ════════════════════════════════════════════════════════════════════
# Part 3: squawkit standalone
# ════════════════════════════════════════════════════════════════════


class TestSquawkitDefaults:
    """Smart defaults inference works against the fledgling repo."""

    def test_infer_defaults(self):
        from squawkit.defaults import infer_defaults
        import fledgling
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        defaults = infer_defaults(con, root=PROJECT_ROOT)
        assert "py" in defaults.code_pattern
        assert defaults.main_branch in ("main", "master")
        assert len(defaults.languages) > 0
        assert "Python" in defaults.languages

    def test_doc_pattern_finds_docs(self):
        from squawkit.defaults import infer_defaults
        import fledgling
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        defaults = infer_defaults(con, root=PROJECT_ROOT)
        assert defaults.doc_pattern.startswith("docs/")


class TestSquawkitFormatting:
    """Truncation helpers work."""

    def test_truncate_rows(self):
        from squawkit.formatting import _truncate_rows
        rows = [(i, i * 2) for i in range(100)]
        truncated, omission = _truncate_rows(rows, 10, "test_macro")
        assert len(truncated) == 10
        assert omission is not None
        assert "omitted" in omission


class TestSquawkitSession:
    """Session cache and access log."""

    def test_cache_put_get(self):
        from squawkit.session import SessionCache
        cache = SessionCache()
        cache.put("test_tool", {"arg": "val"}, "result text", 5, ttl=60)
        entry = cache.get("test_tool", {"arg": "val"})
        assert entry is not None
        assert entry.text == "result text"
        assert entry.row_count == 5

    def test_cache_miss(self):
        from squawkit.session import SessionCache
        cache = SessionCache()
        assert cache.get("nonexistent", {}) is None

    def test_access_log(self):
        import duckdb
        from squawkit.session import AccessLog
        con = duckdb.connect()
        log = AccessLog(con)
        log.record("tool1", {"a": 1}, 10, cached=False, elapsed_ms=50.0)
        log.record("tool2", {"b": 2}, 5, cached=True, elapsed_ms=1.0)
        summary = log.summary()
        assert summary["total_calls"] == 2
        assert summary["cached_calls"] == 1
        recent = log.recent_calls()
        assert len(recent) == 2


class TestSquawkitWorkflows:
    """Compound workflow helpers produce formatted briefings."""

    def test_format_briefing(self):
        from squawkit.workflows import _format_briefing
        md = _format_briefing("Test", [("Section A", "content a"), ("Section B", "content b")])
        assert "## Test" in md
        assert "### Section A" in md
        assert "content a" in md


# ════════════════════════════════════════════════════════════════════
# Part 4: Cross-package integration
# ════════════════════════════════════════════════════════════════════


class TestFledglingPluckitIntegration:
    """Pluckit uses fledgling's connection and macros."""

    def test_plucker_uses_fledgling_connection(self):
        from pluckit import Plucker
        p = Plucker(repo=PROJECT_ROOT)
        assert p._ctx._fledgling_loaded is True
        assert type(p._ctx.db).__name__ == "Connection"

    def test_plucker_connection_has_workflow_macros(self):
        """fledgling's workflow macros are available through pluckit's connection."""
        from pluckit import Plucker
        p = Plucker(repo=PROJECT_ROOT)
        # Call a fledgling workflow macro through pluckit's connection
        row = p._ctx.db.execute(
            "SELECT * FROM explore_query(root := ?)", [PROJECT_ROOT]
        ).fetchone()
        result = row[0]
        assert "languages" in result
        assert len(result["languages"]) > 0

    def test_plucker_connection_has_find_class_members(self):
        """find_class_members macro is callable through pluckit's connection."""
        from pluckit import Plucker
        p = Plucker(code=CONNECTION_PATH, repo=PROJECT_ROOT)
        # Find the Connection class's node_id
        row = p._ctx.db.execute(
            "SELECT node_id FROM read_ast(?) WHERE type = 'class_definition' AND name = 'Connection'",
            [CONNECTION_PATH],
        ).fetchone()
        assert row is not None
        node_id = row[0]
        # Call find_class_members
        members = p._ctx.db.execute(
            "SELECT name, type FROM find_class_members(?, ?)",
            [CONNECTION_PATH, node_id],
        ).fetchall()
        names = [m[0] for m in members]
        assert "__init__" in names

    def test_viewer_find_renders_with_fledgling_macros(self):
        """AstViewer works end-to-end through pluckit → fledgling chain."""
        from pluckit import Plucker
        from pluckit.plugins.viewer import AstViewer
        p = Plucker(code=CONNECTION_PATH, repo=PROJECT_ROOT, plugins=[AstViewer])
        output = p.view(".func#connect")
        md = str(output)
        assert len(md) > 0
        assert "connect" in md


class TestSquawkitFledglingIntegration:
    """Squawkit uses fledgling's connection for defaults inference."""

    def test_squawkit_defaults_via_fledgling_connect(self):
        """squawkit.defaults.infer_defaults works with a fledgling connection."""
        import fledgling
        from squawkit.defaults import infer_defaults
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        defaults = infer_defaults(con, root=PROJECT_ROOT)
        assert defaults.code_pattern == "**/*.py"
        assert len(defaults.languages) > 3

    def test_squawkit_formatting_on_fledgling_data(self):
        """squawkit's formatting helpers work on data from fledgling macros."""
        import fledgling
        from squawkit.formatting import _format_markdown_table
        con = fledgling.connect(init=False, root=PROJECT_ROOT)
        rows = con.execute(
            "SELECT hash, author, message FROM recent_changes(5)"
        ).fetchall()
        cols = ["hash", "author", "message"]
        md = _format_markdown_table(cols, [list(r) for r in rows])
        assert "| hash" in md
        assert len(md.split("\n")) >= 7  # header + separator + 5 rows


class TestAllThreeTogether:
    """The full stack: pluckit (with fledgling) producing data for squawkit formatting."""

    def test_pluckit_find_formatted_by_squawkit(self):
        """pluckit finds definitions, squawkit formats them."""
        from pluckit import Plucker
        from squawkit.formatting import _format_markdown_table
        p = Plucker(code=CONNECTION_PATH, repo=PROJECT_ROOT)
        sel = p.find(".func")
        rows = sel.materialize()
        data = [[r["name"], r["start_line"]] for r in rows]
        md = _format_markdown_table(["name", "start_line"], data)
        assert "| name" in md
        assert "connect" in md

    def test_pluckit_connection_serves_squawkit_defaults(self):
        """pluckit's fledgling-loaded connection serves squawkit's defaults inference."""
        from pluckit import Plucker
        from squawkit.defaults import infer_defaults
        p = Plucker(repo=PROJECT_ROOT)
        defaults = infer_defaults(p._ctx.db, root=PROJECT_ROOT)
        assert defaults.code_pattern == "**/*.py"
        assert "Python" in defaults.languages

    def test_full_stack_explore(self):
        """pluckit's connection → fledgling's explore_query → squawkit's briefing formatter."""
        from pluckit import Plucker
        from squawkit.workflows import _format_briefing
        p = Plucker(repo=PROJECT_ROOT)
        # Use fledgling's explore_query through pluckit's connection
        row = p._ctx.db.execute(
            "SELECT * FROM explore_query(root := ?)", [PROJECT_ROOT]
        ).fetchone()
        result = row[0]
        # Format with squawkit's briefing helper
        sections = []
        if result["languages"]:
            lang_lines = [f"{l['language']}: {l['file_count']} files" for l in result["languages"][:5]]
            sections.append(("Languages", "\n".join(lang_lines)))
        if result["recent"]:
            commit_lines = [f"{c['hash']} {c['message']}" for c in result["recent"][:3]]
            sections.append(("Recent Activity", "\n".join(commit_lines)))
        md = _format_briefing("Fledgling Project", sections)
        assert "## Fledgling Project" in md
        assert "### Languages" in md
        assert "Python" in md
