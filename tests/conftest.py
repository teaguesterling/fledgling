"""Shared fixtures for source_sextant macro tests.

All tests use the source_sextant repo itself as test data (dog-fooding).
"""

import os
import pytest
import duckdb

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(PROJECT_ROOT, "sql")
CLAUDE_PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

# Test data paths (the repo itself)
SPEC_PATH = os.path.join(PROJECT_ROOT, "docs/vision/PRODUCT_SPEC.md")
ANALYSIS_PATH = os.path.join(PROJECT_ROOT, "docs/vision/CONVERSATION_ANALYSIS.md")
CONFTEST_PATH = os.path.join(PROJECT_ROOT, "tests/conftest.py")
REPO_PATH = PROJECT_ROOT


def load_sql(con, filename):
    """Load a SQL macro file into a DuckDB connection.

    Strips comment-only lines before splitting on semicolons to avoid
    parsing errors from semicolons inside comments.
    """
    path = os.path.join(SQL_DIR, filename)
    with open(path) as f:
        sql = f.read()
    lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
    cleaned = "\n".join(lines)
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt + ";")


@pytest.fixture
def con():
    """Fresh in-memory DuckDB connection."""
    conn = duckdb.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def source_macros(con):
    """Connection with read_lines extension + source macros."""
    con.execute("LOAD read_lines")
    load_sql(con, "source.sql")
    return con


@pytest.fixture
def code_macros(con):
    """Connection with sitting_duck extension + code macros."""
    con.execute("LOAD sitting_duck")
    load_sql(con, "code.sql")
    return con


@pytest.fixture
def docs_macros(con):
    """Connection with markdown extension + docs macros."""
    con.execute("LOAD markdown")
    load_sql(con, "docs.sql")
    return con


@pytest.fixture
def repo_macros(con):
    """Connection with duck_tails extension + repo macros."""
    con.execute("LOAD duck_tails")
    load_sql(con, "repo.sql")
    return con


@pytest.fixture
def all_macros(con):
    """Connection with ALL extensions and ALL macros loaded.

    Load order matters: source.sql drops sitting_duck's conflicting
    read_lines macro, so it must load after sitting_duck.
    """
    con.execute("LOAD read_lines")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD markdown")
    con.execute("LOAD duck_tails")
    # sitting_duck's read_lines macro shadows the extension; drop it
    con.execute("DROP MACRO TABLE IF EXISTS read_lines")
    load_sql(con, "source.sql")
    load_sql(con, "code.sql")
    load_sql(con, "docs.sql")
    load_sql(con, "repo.sql")
    return con
