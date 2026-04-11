"""Tests for the fledgling installer's module registry and dependency resolution."""

import pytest
import duckdb
import os
from conftest import load_sql, SQL_DIR


def load_installer_registry(con):
    """Load the module registry inline (same as what the installer embeds)."""
    con.execute("""
        CREATE TABLE _module_registry AS FROM (VALUES
            ('sandbox',       'core',    [],                              [],                        NULL,             NULL),
            ('dr_fledgling',  'core',    [],                              ['sandbox'],               NULL,             NULL),
            ('source',        'feature', ['read_lines'],                  ['sandbox'],               'files',          NULL),
            ('code',          'feature', ['sitting_duck'],                ['sandbox'],               'code',           NULL),
            ('docs',          'feature', ['markdown'],                    ['sandbox'],               'docs',           NULL),
            ('repo',          'feature', ['duck_tails'],                  ['sandbox'],               'git',            NULL),
            ('structural',    'feature', ['sitting_duck','duck_tails'],   ['sandbox','code','repo'], NULL,             NULL),
            ('conversations', 'feature', [],                              [],                        'conversations',  NULL),
            ('help',          'feature', ['markdown'],                    [],                        'help',           'SKILL.md')
        ) AS t(module, kind, extension_deps, module_deps, tool_file, resource)
    """)


RESOLVE_CTE = """
    CREATE TABLE _resolved AS
    WITH RECURSIVE deps AS (
        SELECT module, 0 AS depth
        FROM _module_registry WHERE kind = 'core'
        UNION ALL
        SELECT module, 0 AS depth
        FROM _module_registry
        WHERE kind = 'feature'
          AND list_contains(getvariable('_selected'), module)
        UNION ALL
        SELECT dep.module, d.depth + 1
        FROM deps d
        JOIN _module_registry dep
          ON list_contains(
            (SELECT module_deps FROM _module_registry WHERE module = d.module),
            dep.module
          )
        WHERE d.depth < 10
    )
    SELECT module, max(depth) AS load_order
    FROM deps GROUP BY module
"""


class TestModuleRegistry:
    def test_registry_has_all_modules(self, con):
        load_installer_registry(con)
        rows = con.execute("SELECT count(*) FROM _module_registry").fetchone()
        assert rows[0] == 9

    def test_core_modules(self, con):
        load_installer_registry(con)
        rows = con.execute(
            "SELECT module FROM _module_registry WHERE kind = 'core' ORDER BY module"
        ).fetchall()
        modules = [r[0] for r in rows]
        assert modules == ["dr_fledgling", "sandbox"]

    def test_feature_modules(self, con):
        load_installer_registry(con)
        rows = con.execute(
            "SELECT module FROM _module_registry WHERE kind = 'feature' ORDER BY module"
        ).fetchall()
        modules = [r[0] for r in rows]
        assert len(modules) == 7


class TestDependencyResolution:
    def test_all_modules_selected(self, con):
        """Selecting all feature modules resolves all modules."""
        load_installer_registry(con)
        con.execute("""
            SET VARIABLE _selected = ['source', 'code', 'docs', 'repo',
                                      'structural', 'conversations', 'help']
        """)
        con.execute(RESOLVE_CTE)

        rows = con.execute("SELECT module FROM _resolved ORDER BY module").fetchall()
        modules = [r[0] for r in rows]
        assert "sandbox" in modules
        assert "dr_fledgling" in modules
        assert "source" in modules
        assert "structural" in modules

    def test_minimal_selection(self, con):
        """Selecting just 'source' pulls in sandbox (dependency) + core modules."""
        load_installer_registry(con)
        con.execute("SET VARIABLE _selected = ['source']")
        con.execute(RESOLVE_CTE)

        rows = con.execute("SELECT module FROM _resolved ORDER BY module").fetchall()
        modules = [r[0] for r in rows]
        assert "sandbox" in modules
        assert "source" in modules
        assert "dr_fledgling" in modules
        assert "structural" not in modules

    def test_structural_pulls_code_and_repo(self, con):
        """Selecting 'structural' transitively pulls in code + repo + sandbox."""
        load_installer_registry(con)
        con.execute("SET VARIABLE _selected = ['structural']")
        con.execute(RESOLVE_CTE)

        rows = con.execute("SELECT module FROM _resolved ORDER BY module").fetchall()
        modules = [r[0] for r in rows]
        assert "sandbox" in modules
        assert "code" in modules
        assert "repo" in modules
        assert "structural" in modules

    def test_load_order_respects_depth(self, con):
        """Leaf dependencies have higher load_order and are assembled first (DESC)."""
        load_installer_registry(con)
        con.execute("SET VARIABLE _selected = ['structural']")
        con.execute(RESOLVE_CTE)

        rows = con.execute(
            "SELECT module, load_order FROM _resolved ORDER BY load_order DESC, module"
        ).fetchall()
        order = {r[0]: r[1] for r in rows}
        # Higher load_order = deeper dependency = should be loaded first
        assert order["sandbox"] >= order["code"]
        assert order["sandbox"] >= order["repo"]
        assert order["code"] >= order["structural"]
        assert order["repo"] >= order["structural"]


class TestExtensionInference:
    def test_infers_extensions(self, con):
        """Extension deps are the union of all selected modules' extension_deps."""
        load_installer_registry(con)
        con.execute("""
            SET VARIABLE _all_modules = ['sandbox', 'dr_fledgling', 'source', 'code']
        """)
        con.execute("""
            CREATE TABLE _extensions AS
            SELECT list(DISTINCT ext ORDER BY ext) AS extensions
            FROM (SELECT unnest(extension_deps) AS ext
                  FROM _module_registry
                  WHERE list_contains(getvariable('_all_modules'), module))
        """)

        rows = con.execute("SELECT extensions FROM _extensions").fetchone()
        assert "read_lines" in rows[0]
        assert "sitting_duck" in rows[0]
        assert "markdown" not in rows[0]


class TestToolFileMapping:
    def test_tool_files_from_map(self, con):
        """Tool file mapping filters modules without tool publications."""
        con.execute("""
            SET VARIABLE _tool_map = MAP {
                'source': 'files', 'code': 'code', 'docs': 'docs',
                'repo': 'git', 'conversations': 'conversations', 'help': 'help'
            }
        """)
        con.execute("""
            SET VARIABLE _modules = ['sandbox', 'source', 'code', 'dr_fledgling']
        """)
        con.execute("""
            SET VARIABLE _tool_files = [element_at(getvariable('_tool_map'), m)[1]
                                        FOR m IN getvariable('_modules')
                                        IF element_at(getvariable('_tool_map'), m)[1] IS NOT NULL]
        """)

        result = con.execute("SELECT getvariable('_tool_files')").fetchone()[0]
        assert "files" in result
        assert "code" in result
        assert len(result) == 2


class TestAssemblyLocal:
    """Test the assembly logic using local SQL files (no network)."""

    def test_header_generation(self, con):
        """Header macro produces valid SQL text."""
        con.execute("SET VARIABLE _version = '0.7.0'")
        con.execute("""
            CREATE OR REPLACE MACRO _fledgling_header(root, profile, extensions, modules) AS
                '-- .fledgling-init.sql — generated by install-fledgling.sql v'
                || getvariable('_version') || E'\\n'
                || '-- Profile: ' || profile || E'\\n'
                || '-- Modules: ' || array_to_string(modules, ', ') || E'\\n'
        """)

        result = con.execute("""
            SELECT _fledgling_header('/test', 'analyst',
                ['read_lines', 'sitting_duck'], ['sandbox', 'source', 'code'])
        """).fetchone()[0]

        assert 'v0.7.0' in result
        assert 'analyst' in result
        assert 'sandbox, source, code' in result

    def test_footer_analyst(self, con):
        """Footer for analyst profile includes 4GB memory."""
        con.execute("""
            CREATE OR REPLACE MACRO _fledgling_footer(root, profile) AS
                CASE profile
                    WHEN 'analyst' THEN 'SET memory_limit = ''4GB'';'
                    ELSE 'SET memory_limit = ''2GB'';'
                END
        """)

        result = con.execute(
            "SELECT _fledgling_footer('/test', 'analyst')"
        ).fetchone()[0]
        assert '4GB' in result

    def test_footer_core(self, con):
        """Footer for core profile uses 2GB."""
        con.execute("""
            CREATE OR REPLACE MACRO _fledgling_footer(root, profile) AS
                CASE profile
                    WHEN 'analyst' THEN 'SET memory_limit = ''4GB'';'
                    ELSE 'SET memory_limit = ''2GB'';'
                END
        """)

        result = con.execute(
            "SELECT _fledgling_footer('/test', 'core')"
        ).fetchone()[0]
        assert '2GB' in result

    def test_local_assembly(self, con, tmp_path):
        """Assemble from local SQL files and verify output structure."""
        modules = ['sandbox', 'source']
        contents = []
        for m in modules:
            path = os.path.join(SQL_DIR, f"{m}.sql")
            with open(path) as f:
                contents.append((m, f.read()))

        con.execute("CREATE TABLE _ordered_macros (content VARCHAR, load_order INT)")
        for i, (name, content) in enumerate(contents):
            con.execute(
                "INSERT INTO _ordered_macros VALUES (?, ?)",
                [content, i]
            )

        assembled = con.execute("""
            SELECT string_agg(content, E'\\n;\\n' ORDER BY load_order)
            FROM _ordered_macros
        """).fetchone()[0]

        assert 'CREATE OR REPLACE MACRO resolve(' in assembled
        assert 'CREATE OR REPLACE MACRO list_files(' in assembled
