"""Tests for source retrieval macros (read_lines tier)."""

import duckdb
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


    def test_nonexistent_file_raises_error(self, source_macros):
        """Nonexistent files raise IO Error (read_lines fix in DuckDB 1.5.1)."""
        with pytest.raises(duckdb.IOException, match="No files found"):
            source_macros.execute(
                "SELECT * FROM read_source('this-file-does-not-exist.txt')"
            ).fetchall()

    def test_empty_file_returns_zero_rows(self, source_macros, tmp_path):
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")
        rows = source_macros.execute(
            "SELECT * FROM read_source(?)", [str(empty_file)]
        ).fetchall()
        assert len(rows) == 0


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

    def test_nonexistent_file_raises_error(self, source_macros):
        with pytest.raises(duckdb.IOException, match="No files found"):
            source_macros.execute(
                "SELECT * FROM read_context('this-file-does-not-exist.txt', 10)"
            ).fetchall()


class TestProjectOverviewMacro:
    def test_columns(self, source_macros):
        desc = source_macros.execute(
            "DESCRIBE SELECT * FROM project_overview(?)", [PROJECT_ROOT]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "language" in col_names
        assert "extension" in col_names
        assert "file_count" in col_names

    def test_returns_language_breakdown(self, source_macros):
        rows = source_macros.execute(
            "SELECT * FROM project_overview(?)", [PROJECT_ROOT]
        ).fetchall()
        assert len(rows) > 0
        languages = {r[0] for r in rows}
        assert "SQL" in languages
        assert "Python" in languages

    def test_file_counts_are_positive(self, source_macros):
        rows = source_macros.execute(
            "SELECT * FROM project_overview(?)", [PROJECT_ROOT]
        ).fetchall()
        for row in rows:
            assert row[2] > 0

    def test_ordered_by_file_count_desc(self, source_macros):
        rows = source_macros.execute(
            "SELECT * FROM project_overview(?)", [PROJECT_ROOT]
        ).fetchall()
        counts = [r[2] for r in rows]
        assert counts == sorted(counts, reverse=True)

    def test_subdirectory_scoping(self, source_macros):
        all_rows = source_macros.execute(
            "SELECT * FROM project_overview(?)", [PROJECT_ROOT]
        ).fetchall()
        sql_rows = source_macros.execute(
            "SELECT * FROM project_overview(?)", [PROJECT_ROOT + "/sql"]
        ).fetchall()
        assert len(sql_rows) < len(all_rows)
        sql_languages = {r[0] for r in sql_rows}
        assert "SQL" in sql_languages

    def test_aggregation_with_fixture_data(self, source_macros, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "utils.py").write_text("def util(): pass")
        (tmp_path / "schema.sql").write_text("CREATE TABLE t(id INT)")
        (tmp_path / "README.md").write_text("# README")
        rows = source_macros.execute(
            "SELECT * FROM project_overview(?)", [str(tmp_path)]
        ).fetchall()
        assert len(rows) == 3
        by_lang = {r[0]: r[2] for r in rows}
        assert by_lang["Python"] == 2
        assert by_lang["SQL"] == 1
        assert by_lang["Markdown"] == 1

    def test_empty_directory_returns_zero_rows(self, source_macros, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        rows = source_macros.execute(
            "SELECT * FROM project_overview(?)", [str(empty_dir)]
        ).fetchall()
        assert len(rows) == 0


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
