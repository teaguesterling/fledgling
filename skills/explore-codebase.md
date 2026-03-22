---
name: explore-codebase
description: Use when exploring an unfamiliar codebase or answering "what does this project do?" — systematic exploration using fledgling tools instead of bash
---

# Explore Codebase with Fledgling

## Overview

Use fledgling's structured tools instead of bash commands (`find`, `grep`, `cat`, `git log`) to explore a codebase. Fledgling returns structured, composable results that are more token-efficient and easier to reason about.

**Announce at start:** "I'm using fledgling to explore the codebase."

## The Exploration Sequence

Work top-down. Each phase uses specific tools for its purpose.

### Phase 1: Landscape (what's here?)

```
project_overview()              → languages, file counts
list_files('**/*.py')           → find source files
doc_outline('**/*.md')          → find documentation
```

Use `project-overview` first — it tells you the dominant languages and file counts in one call. Then `list-files` with the dominant extensions to see the structure.

**Tool:** `fledgling project-overview` or query `SELECT * FROM project_overview()`

### Phase 2: Architecture (how is it organized?)

```
CodeStructure('src/**/*.py')    → definitions per file, complexity
find_definitions('src/**/*.py') → functions, classes, modules
module_dependencies('src/**/*.py', 'pkg_name') → import graph
```

Use `CodeStructure` for the high-level triage: which files are large, which functions are complex. Then `FindDefinitions` to see what's defined where.

**Key insight:** `CodeStructure` now includes `cyclomatic_complexity`, `descendant_count`, and `children_count`. Sort by complexity to find the important code.

### Phase 3: Dependencies (what connects to what?)

```
FindInAST('src/**/*.py', 'imports')          → what does each file import
module_dependencies('src/**/*.py', 'myapp')  → internal dependency graph
function_callers('src/**/*.py', 'validate')  → who calls this function
```

Use `FindInAST` with `kind='imports'` to see external dependencies. Use `module_dependencies` for the internal graph. Use `function_callers` to trace call chains.

### Phase 4: History (what changed recently?)

```
recent_changes(20)                            → commit history
GitDiffSummary(from_rev='HEAD~10', to_rev='HEAD') → files changed
changed_function_summary('HEAD~10', 'HEAD', '**/*.py') → functions changed with complexity
```

Start with `recent-changes` to understand the velocity and focus areas. Then `GitDiffSummary` to see what files are active. Then `changed_function_summary` for the semantic view.

### Phase 5: Deep Dive (read specific code)

```
ReadLines(file_path='src/main.py')            → full file
ReadLines(file_path='src/main.py', lines='42-60') → specific range
ReadLines(file_path='src/main.py', match='validate') → grep-like filter
MDSection(file_path='README.md', section_id='installation') → doc section
```

Only read full files after you know which ones matter from the previous phases. Use `lines` and `match` to read surgically.

## Composing Queries

Fledgling's real power is SQL composability via the query tool:

```sql
-- Complex functions in recently changed files
SELECT * FROM changed_function_summary('HEAD~5', 'HEAD', '**/*.py')
WHERE cyclomatic > 5 ORDER BY cyclomatic DESC;

-- Files with the most definitions (architectural hubs)
SELECT file_path, count(*) AS def_count
FROM find_definitions('src/**/*.py')
GROUP BY file_path ORDER BY def_count DESC LIMIT 10;

-- What does this project actually call?
SELECT name, count(*) AS call_count
FROM find_in_ast('src/**/*.py', 'calls')
GROUP BY name ORDER BY call_count DESC LIMIT 20;
```

## Anti-Patterns

- **Don't** use `cat` or `head` — use `ReadLines` with line ranges
- **Don't** use `grep -r` — use `FindDefinitions`, `FindInAST`, or `ReadLines` with `match`
- **Don't** use `find . -name` — use `list_files` with glob patterns
- **Don't** use `git log` — use `recent_changes` or `GitDiffSummary`
- **Don't** read a whole file to find one function — use `FindDefinitions` first, then `ReadLines` with the line range

## When to Fall Back to Bash

Fledgling doesn't cover:
- Running builds or tests (use blq)
- Git operations that change state (commits, pushes — use jetsam or git)
- Interactive tools
- Network requests
