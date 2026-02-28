"""Tests for repository intelligence macros (duck_tails tier)."""

import pytest
from conftest import REPO_PATH


class TestRecentChanges:
    def test_returns_commits(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT * FROM recent_changes(10, ?)", [REPO_PATH]
        ).fetchall()
        assert len(rows) >= 3  # we've made at least 3 commits

    def test_respects_limit(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT * FROM recent_changes(2, ?)", [REPO_PATH]
        ).fetchall()
        assert len(rows) == 2

    def test_commit_columns(self, repo_macros):
        desc = repo_macros.execute(
            "DESCRIBE SELECT * FROM recent_changes(1, ?)", [REPO_PATH]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "hash" in col_names
        assert "author" in col_names
        assert "date" in col_names
        assert "message" in col_names

    def test_hash_is_short(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT hash FROM recent_changes(1, ?)", [REPO_PATH]
        ).fetchall()
        assert len(rows[0][0]) == 8

    def test_initial_commit_message(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT message FROM recent_changes(100, ?)", [REPO_PATH]
        ).fetchall()
        messages = [r[0] for r in rows]
        assert any("Initial commit" in m for m in messages)


class TestBranchList:
    def test_returns_branches(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT * FROM branch_list(?)", [REPO_PATH]
        ).fetchall()
        assert len(rows) >= 1

    def test_has_current_branch(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT branch_name, is_current FROM branch_list(?)", [REPO_PATH]
        ).fetchall()
        current = [r for r in rows if r[1]]
        assert len(current) == 1

    def test_branch_columns(self, repo_macros):
        desc = repo_macros.execute(
            "DESCRIBE SELECT * FROM branch_list(?)", [REPO_PATH]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "branch_name" in col_names
        assert "is_current" in col_names
        assert "is_remote" in col_names


class TestTagList:
    def test_returns_without_error(self, repo_macros):
        """Tag list may be empty for new repos but should not error."""
        rows = repo_macros.execute(
            "SELECT * FROM tag_list(?)", [REPO_PATH]
        ).fetchall()
        assert isinstance(rows, list)

    def test_tag_columns(self, repo_macros):
        desc = repo_macros.execute(
            "DESCRIBE SELECT * FROM tag_list(?)", [REPO_PATH]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "tag_name" in col_names
        assert "is_annotated" in col_names


class TestRepoFiles:
    def test_lists_tracked_files(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT * FROM repo_files('HEAD', ?)", [REPO_PATH]
        ).fetchall()
        assert len(rows) > 0

    def test_finds_known_files(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT file_path FROM repo_files('HEAD', ?)", [REPO_PATH]
        ).fetchall()
        paths = [r[0] for r in rows]
        assert any("PRODUCT_SPEC" in p for p in paths)

    def test_file_columns(self, repo_macros):
        desc = repo_macros.execute(
            "DESCRIBE SELECT * FROM repo_files('HEAD', ?)", [REPO_PATH]
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "file_path" in col_names
        assert "size_bytes" in col_names
        assert "is_text" in col_names

    def test_ordered_by_path(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT file_path FROM repo_files('HEAD', ?)", [REPO_PATH]
        ).fetchall()
        paths = [r[0] for r in rows]
        assert paths == sorted(paths)


class TestFileAtVersion:
    def test_reads_file_at_head(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT * FROM file_at_version('docs/vision/PRODUCT_SPEC.md', 'HEAD', ?)",
            [REPO_PATH],
        ).fetchall()
        assert len(rows) == 1
        assert len(rows[0][3]) > 100  # content should be substantial

    def test_content_matches_current(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT content FROM file_at_version('docs/vision/PRODUCT_SPEC.md', 'HEAD', ?)",
            [REPO_PATH],
        ).fetchall()
        assert "Fledgling" in rows[0][0]

    def test_file_columns(self, repo_macros):
        desc = repo_macros.execute(
            "DESCRIBE SELECT * FROM file_at_version('docs/vision/PRODUCT_SPEC.md', 'HEAD', ?)",
            [REPO_PATH],
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "file_path" in col_names
        assert "content" in col_names


class TestFileChanges:
    def test_returns_changed_files(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT * FROM file_changes('HEAD~1', 'HEAD', ?)", [REPO_PATH]
        ).fetchall()
        assert len(rows) >= 1

    def test_detects_status(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT DISTINCT status FROM file_changes('HEAD~1', 'HEAD', ?)",
            [REPO_PATH],
        ).fetchall()
        statuses = {r[0] for r in rows}
        assert statuses <= {"added", "deleted", "modified"}

    def test_columns(self, repo_macros):
        desc = repo_macros.execute(
            "DESCRIBE SELECT * FROM file_changes('HEAD~1', 'HEAD', ?)",
            [REPO_PATH],
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "file_path" in col_names
        assert "status" in col_names
        assert "old_size" in col_names
        assert "new_size" in col_names

    def test_ordered_by_path(self, repo_macros):
        rows = repo_macros.execute(
            "SELECT file_path FROM file_changes('HEAD~1', 'HEAD', ?)",
            [REPO_PATH],
        ).fetchall()
        paths = [r[0] for r in rows]
        assert paths == sorted(paths)


class TestFileDiff:
    def test_returns_diff_lines(self, repo_macros):
        # Find a file that changed
        changed = repo_macros.execute(
            "SELECT file_path FROM file_changes('HEAD~1', 'HEAD', ?)",
            [REPO_PATH],
        ).fetchone()
        assert changed is not None, "No changed files between HEAD~1 and HEAD"
        rows = repo_macros.execute(
            "SELECT * FROM file_diff(?, 'HEAD~1', 'HEAD', ?)",
            [changed[0], REPO_PATH],
        ).fetchall()
        assert len(rows) > 0

    def test_diff_has_line_types(self, repo_macros):
        changed = repo_macros.execute(
            "SELECT file_path FROM file_changes('HEAD~1', 'HEAD', ?)",
            [REPO_PATH],
        ).fetchone()
        assert changed is not None
        rows = repo_macros.execute(
            "SELECT DISTINCT line_type FROM file_diff(?, 'HEAD~1', 'HEAD', ?)",
            [changed[0], REPO_PATH],
        ).fetchall()
        line_types = {r[0] for r in rows}
        assert line_types <= {"ADDED", "REMOVED", "CONTEXT"}
        assert line_types & {"ADDED", "REMOVED"}  # diff must have changes

    def test_columns(self, repo_macros):
        changed = repo_macros.execute(
            "SELECT file_path FROM file_changes('HEAD~1', 'HEAD', ?)",
            [REPO_PATH],
        ).fetchone()
        assert changed is not None
        desc = repo_macros.execute(
            "DESCRIBE SELECT * FROM file_diff(?, 'HEAD~1', 'HEAD', ?)",
            [changed[0], REPO_PATH],
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "seq" in col_names
        assert "line_type" in col_names
        assert "content" in col_names


class TestCrossExtensionComposition:
    """Test that macros from different tiers compose in the same connection."""

    def test_all_macros_load_together(self, all_macros):
        """Verify all macros coexist without conflicts."""
        # One query per tier to prove they all work
        assert all_macros.execute(
            "SELECT count(*) FROM read_source(?)", [REPO_PATH + "/tests/conftest.py"]
        ).fetchone()[0] > 0

        assert all_macros.execute(
            "SELECT count(*) FROM find_definitions(?)",
            [REPO_PATH + "/tests/conftest.py"],
        ).fetchone()[0] > 0

        assert all_macros.execute(
            "SELECT count(*) FROM doc_outline(?)",
            [REPO_PATH + "/docs/vision/PRODUCT_SPEC.md"],
        ).fetchone()[0] > 0

        assert all_macros.execute(
            "SELECT count(*) FROM recent_changes(3, ?)", [REPO_PATH]
        ).fetchone()[0] > 0
