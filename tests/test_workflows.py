"""Tests for workflow query macros (workflows tier)."""

import pytest
from conftest import PROJECT_ROOT


# ── explore_query ────────────────────────────────────────────────────


class TestExploreQuery:
    def test_returns_single_row(self, workflows_macros):
        rows = workflows_macros.execute(
            "SELECT * FROM explore_query(root := ?)", [PROJECT_ROOT]
        ).fetchall()
        assert len(rows) == 1

    def test_result_column_is_a_struct(self, workflows_macros):
        desc = workflows_macros.execute(
            "DESCRIBE SELECT * FROM explore_query(root := ?)", [PROJECT_ROOT]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert col_names == ["result"]
        col_types = {r[0]: r[1] for r in desc}
        assert col_types["result"].startswith("STRUCT")

    def test_struct_has_four_sections(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT result FROM explore_query(root := ?)", [PROJECT_ROOT]
        ).fetchone()
        result = row[0]
        assert set(result.keys()) == {"languages", "structure", "docs", "recent"}

    def test_languages_section_populated(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT result.languages FROM explore_query(root := ?)", [PROJECT_ROOT]
        ).fetchone()
        langs = row[0]
        assert langs is not None
        assert len(langs) > 0
        # fledgling is a Python project, so Python should be in the list
        names = [l["language"] for l in langs]
        assert "Python" in names

    def test_structure_respects_top_n(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT result.structure FROM explore_query(root := ?, top_n := 5)",
            [PROJECT_ROOT],
        ).fetchone()
        structure = row[0]
        assert structure is not None
        assert len(structure) <= 5

    def test_recent_section_populated(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT result.recent FROM explore_query(root := ?)", [PROJECT_ROOT]
        ).fetchone()
        recent = row[0]
        assert recent is not None
        assert len(recent) > 0
        # Each commit has hash + author + date + message
        assert "hash" in recent[0]
        assert "message" in recent[0]


# ── investigate_query ────────────────────────────────────────────────


class TestInvestigateQuery:
    def test_returns_single_row(self, workflows_macros):
        pattern = f"{PROJECT_ROOT}/tests/conftest.py"
        rows = workflows_macros.execute(
            "SELECT * FROM investigate_query('load_sql', file_pattern := ?)",
            [pattern],
        ).fetchall()
        assert len(rows) == 1

    def test_struct_has_three_sections(self, workflows_macros):
        pattern = f"{PROJECT_ROOT}/tests/conftest.py"
        row = workflows_macros.execute(
            "SELECT result FROM investigate_query('load_sql', file_pattern := ?)",
            [pattern],
        ).fetchone()
        result = row[0]
        assert set(result.keys()) == {"definitions", "callers", "call_sites"}

    def test_finds_the_definition(self, workflows_macros):
        pattern = f"{PROJECT_ROOT}/tests/conftest.py"
        row = workflows_macros.execute(
            "SELECT result.definitions FROM investigate_query('load_sql', file_pattern := ?)",
            [pattern],
        ).fetchone()
        defs = row[0]
        assert defs is not None
        assert len(defs) >= 1
        names = [d["name"] for d in defs]
        assert "load_sql" in names


# ── review_query ─────────────────────────────────────────────────────


class TestReviewQuery:
    def test_returns_single_row(self, workflows_macros):
        pattern = f"{PROJECT_ROOT}/sql/**/*.sql"
        rows = workflows_macros.execute(
            f"SELECT * FROM review_query('HEAD~1', 'HEAD', ?, repo := '{PROJECT_ROOT}')",
            [pattern],
        ).fetchall()
        assert len(rows) == 1

    def test_struct_has_two_sections(self, workflows_macros):
        pattern = f"{PROJECT_ROOT}/sql/**/*.sql"
        row = workflows_macros.execute(
            f"SELECT result FROM review_query('HEAD~1', 'HEAD', ?, repo := '{PROJECT_ROOT}')",
            [pattern],
        ).fetchone()
        result = row[0]
        assert set(result.keys()) == {"changed_files", "function_summary"}


# ── search_query ─────────────────────────────────────────────────────


class TestSearchQuery:
    def test_returns_single_row(self, workflows_macros):
        pattern = f"{PROJECT_ROOT}/tests/conftest.py"
        rows = workflows_macros.execute(
            "SELECT * FROM search_query('load%', file_pattern := ?)",
            [pattern],
        ).fetchall()
        assert len(rows) == 1

    def test_struct_has_three_sections(self, workflows_macros):
        pattern = f"{PROJECT_ROOT}/tests/conftest.py"
        row = workflows_macros.execute(
            "SELECT result FROM search_query('load%', file_pattern := ?)",
            [pattern],
        ).fetchone()
        result = row[0]
        assert set(result.keys()) == {"definitions", "call_sites", "doc_sections"}

    def test_finds_matching_definition(self, workflows_macros):
        pattern = f"{PROJECT_ROOT}/tests/conftest.py"
        row = workflows_macros.execute(
            "SELECT result.definitions FROM search_query('load%', file_pattern := ?)",
            [pattern],
        ).fetchone()
        defs = row[0]
        assert defs is not None
        # load_sql is defined in conftest.py
        names = [d["name"] for d in defs] if defs else []
        assert any("load" in n for n in names)


# ── pss_render ───────────────────────────────────────────────────────


class TestPssRender:
    """pss_render composes ast_select + duck_blocks_to_md into a markdown
    document with file:range headings and (peek-based) code blocks."""

    def test_returns_single_row(self, workflows_macros):
        rows = workflows_macros.execute(
            "SELECT * FROM pss_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchall()
        assert len(rows) == 1

    def test_result_is_markdown_string(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT * FROM pss_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchone()
        md_text = row[0]
        assert isinstance(md_text, str)
        assert len(md_text) > 0

    def test_contains_heading_with_file_range(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT * FROM pss_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchone()
        md_text = row[0]
        # Each match produces a level-1 heading with file:range
        assert "# " in md_text
        assert "connection.py:" in md_text

    def test_contains_fenced_code_blocks(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT * FROM pss_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchone()
        md_text = row[0]
        # Code blocks should be fenced with language tag
        assert "```python" in md_text

    def test_no_matches_returns_valid_output(self, workflows_macros):
        """Selector matching zero nodes returns a valid (possibly empty) result."""
        row = workflows_macros.execute(
            "SELECT * FROM pss_render(?, '.func#nonexistent_symbol_xyz_abc')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchone()
        # Should not raise; result may be None or empty string
        assert row is not None


# ── ast_select_render ────────────────────────────────────────────────


class TestAstSelectRender:
    """ast_select_render: selector heading + per-match sub-headings + code."""

    def test_returns_single_row(self, workflows_macros):
        rows = workflows_macros.execute(
            "SELECT * FROM ast_select_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchall()
        assert len(rows) == 1

    def test_starts_with_selector_heading(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT * FROM ast_select_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchone()
        md_text = row[0]
        # The selector should appear as the first level-1 heading,
        # wrapped in backticks
        first_line = md_text.lstrip().split("\n", 1)[0]
        assert first_line.startswith("# ")
        assert "`.func`" in first_line

    def test_has_level_2_headings_per_match(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT * FROM ast_select_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchone()
        md_text = row[0]
        # At least one level-2 heading per match
        assert "## " in md_text
        # Sub-heading format: "<symbol> — <file>:<start>-<end>"
        assert "—" in md_text

    def test_contains_fenced_code_blocks(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT * FROM ast_select_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchone()
        assert "```python" in row[0]
