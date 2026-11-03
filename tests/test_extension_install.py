"""Tests for installing the DuckDB extensions fledgling loads.

`LOAD x` does not install x, and ~/.duckdb/extensions is keyed by DuckDB
version, so a fresh environment has nothing to load.  These tests pin the two
pieces that keep a first boot working: the scan that reads the extension names
out of the init chain, and the install-then-retry in load_extensions().

No network and no duckdb CLI needed — FakeStore stands in for the extension
store and records every statement it is given.
"""

import os
import pytest

from fledgling.cli import _init_chain_extensions
from fledgling.connection import load_extensions

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED_LOADS = ["duckdb_mcp", "read_lines", "sitting_duck", "markdown", "duck_tails", "fts"]


class TestInitChainExtensions:
    """The extension list has to come from the SQL, not from a second copy.

    A hardcoded list drifts from what the init chain actually loads, and the
    drift stays silent until a boot fails on the extension nobody added here.
    """

    def test_core_profile_lists_every_load(self):
        entry = os.path.join("init", "init-fledgling-core.sql")
        assert _init_chain_extensions([entry], PROJECT_ROOT) == EXPECTED_LOADS

    def test_analyst_profile_lists_the_same_set(self):
        entry = os.path.join("init", "init-fledgling-analyst.sql")
        assert _init_chain_extensions([entry], PROJECT_ROOT) == EXPECTED_LOADS

    def test_walks_the_chain_rather_than_the_entry_file(self):
        """The profile files carry no LOAD of their own — the LOADs are one
        `.read` away, in init-fledgling-base.sql.  Scanning only the entry
        file would return nothing and so install nothing."""
        entry = os.path.join(PROJECT_ROOT, "init", "init-fledgling-core.sql")
        with open(entry, encoding="utf-8") as fh:
            assert "LOAD " not in fh.read()
        assert _init_chain_extensions([entry], PROJECT_ROOT) == EXPECTED_LOADS

    def test_absent_and_empty_paths_are_skipped(self):
        """mcp_main passes the optional project overlay path unconditionally."""
        assert _init_chain_extensions(["init/does-not-exist.sql", ""], PROJECT_ROOT) == []


class FakeStore:
    """A connection backed by a fake version-keyed extension store.

    LOAD fails unless the extension is in `installed`, which is what an empty
    ~/.duckdb/extensions/v<VER>/ does on a fresh machine.  INSTALL adds to it,
    and only from a repository that carries the extension.
    """

    def __init__(self, installed=(), community=(), core=()):
        self.statements = []
        self.installed = set(installed)
        self.community = set(community)
        self.core = set(core)

    def execute(self, statement):
        self.statements.append(statement)
        if statement.startswith("LOAD "):
            name = statement[len("LOAD "):]
            if name not in self.installed:
                raise RuntimeError(f"IO Error: Extension {name!r} not found")
        elif statement.endswith(" FROM community"):
            name = statement[len("INSTALL "):-len(" FROM community")]
            if name not in self.community:
                raise RuntimeError(f"HTTP Error: Failed to download extension {name!r} (HTTP 404)")
            self.installed.add(name)
        elif statement.startswith("INSTALL "):
            name = statement[len("INSTALL "):]
            if name not in self.core:
                raise RuntimeError(f"Extension {name!r} is not a core extension")
            self.installed.add(name)
        return self


class TestLoadExtensionsInstallsWhatItLoads:
    def test_a_warm_extension_is_never_installed(self):
        """Installing unconditionally would cost a network round trip on every
        connect, so INSTALL must only ever follow a failed LOAD."""
        con = FakeStore(installed=["read_lines"])
        load_extensions(con, ["read_lines"])
        assert con.statements == ["LOAD read_lines"]

    def test_a_missing_community_extension_is_installed_then_loaded(self):
        con = FakeStore(community=["read_lines"])
        load_extensions(con, ["read_lines"])
        assert con.statements == [
            "LOAD read_lines",
            "INSTALL read_lines FROM community",
            "LOAD read_lines",
        ]
        assert "read_lines" in con.installed

    def test_a_core_extension_falls_back_to_a_plain_install(self):
        """fts is core, so `INSTALL fts FROM community` is a 404 and the plain
        form is what works."""
        con = FakeStore(core=["fts"])
        load_extensions(con, ["fts"])
        assert con.statements == [
            "LOAD fts",
            "INSTALL fts FROM community",
            "INSTALL fts",
            "LOAD fts",
        ]

    def test_the_original_load_error_is_what_surfaces(self):
        """The LOAD error names the missing extension and its path.  Reporting
        the INSTALL error instead would replace the cause with a download
        failure, which sends the reader to the network rather than the store."""
        con = FakeStore()
        with pytest.raises(RuntimeError, match="IO Error"):
            load_extensions(con, ["sitting_duck"])

    def test_tolerant_still_skips_an_extension_that_will_not_load(self):
        """Read-only cache readers rely on this: build-only extensions cannot
        load on a read-only connection and are not needed to query the index."""
        con = FakeStore()
        load_extensions(con, ["sitting_duck"], tolerant=True)
        assert "sitting_duck" not in con.installed
