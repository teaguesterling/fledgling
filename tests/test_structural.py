"""Tests for structural analysis macros (sitting_duck + duck_tails cross-tier)."""
import pytest
from conftest import CONFTEST_PATH, PROJECT_ROOT


class TestStructuralDiff:
    """Tests for the structural_diff macro.

    Blocked on sitting_duck#48: read_ast ignores @rev in git:// URIs.
    All tests are marked xfail until the upstream fix lands.
    """

    @pytest.mark.xfail(
        reason="sitting_duck#48: read_ast ignores @rev in git:// URIs",
        strict=True,
    )
    def test_detects_added_definitions(self, structural_macros):
        """Added definitions between revisions should appear with change='added'."""
        rows = structural_macros.execute("""
            SELECT * FROM structural_diff(
                'tests/conftest.py', 'HEAD~15', 'HEAD', '.'
            )
            WHERE change = 'added'
        """).fetchall()
        names = [r[0] for r in rows]
        # _create_mcp_server was added between HEAD~15 and HEAD
        assert "_create_mcp_server" in names

    @pytest.mark.xfail(
        reason="sitting_duck#48: read_ast ignores @rev in git:// URIs",
        strict=True,
    )
    def test_detects_modified_definitions(self, structural_macros):
        """Modified definitions should appear with change='modified'."""
        rows = structural_macros.execute("""
            SELECT * FROM structural_diff(
                'tests/conftest.py', 'HEAD~15', 'HEAD', '.'
            )
            WHERE change = 'modified'
        """).fetchall()
        names = [r[0] for r in rows]
        # mcp_server was refactored (shrunk significantly)
        assert "mcp_server" in names

    def test_result_columns(self, structural_macros):
        """structural_diff should return the expected column set."""
        desc = structural_macros.execute("""
            SELECT * FROM structural_diff(
                'tests/conftest.py', 'HEAD~15', 'HEAD', '.'
            )
            LIMIT 0
        """).description
        col_names = [d[0] for d in desc]
        assert col_names == [
            "name", "kind", "change",
            "old_lines", "new_lines",
            "old_complexity", "new_complexity", "complexity_delta",
        ]

    def test_unchanged_not_included(self, structural_macros):
        """Unchanged definitions should be filtered out."""
        rows = structural_macros.execute("""
            SELECT * FROM structural_diff(
                'tests/conftest.py', 'HEAD~15', 'HEAD', '.'
            )
            WHERE change = 'unchanged'
        """).fetchall()
        assert len(rows) == 0

    @pytest.mark.xfail(
        reason="sitting_duck#48: read_ast ignores @rev in git:// URIs",
        strict=True,
    )
    def test_complexity_delta_sign(self, structural_macros):
        """Added definitions should have positive delta; shrunk ones negative."""
        rows = structural_macros.execute("""
            SELECT name, change, complexity_delta
            FROM structural_diff(
                'tests/conftest.py', 'HEAD~15', 'HEAD', '.'
            )
        """).fetchall()
        by_name = {r[0]: r for r in rows}

        # mcp_server was refactored down — negative delta
        assert by_name["mcp_server"][2] < 0
        # _create_mcp_server was added — positive delta
        assert by_name["_create_mcp_server"][2] > 0


class TestChangedFunctionSummary:
    def test_returns_functions_in_changed_files(self, structural_macros):
        """Should return definitions from files that changed between revisions."""
        rows = structural_macros.execute("""
            SELECT * FROM changed_function_summary(
                'HEAD~15', 'HEAD', ?
            )
        """, [PROJECT_ROOT + "/tests/**/*.py"]).fetchall()
        assert len(rows) > 0

    def test_columns(self, structural_macros):
        desc = structural_macros.execute("""
            DESCRIBE SELECT * FROM changed_function_summary(
                'HEAD~15', 'HEAD', ?
            )
        """, [PROJECT_ROOT + "/tests/**/*.py"]).fetchall()
        col_names = [r[0] for r in desc]
        assert col_names == [
            "file_path", "name", "kind", "lines",
            "cyclomatic", "change_status",
        ]

    def test_ordered_by_cyclomatic_desc(self, structural_macros):
        rows = structural_macros.execute("""
            SELECT cyclomatic FROM changed_function_summary(
                'HEAD~15', 'HEAD', ?
            )
        """, [PROJECT_ROOT + "/tests/**/*.py"]).fetchall()
        cyclomatic = [r[0] for r in rows]
        assert cyclomatic == sorted(cyclomatic, reverse=True)

    def test_change_status_values(self, structural_macros):
        rows = structural_macros.execute("""
            SELECT DISTINCT change_status FROM changed_function_summary(
                'HEAD~15', 'HEAD', ?
            )
        """, [PROJECT_ROOT + "/tests/**/*.py"]).fetchall()
        statuses = {r[0] for r in rows}
        assert statuses <= {"added", "modified"}
