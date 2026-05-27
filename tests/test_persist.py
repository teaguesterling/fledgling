"""Tests for the persistent fact-substrate (workstream C).

connect(persist=, read_only=) + build_cache(): a builder writes a file-backed cache
once; readers open it read-only and skip the rebuild. Staleness is keyed on git
content (HEAD + uncommitted changes), not mtime.
"""
import subprocess

import duckdb
import pytest

import fledgling


def _has_build_extensions() -> bool:
    con = duckdb.connect(":memory:")
    try:
        for ext in ("read_lines", "sitting_duck", "markdown", "fts"):
            con.execute(f"LOAD {ext}")
        return True
    except Exception:
        return False
    finally:
        con.close()


pytestmark = pytest.mark.skipif(
    not _has_build_extensions(),
    reason="FTS/AST build extensions unavailable in this environment",
)


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture
def project(tmp_path):
    """A tiny git-tracked project with searchable code + docs."""
    (tmp_path / "mod.py").write_text(
        "def connect_to_database(url):\n"
        '    """Open a connection to the configured database."""\n'
        "    return url\n"
    )
    (tmp_path / "README.md").write_text(
        "# Guide\n\n## Connect\n\nHow to connect to the database.\n"
    )
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_build_cache_creates_file_and_returns_true(project):
    db = project / ".fledgling" / "cache.duckdb"
    built = fledgling.build_cache(str(db), root=str(project))
    assert built is True
    assert db.exists()
    assert fledgling.cache_is_fresh(str(db), root=str(project))


def test_readonly_reader_searches_without_rebuild(project):
    db = project / "cache.duckdb"
    fledgling.build_cache(str(db), root=str(project))
    # Reader opens read-only; the macros + FTS index are already persisted.
    con = fledgling.connect(persist=str(db), read_only=True, root=str(project))
    rows = con.con.execute("SELECT count(*) FROM fts.content").fetchone()[0]
    assert rows > 0, "persisted FTS content should be present without a rebuild"
    hits = con.con.execute("SELECT * FROM search_content('connect') LIMIT 5").fetchall()
    assert hits, "read-only search over the persisted index should return hits"


def test_build_cache_idempotent_when_fresh(project):
    db = project / "cache.duckdb"
    assert fledgling.build_cache(str(db), root=str(project)) is True
    # Nothing changed -> the content key matches -> no rebuild.
    assert fledgling.build_cache(str(db), root=str(project)) is False


def test_cache_stale_on_content_change(project):
    db = project / "cache.duckdb"
    fledgling.build_cache(str(db), root=str(project))
    assert fledgling.cache_is_fresh(str(db), root=str(project))
    # An uncommitted edit shifts the content key (git status --porcelain changes).
    (project / "mod.py").write_text("def connect_to_database(url):\n    return url + '!'\n")
    assert not fledgling.cache_is_fresh(str(db), root=str(project))
    # build_cache then rebuilds (returns True).
    assert fledgling.build_cache(str(db), root=str(project)) is True


def test_readonly_connection_rejects_writes(project):
    db = project / "cache.duckdb"
    fledgling.build_cache(str(db), root=str(project))
    con = fledgling.connect(persist=str(db), read_only=True, root=str(project))
    with pytest.raises(Exception):
        con.con.execute("CREATE TABLE should_fail (x INT)")


def test_persist_roundtrip_macros_survive_reopen(project):
    db = project / "cache.duckdb"
    # Read-write builder persists macros + data.
    fledgling.build_cache(str(db), root=str(project))
    # Fresh read-only reopen: persisted macros are callable without re-creation.
    con = fledgling.connect(persist=str(db), read_only=True, root=str(project))
    hits = con.con.execute("SELECT * FROM search_content('database') LIMIT 5").fetchall()
    assert hits


def test_non_git_project_treated_as_stale(tmp_path):
    """No git repo -> no content key -> cache_is_fresh False (always rebuild)."""
    (tmp_path / "a.py").write_text("def connect(): pass\n")
    (tmp_path / "a.md").write_text("# A\n\nconnect notes\n")
    db = tmp_path / "cache.duckdb"
    fledgling.build_cache(str(db), root=str(tmp_path))
    # key is None (not a git repo) -> never reported fresh.
    assert fledgling.cache_is_fresh(str(db), root=str(tmp_path)) is False
