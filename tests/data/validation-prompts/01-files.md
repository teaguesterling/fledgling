# Files Tier Validation

## ListFiles

### 1.1 Filesystem mode — relative glob

```
Use the Fledgling ListFiles tool to find all SQL files in the sql/ directory
(not subdirectories). Use a relative path.

Expected: Returns 7 files (code.sql, conversations.sql, docs.sql, help.sql,
repo.sql, sandbox.sql, source.sql). Paths should be absolute.
```

### 1.2 Filesystem mode — recursive glob

```
Use Fledgling ListFiles to find all Python files in the tests/ directory
recursively. Use the pattern tests/**/*.py.

Expected: Returns test files including conftest.py, test_source.py,
test_code.py, etc. At least 10 files.
```

### 1.3 Filesystem mode — no matches

```
Use Fledgling ListFiles with the pattern nonexistent_xyz_/*.foo

Expected: Returns an empty table (headers only, no data rows).
```

### 1.4 Git mode — HEAD

```
Use Fledgling ListFiles in git mode to list files matching sql/tools/%.sql
at commit HEAD.

Expected: Returns 6 tool files (code.sql, conversations.sql, docs.sql,
files.sql, git.sql, help.sql). Paths should be repo-relative (not absolute).
```

### 1.5 Git mode — specific commit

```
Use Fledgling ListFiles in git mode to list all files matching %.md at
commit main.

Expected: Returns markdown files as they exist on main branch. Should include
CLAUDE.md, SKILL.md, README.md.
```

## ReadLines

### 1.6 Whole file — relative path

```
Use Fledgling ReadLines to read sql/sandbox.sql (relative path, no line range).

Expected: Returns all 30-31 lines of the file with line numbers. Content
should include the resolve() macro definition.
```

### 1.7 Line range

```
Use Fledgling ReadLines to read lines 26-30 of sql/sandbox.sql.

Expected: Returns exactly 5 lines showing the CREATE OR REPLACE MACRO
resolve(p) definition.
```

### 1.8 Match filter

```
Use Fledgling ReadLines to read tests/conftest.py with match filter "def "
(note the trailing space) to find all function definitions.

Expected: Returns only lines containing "def " with their line numbers.
Should include load_sql, call_tool, mcp_request, list_tools, etc.
```

### 1.9 Match with context

```
Use Fledgling ReadLines to read tests/conftest.py with match "call_tool"
and ctx=2.

Expected: Returns lines matching "call_tool" plus 2 lines of context above
and below each match.
```

### 1.10 Git mode

```
Use Fledgling ReadLines to read sql/sandbox.sql at commit HEAD, lines 1-5.

Expected: Returns the first 5 lines of the file as it exists in the HEAD
commit. Should show the file header comment.
```

## ReadAsTable

### 1.11 TOML file

```
Use Fledgling ReadAsTable to preview .lq/commands.toml.

Expected: Returns structured data from the TOML file showing blq command
configurations.
```

### 1.12 JSON file

```
Use Fledgling ReadAsTable to preview .mcp.json with a limit of 5 rows.

Expected: Returns the MCP server configuration as structured table data.
```
