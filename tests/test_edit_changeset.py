# tests/test_edit_changeset.py
"""Tests for Changeset (pure Python, no DuckDB)."""

import pytest
from fledgling.edit.region import Region
from fledgling.edit.ops import (
    Remove, Replace, InsertBefore, InsertAfter, Wrap, Move,
)
from fledgling.edit.changeset import Changeset


SAMPLE_FILE = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
#               line 1         line 2     line 3  line 4        line 5


@pytest.fixture
def sample_file(tmp_path):
    p = tmp_path / "sample.py"
    p.write_text(SAMPLE_FILE)
    return str(p)


class TestChangesetPreviewSingleEdit:
    def test_remove(self, sample_file):
        r = Region.at(sample_file, 4, 5, content="def bar():\n    return 2\n")
        cs = Changeset([Remove(region=r)])
        result = cs.preview()
        assert sample_file in result
        assert "def bar" not in result[sample_file]
        assert "def foo" in result[sample_file]

    def test_replace(self, sample_file):
        r = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        cs = Changeset([Replace(region=r, new_content="def foo():\n    return 42\n")])
        result = cs.preview()
        assert "return 42" in result[sample_file]
        assert "return 1" not in result[sample_file]

    def test_insert_before(self, sample_file):
        r = Region.at(sample_file, 4, 5)
        cs = Changeset([InsertBefore(region=r, content="# comment\n")])
        result = cs.preview()
        lines = result[sample_file].splitlines()
        bar_idx = next(i for i, l in enumerate(lines) if "def bar" in l)
        assert lines[bar_idx - 1] == "# comment"

    def test_insert_after(self, sample_file):
        r = Region.at(sample_file, 2, 2)
        cs = Changeset([InsertAfter(region=r, content="    # added\n")])
        result = cs.preview()
        lines = result[sample_file].splitlines()
        ret_idx = next(i for i, l in enumerate(lines) if "return 1" in l)
        assert "# added" in lines[ret_idx + 1]

    def test_wrap(self, sample_file):
        r = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        cs = Changeset([Wrap(region=r, before="# BEGIN\n", after="# END\n")])
        result = cs.preview()
        text = result[sample_file]
        assert "# BEGIN\ndef foo" in text
        assert "return 1\n# END" in text


class TestChangesetPreviewMultiEdit:
    def test_two_removes_same_file(self, sample_file):
        r1 = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        r2 = Region.at(sample_file, 4, 5, content="def bar():\n    return 2\n")
        cs = Changeset([Remove(region=r1), Remove(region=r2)])
        result = cs.preview()
        # Only the blank line between them should remain
        assert "def foo" not in result[sample_file]
        assert "def bar" not in result[sample_file]

    def test_multi_edit_preserves_unmodified_lines(self, sample_file):
        r = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        cs = Changeset([Remove(region=r)])
        result = cs.preview()
        assert "def bar" in result[sample_file]


class TestChangesetPreviewMove:
    def test_move_between_files(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("def helper():\n    pass\n\ndef main():\n    pass\n")
        b.write_text("# utils\n")

        src = Region.at(str(a), 1, 2, content="def helper():\n    pass\n")
        dst = Region.at(str(b), 1, 1)
        cs = Changeset([Move(region=src, destination=dst)])
        result = cs.preview()
        assert "def helper" not in result[str(a)]
        assert "def helper" in result[str(b)]


class TestChangesetDiff:
    def test_diff_shows_unified_format(self, sample_file):
        r = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        cs = Changeset([Replace(region=r, new_content="def foo():\n    return 42\n")])
        diff = cs.diff()
        assert "---" in diff
        assert "+++" in diff
        assert "-    return 1" in diff
        assert "+    return 42" in diff


class TestChangesetApply:
    def test_apply_writes_file(self, sample_file):
        r = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        cs = Changeset([Replace(region=r, new_content="def foo():\n    return 42\n")])
        modified = cs.apply()
        assert sample_file in modified
        with open(sample_file) as f:
            assert "return 42" in f.read()

    def test_apply_returns_affected_paths(self, sample_file):
        r = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        cs = Changeset([Remove(region=r)])
        modified = cs.apply()
        assert modified == [sample_file]


class TestChangesetValidate:
    def test_overlapping_regions_warns(self, sample_file):
        r1 = Region.at(sample_file, 1, 3)
        r2 = Region.at(sample_file, 2, 5)
        cs = Changeset([Remove(region=r1), Remove(region=r2)])
        warnings = cs.validate()
        assert len(warnings) > 0
        assert "overlap" in warnings[0].lower()

    def test_shared_boundary_line_warns(self, sample_file):
        """Lines 1-3 and 3-5 both touch line 3 — must warn."""
        r1 = Region.at(sample_file, 1, 3)
        r2 = Region.at(sample_file, 3, 5)
        cs = Changeset([Remove(region=r1), Remove(region=r2)])
        warnings = cs.validate()
        assert len(warnings) > 0
        assert "overlap" in warnings[0].lower()

    def test_non_overlapping_no_warnings(self, sample_file):
        r1 = Region.at(sample_file, 1, 2)
        r2 = Region.at(sample_file, 4, 5)
        cs = Changeset([Remove(region=r1), Remove(region=r2)])
        assert cs.validate() == []


class TestChangesetComposition:
    def test_add_merges_ops(self, sample_file):
        r1 = Region.at(sample_file, 1, 2)
        r2 = Region.at(sample_file, 4, 5)
        cs1 = Changeset([Remove(region=r1)])
        cs2 = Changeset([Remove(region=r2)])
        combined = cs1 + cs2
        assert len(combined.ops) == 2

    def test_files_affected(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("x\n")
        b.write_text("y\n")
        cs = Changeset([
            Remove(region=Region.at(str(a), 1, 1)),
            Remove(region=Region.at(str(b), 1, 1)),
        ])
        assert cs.files_affected() == {str(a), str(b)}
