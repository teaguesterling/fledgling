"""Tests for help system macro (skill guide access)."""

import pytest


class TestHelpOutline:
    """help() with no arguments returns an outline."""

    def test_returns_sections(self, help_macros):
        rows = help_macros.execute("SELECT * FROM help()").fetchall()
        assert len(rows) > 5

    def test_content_is_null(self, help_macros):
        rows = help_macros.execute(
            "SELECT content FROM help()"
        ).fetchall()
        for row in rows:
            assert row[0] is None

    def test_known_section_ids_present(self, help_macros):
        rows = help_macros.execute(
            "SELECT section_id FROM help()"
        ).fetchall()
        ids = [r[0] for r in rows]
        assert "quick-reference" in ids
        assert "file-navigation" in ids
        assert "code-intelligence" in ids
        assert "workflows" in ids
        assert "tips" in ids

    def test_sections_in_document_order(self, help_macros):
        """Outline sections appear in document order (quick-reference before tips)."""
        rows = help_macros.execute(
            "SELECT section_id FROM help()"
        ).fetchall()
        ids = [r[0] for r in rows]
        assert ids.index("quick-reference") < ids.index("tips")

    def test_outline_columns(self, help_macros):
        desc = help_macros.execute(
            "DESCRIBE SELECT * FROM help()"
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "section_id" in col_names
        assert "title" in col_names
        assert "level" in col_names
        assert "content" in col_names


class TestHelpSection:
    """help(section_id) returns matching sections with content."""

    def test_finds_section_by_id(self, help_macros):
        rows = help_macros.execute(
            "SELECT * FROM help('workflows')"
        ).fetchall()
        assert len(rows) >= 1

    def test_section_has_content(self, help_macros):
        rows = help_macros.execute(
            "SELECT content FROM help('workflows')"
        ).fetchall()
        assert len(rows) >= 1
        for row in rows:
            assert row[0] is not None
            assert len(row[0]) > 0

    def test_returns_children_via_path_match(self, help_macros):
        rows = help_macros.execute(
            "SELECT section_id FROM help('workflows')"
        ).fetchall()
        ids = [r[0] for r in rows]
        # Should include the section itself and child sections
        assert "workflows" in ids
        assert len(ids) >= 2  # parent + at least one child

    def test_nonexistent_section_returns_empty(self, help_macros):
        rows = help_macros.execute(
            "SELECT * FROM help('nonexistent-section-xyz')"
        ).fetchall()
        assert len(rows) == 0

    def test_finds_leaf_section(self, help_macros):
        """A subsection like 'listfiles' should be findable by ID."""
        rows = help_macros.execute(
            "SELECT * FROM help('listfiles')"
        ).fetchall()
        assert len(rows) >= 1
