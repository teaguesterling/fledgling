"""Tests for source retrieval macros (read_lines tier)."""

import pytest
from conftest import SPEC_PATH, CONFTEST_PATH, PROJECT_ROOT


class TestReadSource:
    def test_reads_all_lines(self, source_macros):
        rows = source_macros.execute(
            "SELECT * FROM read_source(?)", [SPEC_PATH]
        ).fetchall()
        assert len(rows) > 100
        # Should have line_number and content columns
        assert rows[0][0] == 1  # first line number

    def test_reads_line_range(self, source_macros):
        rows = source_macros.execute(
            "SELECT * FROM read_source(?, '1-5')", [SPEC_PATH]
        ).fetchall()
        assert len(rows) == 5
        assert rows[0][0] == 1
        assert rows[4][0] == 5

    def test_reads_single_line(self, source_macros):
        rows = source_macros.execute(
            "SELECT * FROM read_source(?, '1')", [SPEC_PATH]
        ).fetchall()
        assert len(rows) == 1

    def test_line_content_matches(self, source_macros):
        rows = source_macros.execute(
            "SELECT content FROM read_source(?, '1')", [SPEC_PATH]
        ).fetchall()
        assert "Fledgling" in rows[0][0]

    def test_context_lines(self, source_macros):
        rows = source_macros.execute(
            "SELECT * FROM read_source(?, '10 +/-2')", [SPEC_PATH]
        ).fetchall()
        assert len(rows) == 5  # line 10 plus 2 before, 2 after
        line_numbers = [r[0] for r in rows]
        assert 8 in line_numbers
        assert 10 in line_numbers
        assert 12 in line_numbers

    def test_columns_are_line_number_and_content(self, source_macros):
        desc = source_macros.execute(
            "DESCRIBE SELECT * FROM read_source(?)", [SPEC_PATH]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "line_number" in col_names
        assert "content" in col_names


class TestReadSourceBatch:
    def test_includes_file_path(self, source_macros):
        pattern = PROJECT_ROOT + "/docs/vision/*.md"
        desc = source_macros.execute(
            "DESCRIBE SELECT * FROM read_source_batch(?)", [pattern]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "file_path" in col_names

    def test_reads_multiple_files(self, source_macros):
        pattern = PROJECT_ROOT + "/docs/vision/*.md"
        paths = source_macros.execute(
            "SELECT DISTINCT file_path FROM read_source_batch(?)", [pattern]
        ).fetchall()
        # Should find both PRODUCT_SPEC.md and CONVERSATION_ANALYSIS.md
        assert len(paths) >= 2


class TestReadContext:
    def test_default_context(self, source_macros):
        rows = source_macros.execute(
            "SELECT * FROM read_context(?, 10)", [SPEC_PATH]
        ).fetchall()
        # Default context is 5 lines each side: 5-15 = 11 lines
        assert len(rows) == 11

    def test_custom_context(self, source_macros):
        rows = source_macros.execute(
            "SELECT * FROM read_context(?, 10, 2)", [SPEC_PATH]
        ).fetchall()
        assert len(rows) == 5  # 8,9,10,11,12

    def test_is_center_flag(self, source_macros):
        rows = source_macros.execute(
            "SELECT line_number, is_center FROM read_context(?, 10, 2)",
            [SPEC_PATH],
        ).fetchall()
        center_rows = [r for r in rows if r[1]]
        assert len(center_rows) == 1
        assert center_rows[0][0] == 10


class TestFileLineCount:
    def test_single_file(self, source_macros):
        rows = source_macros.execute(
            "SELECT * FROM file_line_count(?)", [SPEC_PATH]
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][1] > 100  # line_count

    def test_glob_pattern(self, source_macros):
        pattern = PROJECT_ROOT + "/docs/vision/*.md"
        rows = source_macros.execute(
            "SELECT * FROM file_line_count(?)", [pattern]
        ).fetchall()
        assert len(rows) >= 2
        # Ordered by line_count DESC
        assert rows[0][1] >= rows[1][1]
