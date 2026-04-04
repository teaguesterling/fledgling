"""Tests for dr_fledgling diagnostic macro."""

import pytest
from conftest import load_sql


@pytest.fixture
def dr_macros(con):
    """Connection with dr_fledgling macro loaded."""
    con.execute("SET VARIABLE fledgling_version = '0.6.2'")
    con.execute("SET VARIABLE fledgling_profile = 'analyst'")
    con.execute("SET VARIABLE session_root = '/test/root'")
    con.execute("SET VARIABLE fledgling_modules = ['source', 'code']")
    load_sql(con, "dr_fledgling.sql")
    return con


class TestDrFledgling:
    def test_returns_rows(self, dr_macros):
        rows = dr_macros.execute("SELECT * FROM dr_fledgling()").fetchall()
        assert len(rows) == 5

    def test_version(self, dr_macros):
        rows = dr_macros.execute(
            "SELECT value FROM dr_fledgling() WHERE key = 'version'"
        ).fetchall()
        assert rows[0][0] == "0.6.2"

    def test_profile(self, dr_macros):
        rows = dr_macros.execute(
            "SELECT value FROM dr_fledgling() WHERE key = 'profile'"
        ).fetchall()
        assert rows[0][0] == "analyst"

    def test_root(self, dr_macros):
        rows = dr_macros.execute(
            "SELECT value FROM dr_fledgling() WHERE key = 'root'"
        ).fetchall()
        assert rows[0][0] == "/test/root"

    def test_modules(self, dr_macros):
        rows = dr_macros.execute(
            "SELECT value FROM dr_fledgling() WHERE key = 'modules'"
        ).fetchall()
        assert rows[0][0] == "source, code"

    def test_extensions_column_exists(self, dr_macros):
        rows = dr_macros.execute(
            "SELECT value FROM dr_fledgling() WHERE key = 'extensions'"
        ).fetchall()
        assert len(rows) == 1
