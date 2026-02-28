# P2-005: Init Script, Test Fixture, Config & Sandboxing

**Status:** Complete (all files created; sitting_duck#22 workaround removed — fixed upstream)
**Depends on:** P2-001 through P2-004 (all tool categories)
**Estimated scope:** New files + fixture update

## Goal

Create the entry point that ties everything together: the init SQL script
that loads extensions, macros, and tool modules, then starts the MCP server.
Also establish the path sandboxing model, update the test fixture for modular
tool files, and provide an example Claude Code configuration.

## Files

| File | Action | Description |
|------|--------|-------------|
| `sql/sandbox.sql` | Create | `session_root` variable, `resolve()` macro, lockdown |
| `init-fledgling.sql` | Create | Entry point for `duckdb -init` |
| `config/claude-code.example.json` | Create | Example MCP server config |
| `tests/conftest.py` | Update | Load modular tool files + sandbox setup |

## Sandboxing Model

### Problem

DuckDB's `allowed_directories` only matches **absolute paths** — relative
paths fail the check even when `file_search_path` would resolve them to an
allowed directory (see [duckdb#21102](https://github.com/duckdb/duckdb/issues/21102)).
MCP clients send relative paths.

### Solution

1. **Before lockdown**: capture CWD into a variable via `getenv('PWD')`
2. **`resolve(path)`**: scalar macro that prepends `session_root` for relative paths
3. **`allowed_directories`**: set from `session_root` plus user-configurable extras
4. **Lockdown**: `enable_external_access = false`, `lock_configuration = true`
5. **All tool SQL templates** use `resolve($file_path)` instead of bare `$file_path`

### sql/sandbox.sql

```sql
-- Capture project root before lockdown.
-- Override session_root before loading this file to use a custom root.
SET VARIABLE session_root = COALESCE(
    getvariable('session_root'),
    getenv('PWD')
);

-- Additional allowed directories (set before loading this file).
-- Example: SET VARIABLE extra_dirs = ['/data/shared', '/opt/models'];
-- Defaults to empty list if not set.

-- Resolve relative paths against project root.
-- Absolute paths (starting with /) pass through unchanged.
-- When duckdb#21102 is fixed, this can become a no-op.
CREATE OR REPLACE MACRO resolve(p) AS
    CASE WHEN p[1] = '/' THEN p
         ELSE getvariable('session_root') || '/' || p
    END;

-- Lock down filesystem access.
-- session_root is always allowed; extras are appended if set.
SET allowed_directories = list_concat(
    [getvariable('session_root')],
    COALESCE(getvariable('extra_dirs'), [])
);
SET enable_external_access = false;
SET lock_configuration = true;
```

### Usage from init script

```sql
-- Optional: override root and/or add extra dirs before sandbox.sql
-- SET VARIABLE session_root = '/path/to/project';
-- SET VARIABLE extra_dirs = ['/data/shared'];

.read sql/sandbox.sql
```

### Usage from tool SQL templates

```sql
-- All file-reading tools resolve paths through the macro:
SELECT * FROM read_lines(resolve($file_path), ...)
SELECT * FROM read_ast(resolve($file_pattern))
SELECT * FROM read_markdown_sections(resolve($file_pattern), ...)
```

### What's sandboxed

- All `read_lines`, `read_ast`, `read_markdown_*`, `glob()` calls are restricted
  to `session_root` (+ any `extra_dirs`)
- Path traversal (`../../../etc/passwd`) is blocked by DuckDB
- `getenv()` is disabled after lockdown
- Configuration cannot be changed after lockdown

### What's NOT sandboxed (by design)

- Git operations via `duck_tails` (operate on the repo, which is the project root)
- The `query` built-in tool (full SQL access, but filesystem is still locked)

## init-fledgling.sql

Following duckdb_mcp example-06 pattern. Uses `.read` for modularity —
any tool category can be disabled by commenting out its line.

```sql
-- Suppress output during initialization
.headers off
.mode csv
.output /dev/null

-- Load extensions (must happen before sandbox lockdown)
LOAD duckdb_mcp;
LOAD read_lines;
LOAD sitting_duck;
LOAD markdown;
LOAD duck_tails;

-- Fix sitting_duck read_lines collision (sitting_duck#22)
DROP MACRO TABLE IF EXISTS read_lines;

-- Optional: set project root and extra allowed dirs before sandbox
-- SET VARIABLE session_root = '/custom/project/path';
-- SET VARIABLE extra_dirs = ['/data/shared'];

-- Sandbox: capture root, create resolve(), lock filesystem
.read sql/sandbox.sql

-- Load macro definitions
.read sql/source.sql
.read sql/code.sql
.read sql/docs.sql
.read sql/repo.sql

-- Publish MCP tools (comment out to disable a category)
.read sql/tools/files.sql
.read sql/tools/code.sql
.read sql/tools/docs.sql
.read sql/tools/git.sql

-- Restore output and start server
.output stdout
SELECT mcp_server_start('stdio', '{
    "enable_query_tool": true,
    "enable_describe_tool": true,
    "enable_list_tables_tool": true,
    "enable_database_info_tool": false,
    "enable_export_tool": false,
    "enable_execute_tool": false,
    "default_result_format": "markdown"
}');
```

**Note:** `.read` paths are relative to CWD where `duckdb` is invoked,
not relative to the init script. The Claude Code config must set the
correct working directory or use absolute paths.

**Note:** Extensions must load BEFORE `sandbox.sql` because
`enable_external_access = false` blocks extension loading
(see [duckdb#17136](https://github.com/duckdb/duckdb/issues/17136)).

## Test Fixture Update

The fixture mirrors the init script but uses memory transport and
sets `session_root` to `PROJECT_ROOT` explicitly:

```python
@pytest.fixture(scope="session")
def mcp_server():
    con = duckdb.connect(":memory:")
    # Extensions
    con.execute("LOAD read_lines")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD markdown")
    con.execute("LOAD duck_tails")
    con.execute("DROP MACRO TABLE IF EXISTS read_lines")
    # Sandbox (set root before loading sandbox.sql)
    con.execute(f"SET VARIABLE session_root = '{PROJECT_ROOT}'")
    load_sql(con, "sandbox.sql")
    # Macros
    load_sql(con, "source.sql")
    load_sql(con, "code.sql")
    load_sql(con, "docs.sql")
    load_sql(con, "repo.sql")
    # MCP tools
    con.execute("LOAD duckdb_mcp")
    for f in ["tools/files.sql", "tools/code.sql",
              "tools/docs.sql", "tools/git.sql"]:
        load_sql(con, f)
    con.execute("SELECT mcp_server_start('memory')")
    yield con
    con.close()
```

**Note:** The test fixture does NOT lock down filesystem access (no
`enable_external_access = false`) because `tmp_path` files in
`TestReadAsTable` live outside the project root. The sandbox.sql
file should be structured so lockdown can be skipped for testing.

## Example Config (config/claude-code.example.json)

```json
{
  "mcpServers": {
    "fledgling": {
      "command": "duckdb",
      "args": ["-init", "/absolute/path/to/fledgling/init-fledgling.sql"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

Goes in `~/.claude/settings.json` (global) or `.mcp.json` (per-project).
CWD determines the project root (captured as `session_root`).

## Acceptance Criteria

- All 27 MCP tests pass (requires P2-001 through P2-004 complete)
- All 94 existing tests still pass
- `duckdb -init init-fledgling.sql` starts without errors (manual smoke test)
- Tools discoverable via `tools/list` JSON-RPC request
- Files outside `session_root` cannot be read through tools (manual verification)
- Path traversal attempts are blocked
