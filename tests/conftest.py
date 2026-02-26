"""Shared fixtures for duck_nest macro tests.

All tests use the duck_nest repo itself as test data (dog-fooding).
"""

import os
import pytest
import duckdb

DUCK_NEST_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(DUCK_NEST_ROOT, "sql")
CLAUDE_PROJECTS_DIR = os.path.expanduser("~/.claude/projects")


@pytest.fixture
def con():
    """Fresh DuckDB connection for each test."""
    conn = duckdb.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def ext_read_lines(con):
    """Connection with read_lines loaded."""
    con.execute("LOAD read_lines")
    return con


@pytest.fixture
def ext_sitting_duck(con):
    """Connection with sitting_duck loaded."""
    con.execute("LOAD sitting_duck")
    return con


@pytest.fixture
def ext_markdown(con):
    """Connection with duckdb_markdown loaded."""
    con.execute("LOAD markdown")
    return con


@pytest.fixture
def ext_duck_tails(con):
    """Connection with duck_tails loaded."""
    con.execute("LOAD duck_tails")
    return con


@pytest.fixture
def all_extensions(con):
    """Connection with all extensions loaded."""
    con.execute("LOAD read_lines")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD markdown")
    con.execute("LOAD duck_tails")
    return con


def load_sql(con, filename):
    """Load a SQL macro file into the connection."""
    path = os.path.join(SQL_DIR, filename)
    with open(path) as f:
        sql = f.read()
    # Strip comment-only lines before splitting on semicolons
    lines = []
    for line in sql.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("--"):
            lines.append(line)
    cleaned = "\n".join(lines)
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt + ";")


@pytest.fixture
def source_macros(ext_read_lines):
    """Connection with read_lines + source macros loaded."""
    load_sql(ext_read_lines, "source.sql")
    return ext_read_lines


@pytest.fixture
def code_macros(ext_sitting_duck):
    """Connection with sitting_duck + code macros loaded."""
    load_sql(ext_sitting_duck, "code.sql")
    return ext_sitting_duck


@pytest.fixture
def docs_macros(ext_markdown):
    """Connection with duckdb_markdown + docs macros loaded."""
    load_sql(ext_markdown, "docs.sql")
    return ext_markdown


@pytest.fixture
def repo_macros(ext_duck_tails):
    """Connection with duck_tails + repo macros loaded."""
    load_sql(ext_duck_tails, "repo.sql")
    return ext_duck_tails


# Paths to test data (the duck_nest repo itself)
SPEC_PATH = os.path.join(DUCK_NEST_ROOT, "docs/vision/PRODUCT_SPEC.md")
ANALYSIS_PATH = os.path.join(DUCK_NEST_ROOT, "docs/vision/CONVERSATION_ANALYSIS.md")
CONFTEST_PATH = os.path.join(DUCK_NEST_ROOT, "tests/conftest.py")
