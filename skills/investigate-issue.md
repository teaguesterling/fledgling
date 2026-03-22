---
name: investigate-issue
description: Use when investigating a bug, test failure, or unexpected behavior — structured investigation using fledgling tools for code analysis and git history
---

# Investigate Issues with Fledgling

## Overview

When debugging, the natural instinct is to `grep` and `cat` through files. Fledgling provides structured alternatives that are faster, more targeted, and produce less noise.

**Announce at start:** "I'm using fledgling to investigate this issue."

## Investigation Workflow

### Step 1: Locate the Code

Start from what you know (error message, function name, file path) and narrow down.

**If you have a function name:**
```
FindDefinitions('**/*.py', 'parse_config')    → where it's defined
function_callers('**/*.py', 'parse_config')   → who calls it
```

**If you have a file but not a location:**
```
CodeStructure('src/parser.py')                → what's in the file + complexity
FindInAST('src/parser.py', 'calls')           → what it calls
```

**If you have an error message keyword:**
```
ReadLines(file_path='src/parser.py', match='validate')  → lines containing the term
FindInAST('**/*.py', 'calls', 'validate%')              → all call sites
```

### Step 2: Understand the Code

Once you've located the relevant code, read it with context:

```
ReadLines(file_path='src/parser.py', lines='42', ctx='10')  → 10 lines around line 42
```

Check what the function does:
```sql
-- Via query tool: get the full function with context
SELECT * FROM read_source('src/parser.py', '42-80')
```

### Step 3: Check History

Was this code recently changed? By whom?

```
GitDiffSummary(from_rev='HEAD~20', to_rev='HEAD')           → what files changed
GitDiffFile(file='src/parser.py', from_rev='HEAD~5', to_rev='HEAD') → line-level diff
GitShow(file='src/parser.py', rev='HEAD~5')                  → old version
```

```sql
-- Via query tool: which functions changed and got more complex?
SELECT * FROM changed_function_summary('HEAD~10', 'HEAD', 'src/**/*.py')
WHERE cyclomatic > 3 ORDER BY cyclomatic DESC;
```

### Step 4: Trace Dependencies

What does the broken code depend on?

```
FindInAST('src/parser.py', 'imports')                        → external deps
FindInAST('src/parser.py', 'calls')                          → function calls
module_dependencies('src/**/*.py', 'myapp')                  → import graph
```

### Step 5: Check Related Code

Find similar patterns or related implementations:

```sql
-- Other functions with similar names
SELECT * FROM find_definitions('src/**/*.py', '%parse%');

-- Other files that import the same module
SELECT file_path FROM find_in_ast('src/**/*.py', 'imports')
WHERE context LIKE '%parser%';

-- Complexity hotspots in the same area
SELECT * FROM complexity_hotspots('src/parser*.py', 10);
```

## Combining with blq

When the investigation leads to running tests:

```
blq run test                                   → run full suite
blq errors                                     → see failures
blq output --grep "parser" --context 3         → search test output
```

Then back to fledgling for the code:
```
ReadLines(file_path='src/parser.py', lines='42-60')  → read the fix target
```

## Combining with jetsam

Track your investigation:
```
jetsam save    → snapshot current state
jetsam diff    → see what you've changed so far
jetsam log     → check recent git history
```

## Key Principles

1. **Locate before reading** — use FindDefinitions/FindInAST to find the right file and line, THEN ReadLines to read it
2. **Structure over text** — use CodeStructure for overview, not `cat file | head`
3. **History is data** — use GitDiffSummary and changed_function_summary to understand what changed and where
4. **Compose queries** — the query tool lets you join across macros for questions like "which complex functions were recently modified?"
5. **Surgical reads** — always use `lines` and `match` parameters rather than reading entire files
