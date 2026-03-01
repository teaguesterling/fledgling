# Integration Validation

Multi-tool workflows that combine tools across tiers. These test the
kind of real-world usage patterns an agent would follow.

## Explore-then-read workflow

### 8.1 Navigate to a function definition

```
Use Fledgling tools to find where the `call_tool` function is defined
and read its full implementation. Do this in multiple steps:

1. Use FindDefinitions on tests/conftest.py with name_pattern=call_tool
2. Use the start_line and end_line from the result to read the function
   body with ReadLines

Expected: Step 1 finds the definition at a specific line range. Step 2
reads just those lines, showing the complete function implementation
including the auto-fill logic for missing params and the mcp_request call.
```

### 8.2 Understand a section of documentation

```
Use Fledgling tools to understand the DuckDB Quirks section of CLAUDE.md:

1. Use MDOutline on CLAUDE.md to find the section ID for DuckDB Quirks
2. Use MDSection to read the content of that section

Expected: Step 1 shows the section_id (should be "duckdb-quirks").
Step 2 returns the full content with numbered quirks and workarounds.
```

## Cross-reference workflow

### 8.3 Trace a function's usage

```
Use Fledgling tools to understand how resolve() is used:

1. Use FindDefinitions on sql/sandbox.sql to find the resolve macro
2. Use FindCalls on sql/tools/*.sql with name_pattern=resolve to see
   where it's called (note: these may have been replaced with inline
   expressions — if no results, that confirms the P2-009 workaround)
3. Use ListFiles with pattern=sql/tools/*.sql to see all tool files

Expected: Shows the definition of resolve(), its call sites (or lack
thereof after P2-009 workarounds), and the full list of tool files.
```

### 8.4 Review recent changes with context

```
Use Fledgling tools to review the most recent commit:

1. Use GitChanges with count=1 to get the latest commit hash
2. Use ListFiles in git mode with that commit hash and pattern=%.sql
   to see which SQL files existed at that point
3. Use GitBranches to see the current branch context

Expected: Shows the latest commit, the SQL files in that commit, and
the branch context. Demonstrates combining git tools for code review.
```

## Conversation analysis workflow

### 8.5 Analyze your own tool usage

```
Use Fledgling tools to analyze how you use tools:

1. Use ChatToolUsage with limit=10 to see most-used tools overall
2. Use ChatSessions with project=sextant and limit=3 to find recent
   sessions on this project
3. Pick one session_id from step 2 and use ChatDetail to see its
   tool breakdown

Expected: Shows aggregate tool usage patterns, recent project sessions,
and per-session detail. Demonstrates the conversation intelligence tier.
```

## Edge case workflow

### 8.6 Empty results handling

```
Test that tools handle empty results gracefully:

1. Use ListFiles with pattern=nonexistent_xyz_/*.foo
2. Use FindDefinitions on sql/sandbox.sql with name_pattern=nonexistent_%
3. Use MDOutline on sql/sandbox.sql (not a markdown file)

Expected: All three should return empty result tables (headers but no
data rows), not errors. Tools should degrade gracefully when given
valid but unmatched inputs.
```

### 8.7 Large result sets

```
Use Fledgling tools with broad patterns:

1. Use ListFiles with pattern=**/*.py to find all Python files
2. Use FindDefinitions on tests/**/*.py to find all definitions in
   test files
3. Use CodeStructure on tests/conftest.py to get the full structure

Expected: All return results without timeouts or truncation errors.
Result counts should be reasonable (dozens of files, hundreds of
definitions).
```
