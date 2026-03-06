# Fledgling Product Thinking

## What Fledgling Actually Is (March 2026)

A DuckDB-based MCP server that gives agents SQL-composable code intelligence.
Three layers:
1. **Extensions** (sitting_duck, duck_tails, read_lines, markdown) — the engines
2. **SQL macros** (~30 Fledgling-defined) — composable vocabulary
3. **MCP tool publications** (11 tools) — agent entry points

## Current Tool Surface (after March 2026 trim)

**11 published tools:** ReadLines, FindDefinitions, CodeStructure, MDSection,
GitDiffSummary, GitShow, Help, ChatSessions, ChatSearch, ChatToolUsage, ChatDetail

**17 query-only macros:** list_files, project_overview, read_as_table,
find_calls, find_imports, complexity_hotspots, function_callers,
module_dependencies, doc_outline, structural_diff, changed_function_summary,
recent_changes, branch_list, tag_list, file_diff, working_tree_status,
find_code_examples

## What's Unique

The ONLY thing Fledgling does that nothing else can:
1. **AST-based code analysis** — structural understanding, not text matching
2. **SQL composability** — join code structure with git history with complexity
3. **Cross-domain queries** — "show me complex functions in recently changed files"

Everything else is commodity. The unique value is the intersection of
**structural code understanding** and **composability**.

## Fixed Issues (this session)

- project_overview filters .venv, node_modules, __pycache__, etc.
- SKILL.md matches current 11-tool surface
- README matches current tool surface
- Duplicate AST entries filtered (name != '' in find_definitions, code_structure)
- Help tool description references macro catalog
- CodeStructure description cross-references query macros
- test_initial_commit_message window expanded (repo grew past 100 commits)
- changed_function_summary uses real cyclomatic complexity (ast_function_metrics)
- All 223 tests passing (0 failures, 3 xfailed)

## Remaining Problems

### 1. The composition gap
Macros are composable in theory but harder in practice:
- Agents don't know column schemas without consulting Help
- Parameterized macros can't be used in joins easily (e.g., function_callers
  takes a single name, can't join with multiple names from another macro)
- Need qualified_name (sitting_duck#52) to make definition joins trivial

### 2. Macro discoverability
Partially solved by Help('macro-reference') and improved descriptions.
Still gap: agent using query tool doesn't automatically know macros exist.
The query tool description is owned by duckdb_mcp, not Fledgling.

### 3. SQL files poorly parsed
sitting_duck#37: SQL macro names show as 'CREATE', many entries have
empty names. This makes CodeStructure and FindDefinitions nearly useless
on SQL files specifically. Upstream fix needed.

### 4. Chat tools placement
These should eventually be duckdb_mcp examples, not part of Fledgling's
core. However — see quartermaster-pattern.md — the conversation layer
has a deeper purpose as the quartermaster's memory. This reframes the
question: the tools belong in Fledgling, but their audience is the
quartermaster, not the end user.

### 5. No plain text output format
ReadLines and GitDiffFile use json interim format because duckdb_mcp#55
(text format) isn't available. JSON is verbose for line-oriented content.

## Product Direction (prioritized)

### High priority
- **qualified_name** (sitting_duck#52): Universal join key — filed upstream
- **Pre-composed workflow macros**: risky_changes(), etc. — encode domain
  knowledge so agents don't need to write complex joins
- **Plain text output** (duckdb_mcp#55): Would significantly improve
  ReadLines token efficiency

### Medium priority
- Orient macro for single-call project understanding
- Better error messages when glob matches no files
- Kit manifest format for quartermaster pattern

### Future considerations
- Dynamic tool publication (add/remove tools mid-session)
- Quartermaster meta-tool (request_tool for worker→quartermaster signaling)
- Kit effectiveness metrics
- Package distribution (pip/npm)
- Getting-started guide with real examples
