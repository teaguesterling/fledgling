# Fledgling: Project Conventions

## Architecture

SQL macros first, MCP tools second. Every tool is backed by a reusable macro in `sql/<tier>.sql`. The tool publication in `sql/tools/<tier>.sql` is a thin wrapper using `mcp_publish_tool()`. Never put business logic in tool publications.

## SQL Macro Files (`sql/<tier>.sql`)

### File header

```sql
-- Fledgling: <Tier Name> Macros (<extension_name>)
--
-- Brief description of what this tier provides.
```

### Per-macro comments

Every macro gets a block comment with: name, description, and examples.

```sql
-- macro_name: What it does in one line.
-- Additional context if needed.
--
-- Examples:
--   SELECT * FROM macro_name('arg1');
--   SELECT * FROM macro_name('arg1', 'arg2');
CREATE OR REPLACE MACRO macro_name(...) AS TABLE
    ...
```

### Naming

- Macro names: `snake_case` (SQL convention)
- Column aliases: `snake_case`
- Use `AS TABLE` for all macros that return result sets
- Use `:=` for optional parameters with defaults
- Avoid parameter names that shadow column names in the query body (use qualified `t.column` references or rename the parameter)

## Tool Publication Files (`sql/tools/<tier>.sql`)

### File header

```sql
-- Fledgling: <Tier Name> Tool Publications
--
-- MCP tool publications for <description>.
-- Wraps macros from sql/<tier>.sql.
```

### mcp_publish_tool() call pattern

Always pass all 6 arguments:

```sql
SELECT mcp_publish_tool(
    'ToolName',                    -- 1. PascalCase tool name
    'Description for the agent.',  -- 2. Tool description
    'SELECT * FROM macro(...)',    -- 3. SQL template
    '{...}',                       -- 4. JSON Schema properties
    '["required_param"]',          -- 5. Required params list
    'markdown'                     -- 6. Output format (always 'markdown')
);
```

### Optional parameter handling (duckdb_mcp#19 workaround)

MCP tool params arrive as strings. Omitted params must be sent as the literal string `'null'` by the test harness. Tool templates convert them back:

```sql
-- String param with default
COALESCE(NULLIF($param, ''null''), 'default_value')

-- Integer param with default
COALESCE(TRY_CAST(NULLIF($param, ''null'') AS INT), 10)

-- Optional param → NULL (no default)
NULLIF($param, ''null'')
```

### Path resolution

All file path params must go through `resolve()` for sandbox compatibility:

```sql
-- Single file or glob pattern
resolve($file_path)
resolve($file_pattern)

-- Optional path with fallback to project root
COALESCE(resolve(NULLIF($path, ''null'')), '<session_root>')
```

Git tool paths embed `session_root` at publish time because `getvariable()` is not available in the MCP tool execution context:

```sql
'... ''' || getvariable('session_root') || ''' ...'
```

## DuckDB Quirks

These are hard-won lessons. Don't remove workarounds without verifying the upstream fix.

1. **Table refs validate at macro definition time** — `raw_conversations` must exist before loading `conversations.sql`. Macro-to-macro refs ARE deferred.

2. **sitting_duck#22** — Fixed upstream. `sitting_duck` no longer shadows the `read_lines` extension; both are internal catalog entries and coexist. No workaround needed.

3. **sitting_duck#23** — Python import names are empty; use `peek` column instead.

4. **duckdb#21102** — `allowed_directories` checks absolute paths before `file_search_path` resolution. Fix: the `resolve()` macro.

5. **duckdb#17136** — Extensions must load BEFORE `enable_external_access = false`.

6. **`->>` in UNION ALL** — Breaks inside macros. Use `json_extract_string()` instead.

7. **LATERAL UNNEST in macros** — Evaluates before WHERE with mixed-type JSON. Use CTEs to filter first.

8. **`query_table()` Python collision** — DuckDB's `query_table()` uses Python replacement scans, which collide with `import json`. Use `read_json_auto()`/`read_csv_auto()` with `query()` for dynamic dispatch instead.

9. **Table functions in UNION ALL dead branches** — Table functions like `glob()` may execute even in UNION ALL branches filtered by `WHERE false`, especially in the duckdb_mcp execution context. Use `query()` for conditional table function dispatch.

## Tests

### Philosophy

- Dog-fooding: the repo itself is the primary test data
- Macro tests (`test_<tier>.py`) test SQL logic in isolation
- MCP tests (`test_mcp_server.py`) test the tool publication layer end-to-end
- Don't duplicate: if macro tests cover the SQL, MCP tests only need to verify the tool wiring

### Fixtures (conftest.py)

- `con` — bare DuckDB connection
- `<tier>_macros` — connection with one extension + one macro file
- `all_macros` — all extensions + all macro files
- `mcp_server` — session-scoped, all tools published, memory transport
- `conversation_macros` — synthetic JSONL data + conversation macros

### MCP test helpers

- `call_tool(con, name, args)` — auto-fills missing params with `null`, asserts no error
- `md_row_count(text)` — count data rows in markdown table output
- `mcp_request(con, method, params)` — raw JSON-RPC to memory transport

### Test file loading

`load_sql()` strips comment-only lines before splitting on `;`. This is necessary because DuckDB's Python API doesn't support `.read` and comments may contain semicolons. The function cannot handle semicolons inside string literals that span comment-stripped lines — keep string constants on single lines in SQL files.

## File Organization

```
init-fledgling.sql        Entry point for duckdb -init
sql/
  <tier>.sql              Macro definitions (one file per tier)
  sandbox.sql             resolve() macro + sandbox setup
  tools/<tier>.sql        Tool publications (one file per tier)
config/
  claude-code.example.json  Example MCP server config
tests/
  conftest.py             Fixtures, helpers, synthetic data
  test_<tier>.py          Macro tests (one file per tier)
  test_mcp_server.py      MCP integration tests (all tools)
  test_sandbox.py         Path resolution + lockdown tests
docs/
  tasks/P<n>-<nnn>-*.md   Task plans with status tracking
```

## Extension load order

```
1. LOAD duckdb_mcp                          (before lockdown; duckdb#17136)
2. LOAD read_lines
3. LOAD sitting_duck
4. LOAD markdown
5. LOAD duck_tails
6. SET VARIABLE session_root = ...
7. Load sandbox.sql                         (resolve() macro)
8. Load macro files (source, code, docs, repo)
9. Load tool publication files
10. Filesystem lockdown                     (after all .read commands)
11. Start MCP server
```

<!-- blq:agent-instructions -->
## blq - Build Log Query

Run builds and tests via blq MCP tools, not via Bash directly:
- `mcp__blq_mcp__commands` - list available commands
- `mcp__blq_mcp__run` - run a registered command (e.g., `run(command="test")`)
- `mcp__blq_mcp__register_command` - register new commands
- `mcp__blq_mcp__status` - check current build/test status
- `mcp__blq_mcp__errors` - view errors from runs
- `mcp__blq_mcp__info` - detailed run info (supports relative refs like `+1`, `latest`)
- `mcp__blq_mcp__output` - search/filter captured logs (grep, tail, head, lines)

Do NOT use shell pipes or redirects in commands (e.g., `pytest | tail -20`).
Instead: run the command, then use `output(run_id=N, tail=20)` to filter.
<!-- /blq:agent-instructions -->
