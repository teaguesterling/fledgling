# Fledgling: Next Steps

**Last session**: 2026-02-26 (afternoon)
**State**: 138 passing tests (13 expected failures pending P2-001), MCP tools published for code/docs/git

## What Exists

```
fledgling/
  sql/
    source.sql          ✅ 4 macros, 13 tests
    code.sql            ✅ 4 macros, 13 tests
    docs.sql            ✅ 4 macros, 19 tests
    repo.sql            ✅ 5 macros, 18 tests
    conversations.sql   ✅ 13 macros, 31 tests (converted from views)
    sandbox.sql         ✅ resolve() macro + path sandboxing, 12 tests
    tools/
      code.sql          ✅ 4 tool publications (FindDefinitions, FindCalls, FindImports, CodeStructure)
      docs.sql          ✅ 2 tool publications (MDOutline, MDSection)
      git.sql           ✅ 2 tool publications (GitChanges, GitBranches)
      files.sql         ⚠️  Not yet created (P2-001: ListFiles, ReadLines, ReadAsTable)
  tests/
    conftest.py         ✅ Fixtures for all tiers + MCP server + synthetic JSONL data
    test_source.py      ✅ 13 tests
    test_code.py        ✅ 13 tests
    test_docs.py        ✅ 19 tests
    test_repo.py        ✅ 18 tests (includes cross-tier composition)
    test_conversations.py ✅ 31 tests (12 test classes)
    test_sandbox.py     ✅ 12 tests (resolve() + lockdown verification)
    test_mcp_server.py  ✅ 45 tests (32 passing, 13 expected failures pending P2-001)
  docs/
    index.md                    Docs landing page
    getting-started.md          Installation and usage guide
    macros/                     Macro reference (all 5 tiers)
    tasks/                      Task plans (P2-001 through P3-004)
    vision/
      PRODUCT_SPEC.md           5-tier architecture, tool designs
      CONVERSATION_ANALYSIS.md  DuckDB analysis of 270 JSONL files
      CONVERSATION_SCHEMA_DESIGN.md  Schema design doc + blog outline
    planning/
      NEXT_STEPS.md             This file
  pyproject.toml        ✅ Project metadata, dependency groups
  README.md             ✅ Project description and quick example
  mkdocs.yml            ✅ mkdocs-material config
  .readthedocs.yaml     ✅ ReadTheDocs build config
```

All 5 extensions load from DuckDB community on v1.4.4:
`read_lines`, `sitting_duck`, `markdown`, `duck_tails`, `duckdb_mcp`

## Completed

### Conversation macros + tests (2026-02-26 afternoon)

Converted `sql/conversations.sql` from 13 `CREATE VIEW` statements to
`CREATE MACRO ... AS TABLE`. All macros now tested with synthetic JSONL fixture.

**Macros (by tier):**
- Tier 1 (raw_conversations): `sessions()`, `messages()`, `content_blocks()`, `tool_results()`
- Tier 2 (call tier 1): `token_usage()`, `tool_calls()`, `tool_frequency()`, `bash_commands()`
- Tier 3 (call tier 1+2): `session_summary()`, `model_usage()`
- Search: `search_messages(term)`, `search_tool_inputs(term)`
- Loader: `load_conversations(path)`

**DuckDB macro quirks discovered** (documented in auto-memory):
1. Table references in macros resolve at creation time (not call time), even
   with `query_table()`. Only macro-to-macro calls are deferred.
2. The `->>` operator breaks inside `UNION ALL` in macro context. Workaround:
   use `json_extract_string()` instead.
3. LATERAL UNNEST evaluates before WHERE in macros with mixed-type JSON
   columns. Workaround: use CTE to filter before the LATERAL join.

**Tool name inventory:** 104 unique tool names found across ~52k tool calls
in local conversation logs. 24 built-in Claude Code tools + 80 MCP tools
across 9 servers (aidr, blq, duckdb_mcp_test, lq, mess, Notion, context7,
playwright, venv_blq).

### Project rename (2026-02-26 morning)
Renamed from `duck_nest` to `source-sextant`, then to `fledgling`.

### Documentation infrastructure (2026-02-26 morning)
ReadTheDocs + mkdocs-material, macro reference pages, getting started guide.

## Immediate Next

### P2-001: File Tools (ListFiles, ReadLines, ReadAsTable)

The last 3 MCP tools to publish. Requires:
- New macros in `sql/source.sql`: `list_files()`, `read_as_table()`
- Extend `read_source()` with optional `match` and `commit` params
- Create `sql/tools/files.sql` with 3 `mcp_publish_tool()` calls
- 13 tests in `test_mcp_server.py` already written and waiting

See `docs/tasks/P2-001-files-tools.md` for full spec.

### P2-005: Init Script + Config (partially complete)

- ✅ `sql/sandbox.sql` — path resolution and lockdown
- ✅ `tests/conftest.py` — MCP server fixture with memory transport
- ⚠️ `init-fledgling.sql` — entry point for `duckdb -init` (not yet created)
- ⚠️ `config/claude-code.example.json` — example MCP config (not yet created)

See `docs/tasks/P2-005-init-and-config.md` for full spec.

### Conversation data loading

The `conversation_macros` fixture showed the load pattern works:
`load_conversations()` → `CREATE TABLE raw_conversations`. For the MCP server,
need to decide: auto-load from `~/.claude/projects/` on startup, or expose
`load_conversations()` as a tool for on-demand loading?

## Phase 3: Polish and Iterate

### Trim settings.json bash whitelist
Once fledgling is running as MCP, start removing bash entries covered
by MCP tools. The conversation analysis showed which ones:
- `cat`, `head`, `tail` → `read_source`
- `grep`, `find` → `find_definitions` / Grep tool
- `git log`, `git diff`, `git show`, `git branch` → repo macros
- `wc`, `sort`, `awk`, `sed` → DuckDB SQL via query tool

### Blog post: Analyzing Claude Code Conversations with DuckDB
The conversation schema design doc has a blog outline. The data is compelling:
849 MB of JSONL, 267K records, tool usage patterns that directly inform
tooling decisions.

### Per-project configuration
Currently fledgling is global. Consider how project-specific tools
would work.

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

Out of scope for fledgling (which is read-only), but the conversation
analysis showed 2,810 git write operations (16.5% of all bash). A
separate server with safety guardrails.
