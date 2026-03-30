# tests/test_edit_cli.py
"""Smoke tests for fledgling-edit CLI."""

import os
import subprocess
import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def test_file(tmp_path):
    p = tmp_path / "sample.py"
    p.write_text("def old_func():\n    return 1\n\ndef keep():\n    pass\n")
    return str(p)


class TestCLI:
    def test_help(self):
        result = subprocess.run(
            ["python", "-m", "fledgling.edit.cli", "--help"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0
        assert "fledgling-edit" in result.stdout or "usage" in result.stdout.lower()

    def test_remove_preview(self, test_file):
        result = subprocess.run(
            ["python", "-m", "fledgling.edit.cli", "remove", test_file, "old_func"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0
        assert "-def old_func" in result.stdout

    def test_rename_preview(self, test_file):
        result = subprocess.run(
            ["python", "-m", "fledgling.edit.cli", "rename", test_file,
             "old_func", "new_func"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0
        assert "+def new_func" in result.stdout
