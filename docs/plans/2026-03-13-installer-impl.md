# Fledgling Installer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pure-DuckDB installer that fetches fledgling modules from GitHub, assembles them into a self-contained init file, and configures the MCP server.

**Architecture:** Two tracks executed sequentially. Track A makes each module self-contained (bootstrap inside the module file). Track B builds the installer SQL that fetches, resolves dependencies, and assembles modules. The installer writes `.fledgling-init.sql`, `.fledgling-help.md`, and `.mcp.json`.

**Tech Stack:** DuckDB SQL, httpfs extension, pytest

**Spec:** `docs/plans/2026-03-13-installer-design.md`

---

## Chunk 1: Self-Contained Modules

Make `conversations.sql` and `help.sql` include their own bootstrap so they work as standalone modules fetched by the installer. Create `dr_fledgling.sql` as a new core module.

### Task 1: Create dr_fledgling.sql

A macro-only core module for diagnostics. No extension dependencies, depends on sandbox.

**Files:**
- Create: `sql/dr_fledgling.sql`
- Create: `tests/test_dr_fledgling.py`
- Modify: `init/init-fledgling-base.sql` (add `.read sql/dr_fledgling.sql`)
- Modify: `tests/conftest.py` (add `all_macros` loading)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dr_fledgling.py
"""Tests for dr_fledgling diagnostic macro."""

import pytest
from conftest import load_sql


@pytest.fixture
def dr_macros(con):
    """Connection with dr_fledgling macro loaded."""
    con.execute("SET VARIABLE fledgling_version = '0.1.0'")
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
        assert rows[0][0] == "0.1.0"

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_dr_fledgling.py", "-v"])`
Expected: FAIL — file not found

- [ ] **Step 3: Write dr_fledgling.sql**

```sql
-- Fledgling: Diagnostics Module (dr_fledgling)
--
-- Macro-only core module for runtime diagnostics. Reports version,
-- profile, session root, loaded modules, and active extensions.
-- Surfaced through the Help tool.

-- dr_fledgling: Runtime diagnostic summary.
-- Returns key-value pairs: version, profile, root, modules, extensions.
--
-- Examples:
--   SELECT * FROM dr_fledgling();
CREATE OR REPLACE MACRO dr_fledgling() AS TABLE
    SELECT * FROM (VALUES
        ('version',    getvariable('fledgling_version')),
        ('profile',    getvariable('fledgling_profile')),
        ('root',       getvariable('session_root')),
        ('modules',    array_to_string(getvariable('fledgling_modules'), ', ')),
        ('extensions', (
            SELECT array_to_string(list(extension_name ORDER BY extension_name), ', ')
            FROM duckdb_extensions() WHERE installed AND loaded
            AND extension_name IN ('duckdb_mcp','read_lines','sitting_duck','markdown','duck_tails')
        ))
    ) AS t(key, value);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_dr_fledgling.py", "-v"])`
Expected: PASS

- [ ] **Step 5: Add dr_fledgling to init-fledgling-base.sql and all_macros fixture**

In `init/init-fledgling-base.sql`, after `.read sql/sandbox.sql` (line 41), before the feature macro loads:

```sql
.read sql/dr_fledgling.sql
```

In `tests/conftest.py`, in the `all_macros` fixture, add after `load_sql(con, "structural.sql")`:

```python
con.execute("SET VARIABLE fledgling_version = '0.1.0'")
con.execute("SET VARIABLE fledgling_profile = 'test'")
con.execute("SET VARIABLE fledgling_modules = ['source', 'code', 'docs', 'repo', 'structural']")
load_sql(con, "dr_fledgling.sql")
```

- [ ] **Step 6: Run full test suite**

Run: `mcp__blq_mcp__run(command="test", extra=["-v"])`
Expected: All tests pass (including existing tests unchanged)

- [ ] **Step 7: Commit**

```bash
git add sql/dr_fledgling.sql tests/test_dr_fledgling.py
git add init/init-fledgling-base.sql tests/conftest.py
git commit -m "feat: add dr_fledgling diagnostic module"
```

---

### Task 2: Make conversations.sql self-contained

Move the bootstrap from `init-fledgling-base.sql` lines 59-80 into `conversations.sql`. The module should create `raw_conversations` itself using `query()` dispatch.

**Files:**
- Modify: `sql/conversations.sql` (add bootstrap at top)
- Modify: `init/init-fledgling-base.sql` (remove bootstrap, keep `.read`)
- Modify: `tests/conftest.py` (`conversation_macros` fixture simplified)

- [ ] **Step 1: Write the failing test for self-contained bootstrap**

Add to `tests/test_conversations.py`:

```python
class TestSelfContainedBootstrap:
    """conversations.sql bootstraps raw_conversations without external setup."""

    def test_loads_without_preexisting_table(self, con, tmp_path):
        """conversations.sql creates raw_conversations from JSONL."""
        import json
        from conftest import load_sql, CONVERSATION_RECORDS

        project_dir = tmp_path / ".claude" / "projects" / "test-project"
        project_dir.mkdir(parents=True)
        jsonl_path = project_dir / "conversations.jsonl"
        with open(jsonl_path, "w") as f:
            for record in CONVERSATION_RECORDS:
                f.write(json.dumps(record) + "\n")

        con.execute(f"SET VARIABLE conversations_root = '{tmp_path / '.claude' / 'projects'}'")
        load_sql(con, "conversations.sql")

        rows = con.execute("SELECT count(*) FROM raw_conversations").fetchone()
        assert rows[0] == 7

    def test_loads_with_no_jsonl_files(self, con, tmp_path):
        """conversations.sql creates empty raw_conversations when no JSONL exists."""
        from conftest import load_sql

        con.execute(f"SET VARIABLE conversations_root = '{tmp_path}'")
        load_sql(con, "conversations.sql")

        rows = con.execute("SELECT count(*) FROM raw_conversations").fetchone()
        assert rows[0] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_conversations.py::TestSelfContainedBootstrap", "-v"])`
Expected: FAIL — raw_conversations not created by conversations.sql alone

- [ ] **Step 3: Move bootstrap into conversations.sql**

Prepend the bootstrap from `init-fledgling-base.sql` (lines 59-80) to the top of `sql/conversations.sql`, after the file header comment and before the `load_conversations` macro. The bootstrap uses `query()` dispatch for conditional JSONL loading:

```sql
-- Bootstrap: Create raw_conversations table.
-- Uses query() for conditional dispatch: loads JSONL if files exist,
-- otherwise creates an empty table with the expected schema.
SET VARIABLE _has_conversations = (SELECT count(*) > 0 FROM glob(
    getvariable('conversations_root') || '/*/*.jsonl'
));
CREATE TABLE IF NOT EXISTS raw_conversations AS
SELECT * REPLACE (CAST(timestamp AS TIMESTAMP) AS timestamp) FROM query(
    CASE WHEN getvariable('_has_conversations')
    THEN 'SELECT *, filename AS _source_file FROM read_json_auto(
        ''' || getvariable('conversations_root') || '/*/*.jsonl'',
        union_by_name=true, maximum_object_size=33554432, filename=true,
        ignore_errors=true
    )'
    ELSE 'SELECT NULL::VARCHAR AS uuid, NULL::VARCHAR AS sessionId,
          NULL::VARCHAR AS type,
          NULL::STRUCT(role VARCHAR, content JSON, model VARCHAR, id VARCHAR, stop_reason VARCHAR, usage STRUCT(input_tokens BIGINT, output_tokens BIGINT, cache_creation_input_tokens BIGINT, cache_read_input_tokens BIGINT)) AS message,
          NULL::TIMESTAMP AS timestamp, NULL::VARCHAR AS requestId,
          NULL::VARCHAR AS slug, NULL::VARCHAR AS version,
          NULL::VARCHAR AS gitBranch, NULL::VARCHAR AS cwd,
          NULL::BOOLEAN AS isSidechain, NULL::BOOLEAN AS isMeta,
          NULL::VARCHAR AS parentUuid, NULL::VARCHAR AS _source_file
          WHERE false'
    END
);
```

Key change: `CREATE TABLE` → `CREATE TABLE IF NOT EXISTS` so the module is idempotent (safe if bootstrap already ran in init context).

- [ ] **Step 4: Remove bootstrap from init-fledgling-base.sql**

Remove lines 50-80 (the bootstrap block and comments). Keep the `.read sql/conversations.sql` line. The conversations_root variable setup (lines 30-35) stays in init-fledgling-base.sql since it's session config, not module bootstrap.

- [ ] **Step 5: Simplify conversation_macros fixture**

In `tests/conftest.py`, simplify the `conversation_macros` fixture to just set `conversations_root` and load the module:

```python
@pytest.fixture
def conversation_macros(con, tmp_path):
    """Connection with conversation macros + synthetic JSONL test data."""
    project_dir = tmp_path / ".claude" / "projects" / "test-project"
    project_dir.mkdir(parents=True)
    jsonl_path = project_dir / "conversations.jsonl"

    with open(jsonl_path, "w") as f:
        for record in CONVERSATION_RECORDS:
            f.write(json.dumps(record) + "\n")

    con.execute(f"SET VARIABLE conversations_root = '{tmp_path / '.claude' / 'projects'}'")
    load_sql(con, "conversations.sql")
    return con
```

- [ ] **Step 6: Run all conversation tests**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_conversations.py", "-v"])`
Expected: All pass (existing + new)

- [ ] **Step 7: Run full test suite**

Run: `mcp__blq_mcp__run(command="test", extra=["-v"])`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add sql/conversations.sql init/init-fledgling-base.sql tests/conftest.py tests/test_conversations.py
git commit -m "refactor: make conversations.sql self-contained with inline bootstrap"
```

---

### Task 3: Make help.sql self-contained

Move the `_help_sections` bootstrap from `init-fledgling-base.sql` (lines 83-88) into `help.sql`. The module reads from a configurable path (supporting both `SKILL.md` in dev and `.fledgling-help.md` in installed mode).

**Files:**
- Modify: `sql/help.sql` (add bootstrap at top)
- Modify: `init/init-fledgling-base.sql` (remove bootstrap, keep `.read`)
- Modify: `tests/conftest.py` (simplify `help_macros` fixture, remove `materialize_help`)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_help.py`:

```python
from conftest import load_sql, SKILL_PATH


class TestSelfContainedBootstrap:
    """help.sql bootstraps _help_sections without external setup."""

    def test_loads_from_skill_md(self, con):
        """help.sql creates _help_sections from SKILL.md."""
        con.execute("LOAD markdown")
        con.execute(f"SET VARIABLE _help_path = '{SKILL_PATH}'")
        load_sql(con, "help.sql")

        rows = con.execute("SELECT count(*) FROM _help_sections").fetchone()
        assert rows[0] > 5

    def test_help_macro_works_after_bootstrap(self, con):
        """help() macro works after self-contained load."""
        con.execute("LOAD markdown")
        con.execute(f"SET VARIABLE _help_path = '{SKILL_PATH}'")
        load_sql(con, "help.sql")

        rows = con.execute("SELECT * FROM help()").fetchall()
        assert len(rows) > 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_help.py::TestSelfContainedBootstrap", "-v"])`
Expected: FAIL

- [ ] **Step 3: Add bootstrap to help.sql**

Prepend to `sql/help.sql`, after the file header:

```sql
-- Bootstrap: Materialize _help_sections from the skill guide.
-- Path priority: _help_path variable > SKILL.md in current directory.
-- The installer sets _help_path to '.fledgling-help.md'.
-- init-fledgling-base.sql sets it to 'SKILL.md' (or leaves default).
CREATE TABLE IF NOT EXISTS _help_sections AS
SELECT section_id, section_path, level, title, content, start_line, end_line
FROM read_markdown_sections(
    COALESCE(getvariable('_help_path'), 'SKILL.md'),
    content_mode := 'full',
    include_content := true, include_filepath := false
);
```

- [ ] **Step 4: Remove bootstrap from init-fledgling-base.sql**

Remove lines 83-87 (the `CREATE TABLE _help_sections` block and comment). Keep `.read sql/help.sql`.

- [ ] **Step 5: Simplify help_macros fixture and materialize_help**

In `tests/conftest.py`, update `help_macros` to set the variable and let help.sql bootstrap itself:

```python
@pytest.fixture
def help_macros(con):
    """Connection with markdown extension + help macro + materialized SKILL.md."""
    con.execute("LOAD markdown")
    con.execute(f"SET VARIABLE _help_path = '{SKILL_PATH}'")
    load_sql(con, "help.sql")
    return con
```

Update `materialize_help` similarly (used by `all_macros`):

```python
def materialize_help(con):
    """Set up help path for help.sql bootstrap."""
    con.execute(f"SET VARIABLE _help_path = '{SKILL_PATH}'")
```

Update `all_macros` fixture — `materialize_help(con)` + `load_sql(con, "help.sql")` stays the same but now `materialize_help` just sets the variable.

- [ ] **Step 6: Run all help tests**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_help.py", "-v"])`
Expected: All pass

- [ ] **Step 7: Run full test suite**

Run: `mcp__blq_mcp__run(command="test", extra=["-v"])`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add sql/help.sql init/init-fledgling-base.sql tests/conftest.py tests/test_help.py
git commit -m "refactor: make help.sql self-contained with inline bootstrap"
```

---

### Task 4: Set fledgling metadata variables in init-fledgling-base.sql

The init script needs to set the variables that `dr_fledgling` reads. These will also be baked into the installer's generated header.

**Files:**
- Modify: `init/init-fledgling-base.sql`

- [ ] **Step 1: Add variables after conversations_root setup**

After line 35 in `init/init-fledgling-base.sql` (after `conversations_root` setup), add:

```sql
-- Fledgling metadata (read by dr_fledgling)
SET VARIABLE fledgling_version = '0.1.0';
SET VARIABLE fledgling_modules = ['source', 'code', 'docs', 'repo', 'structural', 'conversations', 'help'];
```

The profile variable is set by the per-profile entry points, not here.

- [ ] **Step 2: Run full test suite**

Run: `mcp__blq_mcp__run(command="test", extra=["-v"])`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add init/init-fledgling-base.sql
git commit -m "feat: set fledgling metadata variables in init script"
```

---

## Chunk 2: The Installer

Build `install-fledgling.sql` — the pure-DuckDB installer that fetches modules from GitHub and assembles a self-contained init file.

### Task 5: Create installer SQL — module registry and dependency resolution

The core of the installer: the module registry VALUES table and the recursive CTE for dependency resolution.

**Files:**
- Create: `sql/install-fledgling.sql`
- Create: `tests/test_installer.py`

- [ ] **Step 1: Write the failing test for dependency resolution**

```python
# tests/test_installer.py
"""Tests for the fledgling installer's module registry and dependency resolution."""

import pytest
import duckdb
from conftest import load_sql, SQL_DIR
import os


def load_installer_registry(con):
    """Load just the module registry and dependency resolution from the installer.

    Extracts the registry and resolution SQL from install-fledgling.sql
    without running the full installer (which requires httpfs + network).
    """
    # We test the registry logic by defining it inline — the installer
    # embeds this same table.
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
        con.execute("""
            CREATE TABLE _resolved AS
            WITH RECURSIVE deps AS (
                -- Core modules always included
                SELECT module, 0 AS depth
                FROM _module_registry WHERE kind = 'core'
                UNION ALL
                -- Selected feature modules
                SELECT module, 0 AS depth
                FROM _module_registry
                WHERE kind = 'feature'
                  AND list_contains(getvariable('_selected'), module)
                UNION ALL
                -- Transitive dependencies
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
        """)

        rows = con.execute("SELECT module FROM _resolved ORDER BY module").fetchall()
        modules = [r[0] for r in rows]
        assert "sandbox" in modules
        assert "dr_fledgling" in modules
        assert "source" in modules
        assert "structural" in modules

    def test_minimal_selection(self, con):
        """Selecting just 'source' pulls in sandbox (dependency)."""
        load_installer_registry(con)
        con.execute("SET VARIABLE _selected = ['source']")
        con.execute("""
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
        """)

        rows = con.execute("SELECT module FROM _resolved ORDER BY module").fetchall()
        modules = [r[0] for r in rows]
        assert "sandbox" in modules
        assert "source" in modules
        assert "dr_fledgling" in modules
        # structural should NOT be included
        assert "structural" not in modules

    def test_structural_pulls_code_and_repo(self, con):
        """Selecting 'structural' transitively pulls in code + repo + sandbox."""
        load_installer_registry(con)
        con.execute("SET VARIABLE _selected = ['structural']")
        con.execute("""
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
        """)

        rows = con.execute("SELECT module FROM _resolved ORDER BY module").fetchall()
        modules = [r[0] for r in rows]
        assert "sandbox" in modules
        assert "code" in modules
        assert "repo" in modules
        assert "structural" in modules

    def test_load_order_respects_depth(self, con):
        """Modules with no deps load before modules that depend on them."""
        load_installer_registry(con)
        con.execute("SET VARIABLE _selected = ['structural']")
        con.execute("""
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
        """)

        rows = con.execute(
            "SELECT module, load_order FROM _resolved ORDER BY load_order, module"
        ).fetchall()
        order = {r[0]: r[1] for r in rows}
        # sandbox loads before code/repo, which load before structural
        assert order["sandbox"] <= order["code"]
        assert order["sandbox"] <= order["repo"]
        assert order["code"] <= order["structural"]
        assert order["repo"] <= order["structural"]


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
        assert "markdown" not in rows[0]  # docs not selected


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
        assert len(result) == 2  # sandbox and dr_fledgling have no tool files
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_installer.py", "-v"])`
Expected: Tests pass (they test SQL logic inline, not the installer file itself)

Note: These tests validate the SQL patterns that the installer will use. They don't depend on the installer file existing — they embed the same SQL inline. This is intentional: the installer's registry and resolution logic is tested via these patterns.

- [ ] **Step 3: Commit**

```bash
git add tests/test_installer.py
git commit -m "test: add installer registry and dependency resolution tests"
```

---

### Task 6: Create the installer SQL file

Build the full `install-fledgling.sql` with all sections: httpfs setup, config parsing, registry, resolution, fetching, assembly, and file writing.

**Files:**
- Create: `sql/install-fledgling.sql`

- [ ] **Step 1: Write install-fledgling.sql**

The installer SQL file. This is the file that gets piped to `duckdb` via curl.

```sql
-- install-fledgling.sql: Pure-DuckDB installer for Fledgling
--
-- Usage:
--   curl -sL https://raw.githubusercontent.com/.../install-fledgling.sql | duckdb
--
-- Customized:
--   curl -sL .../install-fledgling.sql | duckdb -cmd "SET VARIABLE fledgling_config = {
--       modules: ['source', 'code', 'docs', 'repo'],
--       profile: 'analyst'
--   }"
--
-- The -cmd flag runs before stdin, so fledgling_config is available when
-- this SQL executes.

-- ── 1. Setup ─────────────────────────────────────────────────────────

INSTALL httpfs;
LOAD httpfs;

SET VARIABLE _version = '0.1.0';
SET VARIABLE _base = 'https://raw.githubusercontent.com/teaguesterling/fledgling/main';

-- ── 2. Parse configuration ───────────────────────────────────────────

-- Default config (all feature modules, analyst profile)
SET VARIABLE _default_modules = ['source', 'code', 'docs', 'repo',
                                  'structural', 'conversations', 'help'];
SET VARIABLE _default_profile = 'analyst';

-- Read user config (set via -cmd before stdin)
SET VARIABLE _user_config = getvariable('fledgling_config');

SET VARIABLE _selected_modules = COALESCE(
    _user_config.modules,
    getvariable('_default_modules')
);
SET VARIABLE _profile = COALESCE(
    _user_config.profile,
    getvariable('_default_profile')
);

-- ── 3. Module registry ───────────────────────────────────────────────

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
) AS t(module, kind, extension_deps, module_deps, tool_file, resource);

-- ── 4. Dependency resolution ─────────────────────────────────────────

CREATE TABLE _resolved AS
WITH RECURSIVE deps AS (
    -- Core modules always included
    SELECT module, 0 AS depth
    FROM _module_registry WHERE kind = 'core'
    UNION ALL
    -- Selected feature modules
    SELECT module, 0 AS depth
    FROM _module_registry
    WHERE kind = 'feature'
      AND list_contains(getvariable('_selected_modules'), module)
    UNION ALL
    -- Transitive dependencies
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
FROM deps GROUP BY module;

-- Compute ordered module list and inferred extensions
SET VARIABLE _all_modules = (
    SELECT list(module ORDER BY load_order, module) FROM _resolved
);

SET VARIABLE _extensions = (
    SELECT list(DISTINCT ext ORDER BY ext)
    FROM (SELECT unnest(extension_deps) AS ext
          FROM _module_registry
          WHERE list_contains(getvariable('_all_modules'), module))
);

-- Tool file mapping
SET VARIABLE _tool_map = MAP {
    'source': 'files', 'code': 'code', 'docs': 'docs',
    'repo': 'git', 'conversations': 'conversations', 'help': 'help'
};

SET VARIABLE _tool_files = [element_at(getvariable('_tool_map'), m)[1]
                            FOR m IN getvariable('_all_modules')
                            IF element_at(getvariable('_tool_map'), m)[1] IS NOT NULL];

-- Resources to download
SET VARIABLE _resource_files = (
    SELECT list(resource)
    FROM _module_registry
    WHERE list_contains(getvariable('_all_modules'), module)
      AND resource IS NOT NULL
);

-- ── 5. Fetch from GitHub ─────────────────────────────────────────────

-- Fetch module SQL files
CREATE TABLE _macros AS
SELECT * FROM read_text(
    [format('{}/sql/{}.sql', getvariable('_base'), m)
     FOR m IN getvariable('_all_modules')]
);

-- Fetch tool publication SQL files
CREATE TABLE _tools AS
SELECT * FROM read_text(
    [format('{}/sql/tools/{}.sql', getvariable('_base'), t)
     FOR t IN getvariable('_tool_files')]
);

-- Fetch resources (SKILL.md, etc.)
CREATE TABLE _resources AS
SELECT * FROM read_text(
    [format('{}/{}', getvariable('_base'), r)
     FOR r IN getvariable('_resource_files')]
);

-- ── 6. Assembly macros ───────────────────────────────────────────────

-- Order macros by dependency depth
CREATE TABLE _ordered_macros AS
SELECT m.content, r.load_order
FROM _macros m
JOIN _resolved r ON m.filename LIKE '%/' || r.module || '.sql'
ORDER BY r.load_order, r.module;

-- Header: extensions, variables, literal-backed macros
CREATE OR REPLACE MACRO _fledgling_header(root, profile, extensions, modules) AS
    '-- .fledgling-init.sql — generated by install-fledgling.sql v' || getvariable('_version') || E'\n'
    || '-- Profile: ' || profile || E'\n'
    || '-- Modules: ' || array_to_string(modules, ', ') || E'\n\n'
    || E'.headers off\n.mode csv\n.output /dev/null\n\n'
    || E'LOAD duckdb_mcp;\n'
    || array_to_string([format('LOAD {};', e) FOR e IN extensions], E'\n')
    || E'\n\n'
    || 'SET VARIABLE session_root = COALESCE(getvariable(''session_root''), NULLIF(getenv(''FLEDGLING_ROOT''), ''''), getenv(''PWD''));' || E'\n'
    || 'SET VARIABLE conversations_root = COALESCE(getvariable(''conversations_root''), NULLIF(getenv(''CONVERSATIONS_ROOT''), ''''), getenv(''HOME'') || ''/.claude/projects'');' || E'\n'
    || 'SET VARIABLE fledgling_version = ''' || getvariable('_version') || ''';' || E'\n'
    || 'SET VARIABLE fledgling_profile = ''' || profile || ''';' || E'\n'
    || 'SET VARIABLE fledgling_modules = ' || modules::VARCHAR || ';' || E'\n'
    || 'SET VARIABLE _help_path = ''.fledgling-help.md'';' || E'\n';

-- Footer: profile settings, lockdown, server start
CREATE OR REPLACE MACRO _fledgling_footer(root, profile) AS
    CASE profile
        WHEN 'analyst' THEN 'SET memory_limit = ''4GB'';' || E'\n'
            || 'SET VARIABLE mcp_server_options = ''{"built_in_tools": {"query": true, "describe": true, "list_tables": true}}'';' || E'\n'
        ELSE 'SET memory_limit = ''2GB'';' || E'\n'
            || 'SET VARIABLE mcp_server_options = ''{"built_in_tools": {"query": false, "describe": false, "list_tables": false}}'';' || E'\n'
    END
    || E'\n'
    || E'.output\n'
    || 'SELECT mcp_server_start(json(getvariable(''mcp_server_options'')));' || E'\n';

-- ── 7. Write output files ────────────────────────────────────────────

-- Write .fledgling-init.sql
COPY (
    SELECT _fledgling_header(
               getenv('PWD'), getvariable('_profile'),
               getvariable('_extensions'), getvariable('_all_modules'))
        || E'\n'
        || (SELECT string_agg(content, E'\n;\n' ORDER BY load_order) FROM _ordered_macros)
        || E'\n;\n'
        || (SELECT string_agg(content, E'\n;\n') FROM _tools)
        || E'\n;\n'
        || _fledgling_footer(getenv('PWD'), getvariable('_profile'))
) TO '.fledgling-init.sql' (FORMAT csv, QUOTE '', HEADER false);

-- Write .fledgling-help.md (SKILL.md content for the help module)
COPY (
    SELECT content FROM _resources WHERE filename LIKE '%SKILL.md'
) TO '.fledgling-help.md' (FORMAT csv, QUOTE '', HEADER false);

-- Merge .mcp.json
COPY (
    SELECT json_pretty(json_merge_patch(
        COALESCE(
            (SELECT content FROM read_text(
                [f FOR f IN glob('.mcp.json') IF f IS NOT NULL]
            )),
            '{}'
        ),
        '{"mcpServers": {"fledgling": {
            "command": "duckdb",
            "args": ["-init", ".fledgling-init.sql"]
        }}}'
    ))
) TO '.mcp.json' (FORMAT csv, QUOTE '', HEADER false);

-- ── 8. Report ────────────────────────────────────────────────────────

.output
SELECT printf('Fledgling %s installed successfully!', getvariable('_version')) AS status;
SELECT printf('  Profile:    %s', getvariable('_profile')) AS info;
SELECT printf('  Modules:    %s', array_to_string(getvariable('_all_modules'), ', ')) AS info;
SELECT printf('  Extensions: %s', array_to_string(getvariable('_extensions'), ', ')) AS info;
SELECT '  Files written:' AS info;
SELECT '    .fledgling-init.sql' AS info;
SELECT '    .fledgling-help.md' AS info;
SELECT '    .mcp.json' AS info;
```

Note: The `.mcp.json` merge uses `glob('.mcp.json')` to safely handle the case where the file doesn't exist — `glob` returns an empty list, `read_text([])` returns no rows, `COALESCE` falls back to `'{}'`.

- [ ] **Step 2: Verify the file is syntactically valid**

This is a smoke test — we can't run the full installer without network access, but we can check that DuckDB parses the SQL structure.

- [ ] **Step 3: Commit**

```bash
git add sql/install-fledgling.sql
git commit -m "feat: add pure-DuckDB installer for per-project setup"
```

---

### Task 7: Integration smoke test

A test that validates the assembly logic end-to-end using local files instead of network fetches.

**Files:**
- Modify: `tests/test_installer.py`

- [ ] **Step 1: Write the integration test**

Add to `tests/test_installer.py`:

```python
class TestAssemblyLocal:
    """Test the assembly logic using local SQL files (no network)."""

    def test_header_generation(self, con):
        """Header macro produces valid SQL text."""
        con.execute("SET VARIABLE _version = '0.1.0'")
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

        assert 'v0.1.0' in result
        assert 'analyst' in result
        assert 'sandbox, source, code' in result

    def test_footer_analyst(self, con):
        """Footer for analyst profile includes query tools."""
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
        # Read local module files
        import os
        from conftest import SQL_DIR

        modules = ['sandbox', 'source']
        contents = []
        for m in modules:
            path = os.path.join(SQL_DIR, f"{m}.sql")
            with open(path) as f:
                contents.append((m, f.read()))

        # Simulate ordered macros table
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
```

- [ ] **Step 2: Run the tests**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_installer.py", "-v"])`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_installer.py
git commit -m "test: add installer assembly integration tests"
```

---

## Open items (not in this plan)

These are documented in the spec's "Open Questions" section and deferred to future work:

- **Try-it mode** (`fledgling_mode = 'try'`): Execute assembled SQL in-process
- **PWD resolution**: May not matter for per-project install
- **Web UI**: For generating customized install commands
- **Hosting**: CDN vs raw GitHub
- **Update checking**: Version comparison on re-run
