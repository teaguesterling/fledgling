---
name: review-changes
description: Use when reviewing code changes, PRs, or recent commits — structured review using fledgling's diff, structural analysis, and complexity tools
---

# Review Changes with Fledgling

## Overview

Code review with fledgling is more systematic than reading diffs in a terminal. You get structural analysis (what definitions changed), complexity metrics (did it get more complex?), and cross-referencing (who calls the changed functions?).

**Announce at start:** "I'm using fledgling to review these changes."

## Review Workflow

### Step 1: What Changed? (File Level)

```
GitDiffSummary(from_rev='main', to_rev='HEAD')
```

This gives you the file-level manifest: added, deleted, modified files with sizes. Prioritize the largest changes.

### Step 2: What Changed? (Function Level)

```sql
-- Via query tool
SELECT * FROM changed_function_summary('main', 'HEAD', '**/*.py')
ORDER BY cyclomatic DESC;
```

This is the key fledgling advantage — you see which functions were added/modified/removed AND their complexity. High-complexity new functions need the most scrutiny.

### Step 3: Read the Diffs

For each important file:

```
GitDiffFile(file='src/parser.py', from_rev='main', to_rev='HEAD')
```

Text format shows clean unified diff with `+`/`-` prefixes.

### Step 4: Understand Context

For non-obvious changes, read surrounding code:

```
ReadLines(file_path='src/parser.py', lines='42', ctx='15')
CodeStructure('src/parser.py')
```

### Step 5: Check Impact

Who calls the changed functions?

```sql
-- For each modified function, check callers
SELECT * FROM function_callers('src/**/*.py', 'parse_config');
```

Were dependencies changed?

```
FindInAST('src/parser.py', 'imports')
```

### Step 6: Compare Versions

See the old implementation:

```
GitShow(file='src/parser.py', rev='main')
```

## Review Checklist Queries

```sql
-- New functions without tests (heuristic: new defs not in test files)
SELECT d.name, d.file_path
FROM changed_function_summary('main', 'HEAD', 'src/**/*.py') d
WHERE d.change_status = 'added'
  AND d.name NOT IN (
    SELECT name FROM find_in_ast('tests/**/*.py', 'calls')
  );

-- Complexity increases (functions that got harder to understand)
SELECT * FROM changed_function_summary('main', 'HEAD', '**/*.py')
WHERE cyclomatic > 5 ORDER BY cyclomatic DESC;

-- Large new files (might need splitting)
SELECT * FROM file_changes('main', 'HEAD')
WHERE status = 'added' AND bytes > 5000;
```

## Integration

- Use **jetsam** for the git workflow (PR creation, commit management)
- Use **blq** to run tests on the changes
- Use **fledgling** for the analysis (this skill)
