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

Tool templates use `_resolve()` and `_session_root()` — literal-backed macros that work in the MCP execution context where `getvariable()` returns NULL. These macros are created externally (`bin/fledgling` via `-cmd`, `conftest.py` via `create_resolve_macros()`) with the session root baked into the macro body as a string literal.

The variable-backed `resolve()` in `sandbox.sql` still works for direct SQL and macro bodies, but must NOT be used in `mcp_publish_tool()` templates.

```sql
-- Required file path
_resolve($file_path)

-- Optional path with fallback to project root
COALESCE(_resolve(NULLIF($path, ''null'')), _session_root())

-- Bare project root (no path parameter)
_session_root()
```

Why not a subquery-based approach: DuckDB table functions reject subqueries as arguments (quirk #10), so macros containing `(SELECT ... FROM table)` cannot be passed to `list_files()`, `read_source()`, etc. The literal-based macros avoid this entirely.

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

10. **C++ table functions reject column refs and subqueries in macros** — `text_diff_lines(r.col)` fails with "does not support lateral join column parameters". Subqueries in macro arguments also rejected (e.g., a macro containing `(SELECT val FROM table)` cannot be passed to `list_files()`). Workaround: for column refs, reimplement in pure SQL; for path resolution, use literal-backed macros (`_resolve`, `_session_root`) created externally with the value baked in.

## Tests

### Running tests

Use blq MCP tools to run tests — never invoke pytest directly via Bash:

```
mcp__blq_mcp__run(command="test")                        # all tests
mcp__blq_mcp__run(command="test", extra=["-k", "pattern"])  # by pattern
mcp__blq_mcp__run(command="test", extra=["tests/test_code.py"])  # by file
mcp__blq_mcp__run(command="test-collect")                 # list without running
mcp__blq_mcp__errors(run_id=N)                            # inspect failures
mcp__blq_mcp__output(run_id=N, tail=30)                   # view output
```

### Philosophy

- Dog-fooding: the repo itself is the primary test data
- Macro tests (`test_<tier>.py`) test SQL logic in isolation
- MCP tests (`test_mcp_server.py`) test the tool publication layer end-to-end
- Don't duplicate: if macro tests cover the SQL, MCP tests only need to verify the tool wiring

### Fixtures (conftest.py)

- `con` — bare DuckDB connection
- `<tier>_macros` — connection with one extension + one macro file
- `all_macros` — all extensions + all macro files
- `mcp_server` — session-scoped, analyst profile, memory transport
- `conversation_macros` — synthetic JSONL data + conversation macros

### MCP test helpers (conftest.py)

- `create_resolve_macros(con)` — create `_resolve()` and `_session_root()` with embedded literals
- `call_tool(con, name, args)` — auto-fills missing params with `null`, asserts no error
- `md_row_count(text)` — count data rows in markdown table output
- `mcp_request(con, method, params)` — raw JSON-RPC to memory transport
- `_create_mcp_server(profile)` — create a server connection with a given profile
- `_list_tools_for_profile(profile)` — list tools in a subprocess (avoids duckdb_mcp global state)

### Test file loading

`load_sql()` strips comment-only lines before splitting on `;`. This is necessary because DuckDB's Python API doesn't support `.read` and comments may contain semicolons. The function cannot handle semicolons inside string literals that span comment-stripped lines — keep string constants on single lines in SQL files.

## File Organization

```
bin/
  fledgling                 Bash launcher (serve, info subcommands)
init/
  init-fledgling.sql        Default entry point (alias for analyst)
  init-fledgling-analyst.sql  Analyst profile entry point (query enabled)
  init-fledgling-core.sql   Core profile entry point (structured tools only)
  init-fledgling-base.sql   Shared setup (extensions, macros, tools)
sql/
  <tier>.sql                Macro definitions (one file per tier)
  sandbox.sql               resolve() macro + sandbox setup
  tools/<tier>.sql          Tool publications (one file per tier)
  profiles/core.sql         Core profile: memory_limit + mcp_server_options
  profiles/analyst.sql      Analyst profile: memory_limit + mcp_server_options
config/
  claude-code.example.json  Example MCP server config
tests/
  conftest.py               Fixtures, helpers, synthetic data
  test_<tier>.py            Macro tests (one file per tier)
  test_mcp_server.py        MCP integration tests (all tools)
  test_profiles.py          Profile enforcement tests
  test_sandbox.py           Path resolution + lockdown tests
docs/
  tasks/P<n>-<nnn>-*.md    Task plans with status tracking
```

## Extension load order

Per-profile entry points (e.g. `init/init-fledgling-analyst.sql`) compose the
base script with a profile:

```
bin/fledgling (via duckdb -cmd, before init):
  0. SET VARIABLE session_root              (from launcher's $PROJECT_ROOT)
  0. CREATE MACRO _resolve(), _session_root()  (literal-backed, for MCP context)

init/init-fledgling-base.sql:
  1. LOAD duckdb_mcp                        (before lockdown; duckdb#17136)
  2. LOAD read_lines
  3. LOAD sitting_duck
  4. LOAD markdown
  5. LOAD duck_tails
  6. SET VARIABLE session_root = ...         (COALESCE preserves -cmd value)
  7. Load sandbox.sql                       (resolve() macro)
  8. Load macro files (source, code, docs, repo)
  9. Load tool publication files            (use _resolve/_session_root)

Per-profile entry point (e.g. init/init-fledgling-analyst.sql):
  10. Load profile SQL                      (memory_limit + mcp_server_options)
  11. Filesystem lockdown                   (after all .read commands)
  12. Start MCP server with profile options
```

## DuckDB MCP Quirks

10. **duckdb_mcp global server options** — `mcp_server_start()` uses process-global options. The first call in a process sets built-in tool visibility for all subsequent calls, regardless of connection. Profile tests use subprocess isolation (`_list_tools_for_profile()`) to work around this. Not an issue in production (each `duckdb -init` runs in its own process).

11. **duck_tails git:// URIs and allowed_directories** — `duck_tails` resolves `git://` URIs to repo-relative paths internally, so `allowed_directories` sees `git://path/to/file` not the full absolute URI. Only the bare `git://` prefix works as an allowed directory. This is safe given `enable_external_access = false` prevents network access.

12. **duckdb_mcp query tool is not read-only** — The built-in query tool (duckdb_mcp#34) does not enforce read-only access. DDL/DML like `CREATE TABLE` succeeds. `access_mode = 'read_only'` cannot be set after database open. Fix must happen in duckdb_mcp's query tool handler.

13. **duckdb_mcp JSON format doesn't escape double quotes** — (duckdb_mcp#52) The `'json'` output format emits raw `"` inside string values instead of `\"`. `json.loads()` fails on content containing quotes (docstrings, HTML attributes, etc.). Tests use `parse_json_rows(text, keys)` which splits on known key-name delimiters instead of JSON string parsing.

14. **duckdb_mcp markdown format doesn't escape pipes** — (duckdb_mcp#54) The `'markdown'` output format does not escape `|` in cell values, so content containing pipes breaks table structure. Pending upstream fix.

15. **getvariable() returns NULL in MCP tool templates** — Tool SQL templates execute in a context where `getvariable()` returns NULL. DuckDB macros are text-substituted (lazy), so a macro calling `getvariable()` also fails when invoked from a tool template. Fix: `_resolve()` and `_session_root()` macros with the session root baked in as a literal string, created by `bin/fledgling` via `-cmd` and `conftest.py` via `create_resolve_macros()`.

## Tool Output Format Strategy

Three output formats, chosen by what the tool returns:

- **`'markdown'`** — Tabular tools with short, structured values: ListFiles, ProjectOverview, ReadAsTable, FindDefinitions, FindCalls, FindImports, CodeStructure, MDOutline, GitChanges, GitBranches, GitDiffSummary, GitTags, GitStatus, ChatSessions, ChatSearch, ChatToolUsage, ChatDetail, Help.
- **`'json'`** — Tools returning metadata alongside large content blobs: GitShow (1 row, entire file), MDSection (section metadata + full markdown text).
- **`'text'`** (pending duckdb_mcp#55) — Line-oriented content tools where the agent is reading, not parsing structure: ReadLines, GitDiffFile. Tool SQL controls formatting via `printf()`. Currently using `'json'` as interim format until `'text'` is available upstream.

<!-- blq:agent-instructions -->
## blq - Build Log Query

**Always use blq MCP tools instead of running pytest/builds via Bash.**

Registered commands (run via `mcp__blq_mcp__run`):
- `test` — run all tests (`extra=["-v"]` for verbose, `extra=["tests/test_code.py"]` for specific file)
- `test-match` — run tests by name pattern (args: `{pattern: "..."}`)
- `test-collect` — list all tests without running
- `fledgling-tool` — call a Fledgling MCP tool (args: `{tool: "ToolName"}`)

Investigating results:
- `mcp__blq_mcp__errors` — view errors from a run
- `mcp__blq_mcp__output` — search/filter captured logs (grep, tail, head, lines)
- `mcp__blq_mcp__info` — detailed run info (supports relative refs like `+1`, `latest`)

Do NOT use shell pipes or redirects in commands (e.g., `pytest | tail -20`).
Instead: run the command, then use `output(run_id=N, tail=20)` to filter.
<!-- /blq:agent-instructions -->
