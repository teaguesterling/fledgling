# Source Sextant: Next Steps

**Last session**: 2026-02-26
**State**: 6 commits, 63 passing tests, 4 macro tiers working, conversation schema drafted

## What Exists

```
source_sextant/
  sql/
    source.sql          ✅ 4 macros, 13 tests passing
    code.sql            ✅ 4 macros, 13 tests passing
    docs.sql            ✅ 4 macros, 16 tests passing (find_code_examples fixed)
    repo.sql            ✅ 5 macros, 18 tests passing
    conversations.sql   ⚠️  Written by background agent, NOT YET TESTED
  tests/
    conftest.py         ✅ Fixtures for all tiers + all-together
    test_source.py      ✅ 13 tests
    test_code.py        ✅ 13 tests
    test_docs.py        ✅ 16 tests
    test_repo.py        ✅ 18 tests (includes cross-tier composition)
  docs/
    vision/
      PRODUCT_SPEC.md             5-tier architecture, tool designs
      CONVERSATION_ANALYSIS.md    DuckDB analysis of 270 JSONL files
      CONVERSATION_SCHEMA_DESIGN.md  Schema design doc + blog outline
```

All 5 extensions load from DuckDB community on v1.4.4:
`read_lines`, `sitting_duck`, `markdown`, `duck_tails`, `duckdb_mcp`

## Immediate Next: Conversation Tier Tests

The conversation schema (`sql/conversations.sql`) was written by a background
agent and has NOT been validated. It defines:

- `load_conversations(path)` — table-returning macro for JSONL ingestion
- Views: `sessions`, `messages`, `content_blocks`, `tool_calls`,
  `tool_results`, `token_usage`, `tool_frequency`, `bash_commands`,
  `session_summary`, `model_usage`
- Search macros: `search_messages(term)`, `search_tool_inputs(term)`

**Action**: Write `tests/test_conversations.py`. Key things to verify:
1. `load_conversations()` actually loads JSONL from `~/.claude/projects/`
2. Views reference correct columns (the agent may have guessed some names)
3. The JSON unnesting for `tool_calls` works (this was the trickiest part
   in our manual exploration — struct field access from LATERAL UNNEST)
4. `bash_commands` categorization logic matches what we validated manually
5. `search_messages` actually finds content

**Likely issues**: The background agent didn't have access to the manual
exploration we did. It may have gotten JSON field paths wrong. Be prepared
to fix `conversations.sql` alongside writing tests.

## Phase 2: Init Script + MCP Server

Once all macros are tested, wire them up as an actual MCP server.

### 2a. Write `init-source-sextant.sql`

The entry point that loads everything and starts the server:

```sql
LOAD duckdb_mcp;
LOAD read_lines;
LOAD sitting_duck;
LOAD markdown;
LOAD duck_tails;

-- Fix sitting_duck read_lines collision
DROP MACRO TABLE IF EXISTS read_lines;

-- Load macros
-- (Need to figure out how to .read SQL files from init script,
-- or inline all macros into init-source-sextant.sql)

-- Publish MCP tools via mcp_publish_tool()
-- ... one call per tool ...

-- Start server
SELECT mcp_server_start('stdio', '{
    "enable_query_tool": true,
    "enable_execute_tool": false,
    "default_result_format": "markdown"
}');
```

**Open question**: Can `duckdb -init` use `.read` to load separate SQL
files? If not, we may need a build step that concatenates everything
into a single init script, or just inline the macros.

### 2b. Define MCP tool publications

Each macro needs a `mcp_publish_tool()` call. Example:

```sql
SELECT mcp_publish_tool(
    'find_definitions',
    'Find function, class, or variable definitions by name pattern',
    'SELECT * FROM find_definitions($path, $pattern)',
    '{"path": {"type": "string", "description": "File or glob pattern"},
     "pattern": {"type": "string", "description": "Name pattern (SQL LIKE)"}}',
    '["path"]',
    'markdown'
);
```

Need one per tool (~17 tools across 5 tiers). The tool count question
from the spec is real: MCP discovery gets noisy. Consider grouping
or being selective about which macros become tools vs. stay as
power-user SQL.

### 2c. Claude Code configuration

Add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "source_sextant": {
      "command": "duckdb",
      "args": ["-init", "/path/to/source_sextant/init-source-sextant.sql"]
    }
  }
}
```

Write `config/claude-code.example.json` with the template.

### 2d. Test the MCP server end-to-end

Use `duckdb_mcp`'s memory transport for automated testing, or manually
test via Claude Code with the server configured.

## Phase 3: Polish and Iterate

### Trim settings.json bash whitelist
Once source_sextant is running as MCP, start removing bash entries that are
now covered by MCP tools. The conversation analysis showed which ones:
- `cat`, `head`, `tail` → `read_source`
- `grep`, `find` → `find_definitions` / Grep tool
- `git log`, `git diff`, `git show`, `git branch` → repo macros
- `wc`, `sort`, `awk`, `sed` → DuckDB SQL via query tool

### Blog post: Analyzing Claude Code Conversations with DuckDB
The conversation schema design doc has a blog outline. The data is
compelling: 849 MB of JSONL, 267K records, tool usage patterns that
directly inform tooling decisions. Good candidate for a post.

### Per-project configuration
Currently source_sextant is global. Consider how project-specific tools
would work — e.g., project-specific sitting_duck queries, custom
doc_outline filters, conversation scoping.

## Upstream Issues Filed

- **sitting_duck#22**: `read_lines` SQL macro shadows the `read_lines`
  community extension. Workaround: `DROP MACRO TABLE IF EXISTS read_lines`
  after loading sitting_duck.
  https://github.com/teaguesterling/sitting_duck/issues/22

- **sitting_duck#23**: Python import statements have empty `name` field.
  Module names only appear in `peek` column. Workaround: test against
  `peek`/`import_statement` instead of `name`.
  https://github.com/teaguesterling/sitting_duck/issues/23

## Future: Safe Git MCP Server (Separate Project)

Out of scope for source_sextant (which is read-only), but the conversation
analysis showed 2,810 git write operations (16.5% of all bash). A
separate server with safety guardrails:

- `safe_commit(files, message)` — explicit file list, runs hooks
- `safe_push(branch)` — refuses force-push, refuses main/master
- `safe_add(files)` — stage specific files only

This is a different security profile from source_sextant and should remain
a separate server.
