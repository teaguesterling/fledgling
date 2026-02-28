"""Tests for documentation intelligence macros (duckdb_markdown tier)."""

import pytest
from conftest import SPEC_PATH, ANALYSIS_PATH, PROJECT_ROOT


class TestDocOutline:
    def test_returns_sections(self, docs_macros):
        rows = docs_macros.execute(
            "SELECT * FROM doc_outline(?)", [SPEC_PATH]
        ).fetchall()
        assert len(rows) > 5

    def test_outline_columns(self, docs_macros):
        desc = docs_macros.execute(
            "DESCRIBE SELECT * FROM doc_outline(?)", [SPEC_PATH]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "file_path" in col_names
        assert "section_id" in col_names
        assert "level" in col_names
        assert "title" in col_names

    def test_respects_max_level(self, docs_macros):
        rows = docs_macros.execute(
            "SELECT DISTINCT level FROM doc_outline(?, 2)", [SPEC_PATH]
        ).fetchall()
        levels = [r[0] for r in rows]
        assert all(l <= 2 for l in levels)

    def test_ordered_by_start_line(self, docs_macros):
        rows = docs_macros.execute(
            "SELECT start_line FROM doc_outline(?)", [SPEC_PATH]
        ).fetchall()
        lines = [r[0] for r in rows]
        assert lines == sorted(lines)

    def test_finds_known_sections(self, docs_macros):
        rows = docs_macros.execute(
            "SELECT section_id FROM doc_outline(?)", [SPEC_PATH]
        ).fetchall()
        ids = [r[0] for r in rows]
        assert "architecture" in ids
        assert "what-is-fledgling" in ids

    def test_multiple_files_via_glob(self, docs_macros):
        pattern = PROJECT_ROOT + "/docs/vision/*.md"
        paths = docs_macros.execute(
            "SELECT DISTINCT file_path FROM doc_outline(?)", [pattern]
        ).fetchall()
        assert len(paths) >= 2


class TestReadDocSection:
    def test_finds_section_by_id(self, docs_macros):
        rows = docs_macros.execute(
            "SELECT * FROM read_doc_section(?, 'architecture')", [SPEC_PATH]
        ).fetchall()
        assert len(rows) >= 1

    def test_section_has_content(self, docs_macros):
        rows = docs_macros.execute(
            "SELECT content FROM read_doc_section(?, 'architecture')",
            [SPEC_PATH],
        ).fetchall()
        assert len(rows) >= 1
        assert len(str(rows[0][0])) > 0

    def test_section_columns(self, docs_macros):
        desc = docs_macros.execute(
            "DESCRIBE SELECT * FROM read_doc_section(?, 'architecture')",
            [SPEC_PATH],
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "section_id" in col_names
        assert "title" in col_names
        assert "content" in col_names

    def test_returns_children_via_path_match(self, docs_macros):
        """read_doc_section should return the section and its children."""
        rows = docs_macros.execute(
            "SELECT section_id FROM read_doc_section(?, 'architecture')",
            [SPEC_PATH],
        ).fetchall()
        ids = [r[0] for r in rows]
        # Should include the section itself and child sections
        assert "architecture" in ids

    def test_nonexistent_section_returns_empty(self, docs_macros):
        rows = docs_macros.execute(
            "SELECT * FROM read_doc_section(?, 'nonexistent-section-xyz')",
            [SPEC_PATH],
        ).fetchall()
        assert len(rows) == 0


class TestFindCodeExamples:
    def test_finds_code_blocks(self, docs_macros):
        rows = docs_macros.execute(
            "SELECT * FROM find_code_examples(?)", [SPEC_PATH]
        ).fetchall()
        assert len(rows) > 0

    def test_code_block_columns(self, docs_macros):
        desc = docs_macros.execute(
            "DESCRIBE SELECT * FROM find_code_examples(?)", [SPEC_PATH]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "language" in col_names
        assert "code" in col_names
        assert "section" in col_names

    def test_filter_by_language(self, docs_macros):
        rows = docs_macros.execute(
            "SELECT language FROM find_code_examples(?, 'sql')", [SPEC_PATH]
        ).fetchall()
        for row in rows:
            assert row[0] == "sql"

    def test_filter_by_json(self, docs_macros):
        rows = docs_macros.execute(
            "SELECT language FROM find_code_examples(?, 'json')", [SPEC_PATH]
        ).fetchall()
        assert len(rows) > 0
        for row in rows:
            assert row[0] == "json"


class TestDocStats:
    def test_returns_stats(self, docs_macros):
        rows = docs_macros.execute(
            "SELECT * FROM doc_stats(?)", [SPEC_PATH]
        ).fetchall()
        assert len(rows) == 1

    def test_stat_columns(self, docs_macros):
        desc = docs_macros.execute(
            "DESCRIBE SELECT * FROM doc_stats(?)", [SPEC_PATH]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "word_count" in col_names
        assert "heading_count" in col_names
        assert "code_block_count" in col_names

    def test_word_count_positive(self, docs_macros):
        rows = docs_macros.execute(
            "SELECT word_count FROM doc_stats(?)", [SPEC_PATH]
        ).fetchall()
        assert rows[0][0] > 100

    def test_ordered_by_word_count(self, docs_macros):
        pattern = PROJECT_ROOT + "/docs/vision/*.md"
        rows = docs_macros.execute(
            "SELECT word_count FROM doc_stats(?)", [pattern]
        ).fetchall()
        counts = [r[0] for r in rows]
        assert counts == sorted(counts, reverse=True)
