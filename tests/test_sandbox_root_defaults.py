"""Root-defaulting macros must work when the process CWD is not the root.

Sandboxing (#49/#50) restricts `allowed_directories` to the connection's root.
Macros that defaulted their root/repo parameter to '.' resolved against the
*process* CWD instead, so every one of them raised

    Permission Error: Cannot access file "./**/*" -
    file system operations are disabled by configuration

as soon as a caller connected with root != cwd — which is the normal library
pattern: a server pointed at a project while running somewhere else. It was
easy to miss because callers often wrap these in try/except and degrade
silently (squackit's infer_defaults returned an empty language list rather
than reporting a permission error).

The macros default to _session_root() now, which is the root the connection
was actually opened with.
"""
import os

import pytest

import fledgling

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def foreign_cwd(tmp_path, monkeypatch):
    """Run with a CWD that is neither the repo nor inside it."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_session_root_is_the_connection_root(foreign_cwd):
    con = fledgling.connect(root=REPO, init=False)
    assert con.sql("SELECT _session_root()").fetchone()[0] == REPO


def test_project_overview_works_from_foreign_cwd(foreign_cwd):
    """The macro that exposed this: it globs its root parameter."""
    con = fledgling.connect(root=REPO, init=False)
    rows = con.sql("SELECT * FROM project_overview()").fetchall()
    assert rows, "project_overview returned nothing from a foreign cwd"
    assert any(lang == "Python" for lang, _ext, _n in rows)


def test_sandbox_still_blocks_outside_root(foreign_cwd):
    """The fix must not widen the sandbox — that was the point of #49/#50."""
    con = fledgling.connect(root=REPO, init=False)
    with pytest.raises(Exception) as exc:
        con.sql("SELECT count(*) FROM glob('/etc/**')").fetchone()
    assert "Permission" in type(exc.value).__name__ or "Permission" in str(exc.value)
