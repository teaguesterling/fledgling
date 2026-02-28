# Fledgling Skill Guide

Fledgling gives you structured, token-efficient access to the codebase you're working in. Instead of reading raw files and guessing at structure, you get targeted tools backed by SQL macros and real parsers (AST for code, markdown parser for docs, git for history).

## Quick Reference

| Tool | Purpose |
|------|---------|
| **Help** | This guide. Call with no args for outline, or a section ID for details. |
| **ListFiles** | Find files by glob pattern or git tree. |
| **ReadLines** | Read file lines with optional range, context, and match filtering. |
| **ReadAsTable** | Preview structured data (CSV, JSON) as tables. |
| **FindDefinitions** | AST-based search for functions, classes, variables. |
| **FindCalls** | Find where functions/methods are called (AST, not grep). |
| **FindImports** | Find import/include/require statements. |
| **CodeStructure** | Top-level overview: what's defined in each file. |
| **MDOutline** | Table of contents for markdown files. |
| **MDSection** | Read a specific section from a markdown file. |
| **GitChanges** | Recent commit history. |
| **GitBranches** | List branches with current branch marked. |
| **query** | Run arbitrary SQL against any of the above macros. |

## File Navigation

### ListFiles

Find files matching a glob pattern. Good for discovering project structure.

```
ListFiles(pattern="src/**/*.py")           # all Python files under src/
ListFiles(pattern="*.md")                  # markdown in current dir
ListFiles(pattern="sql/%", commit="HEAD")  # git mode: SQL LIKE syntax
```

Git mode (with `commit`) uses SQL LIKE wildcards (`%`, `_`) instead of globs.

### ReadLines

Read file content with precision. Replaces cat/head/tail with structured output.

```
ReadLines(file_path="src/main.py")                    # whole file
ReadLines(file_path="src/main.py", lines="10-25")     # line range
ReadLines(file_path="src/main.py", lines="42", ctx="5")  # line 42 ± 5 lines
ReadLines(file_path="src/main.py", match="import")    # only matching lines
ReadLines(file_path="src/main.py", lines="1-50", match="def")  # combined
ReadLines(file_path="src/main.py", commit="HEAD~1")   # previous version
```

### ReadAsTable

Preview structured data files as formatted tables.

```
ReadAsTable(file_path="data/results.csv")
ReadAsTable(file_path="config.json", limit="20")
```

Supports CSV, JSON, and other formats DuckDB can auto-detect.

## Code Intelligence

All code tools use AST parsing (via sitting_duck), not text matching. They work across Python, JavaScript/TypeScript, Rust, Go, and more.

### FindDefinitions

Find where things are defined: functions, classes, methods, variables.

```
FindDefinitions(file_pattern="src/**/*.py")                # all definitions
FindDefinitions(file_pattern="src/**/*.py", name_pattern="parse%")  # names starting with "parse"
FindDefinitions(file_pattern="lib/*.ts", name_pattern="%Handler")   # names ending with "Handler"
```

The `name_pattern` uses SQL LIKE wildcards: `%` matches any sequence, `_` matches one character.

### FindCalls

Find call sites — where functions and methods are invoked.

```
FindCalls(file_pattern="src/**/*.py")
FindCalls(file_pattern="src/**/*.py", name_pattern="connect%")
```

### FindImports

Find import/require/include statements across languages.

```
FindImports(file_pattern="src/**/*.py")
FindImports(file_pattern="src/**/*.ts")
```

### CodeStructure

High-level overview of what's defined in files, with line counts. Good first step to understand unfamiliar code.

```
CodeStructure(file_pattern="src/**/*.py")
CodeStructure(file_pattern="lib/auth.ts")
```

## Documentation

### MDOutline

Get the table of contents of markdown files. Returns section IDs you can pass to MDSection.

```
MDOutline(file_pattern="docs/**/*.md")
MDOutline(file_pattern="README.md", max_level="2")  # only h1 and h2
```

### MDSection

Read a specific section by ID. Use MDOutline first to discover IDs.

```
MDSection(file_path="docs/guide.md", section_id="installation")
MDSection(file_path="README.md", section_id="getting-started")
```

Returns the section and its children (subsections).

## Git

### GitChanges

Recent commit log. Replaces `git log --oneline`.

```
GitChanges()              # last 10 commits
GitChanges(count="5")     # last 5 commits
```

### GitBranches

List all branches with the current branch marked.

```
GitBranches()
```

## Workflows

### Explore an Unfamiliar Codebase

1. `ListFiles(pattern="**/*.py")` — see what files exist
2. `CodeStructure(file_pattern="src/**/*.py")` — understand what's defined where
3. `MDOutline(file_pattern="*.md")` — check for documentation
4. `MDSection(file_path="README.md", section_id="...")` — read relevant docs

### Understand a Function

1. `FindDefinitions(file_pattern="src/**/*.py", name_pattern="my_func%")` — find where it's defined
2. `ReadLines(file_path="src/module.py", lines="42-80")` — read the implementation
3. `FindCalls(file_pattern="src/**/*.py", name_pattern="my_func%")` — find where it's called

### Review Recent Changes

1. `GitChanges(count="5")` — see what changed recently
2. `ListFiles(pattern="sql/%", commit="HEAD")` — browse files at a revision
3. `ReadLines(file_path="src/changed.py", commit="HEAD~1")` — compare with previous version

### Analyze Dependencies

1. `FindImports(file_pattern="src/**/*.py")` — see all imports
2. `FindCalls(file_pattern="src/**/*.py", name_pattern="module%")` — find usage of a specific module

## SQL Queries

The `query` tool lets you run arbitrary SQL using the underlying macros directly. This is useful for filtering, joining, or aggregating results beyond what individual tools expose.

```sql
-- Find large Python files
SELECT file_path, line_count
FROM list_files('src/**/*.py')
WHERE line_count > 200
ORDER BY line_count DESC;

-- Cross-reference: definitions that are never called
SELECT d.name, d.file_path, d.line
FROM find_definitions('src/**/*.py') d
LEFT JOIN find_calls('src/**/*.py') c ON d.name = c.name
WHERE c.name IS NULL;

-- Documentation coverage: files without corresponding docs
SELECT f.file_path
FROM list_files('src/**/*.py') f
WHERE NOT EXISTS (
    SELECT 1 FROM list_files('docs/**/*.md') d
    WHERE d.file_path LIKE '%' || replace(f.file_name, '.py', '.md')
);
```

## Tips

### Glob Patterns

- `*` matches within a directory: `src/*.py`
- `**` matches across directories: `src/**/*.py`
- Combine extensions: `src/**/*.{py,ts}`
- Git mode uses SQL LIKE: `%` for any sequence, `_` for single character

### Path Handling

- Paths are resolved relative to the project root
- Use absolute paths when outside the project
- Git mode paths are always repo-relative

### Output Format

All tools return markdown tables. When using the `query` tool, results are also formatted as markdown by default.

### Token Efficiency

- Use `MDOutline` before `MDSection` to avoid reading irrelevant docs
- Use `CodeStructure` before `ReadLines` to find the right file and line range
- Use `FindDefinitions` with `name_pattern` to narrow results
- Use `ReadLines` with `lines` and `match` to read only what you need
- Use `ListFiles` to verify paths before reading
