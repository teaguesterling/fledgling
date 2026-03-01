# Analyst Built-in Tools Validation

These tools are only available in the analyst profile (not core).

## query

### 7.1 Simple query

```
Use Fledgling query to run: SELECT 1 + 1 AS result
Use markdown format.

Expected: Returns a markdown table with one row showing result=2.
```

### 7.2 Query against internal data

```
Use Fledgling query to run:
SELECT count(*) AS session_count FROM sessions()
Use markdown format.

Expected: Returns the count of loaded conversation sessions. Should be
a positive number if conversation data exists.
```

### 7.3 Query with macros

```
Use Fledgling query to run:
SELECT file_path FROM list_files(resolve('sql/*.sql'), NULL) LIMIT 3
Use markdown format.

Expected: May fail with resolve() returning NULL in MCP context (known
issue, see P2-009). If so, use an absolute path or the ListFiles tool
instead. This test documents the limitation.
```

### 7.4 Read-only enforcement

```
Use Fledgling query to run: CREATE TABLE test_rw AS SELECT 1

Expected: Should fail with a permission error. The query tool only
allows read-only operations.
```

## describe

### 7.5 Describe a table

```
Use Fledgling describe on table raw_conversations.

Expected: Returns column definitions including uuid, sessionId, type,
message (a complex STRUCT), timestamp (TIMESTAMP type), and _source_file.
```

### 7.6 Describe a query

```
Use Fledgling describe with query: SELECT * FROM sessions() LIMIT 0

Expected: Returns the schema of the sessions() macro output including
session_id, project_dir, slug, git_branch, started_at, ended_at,
duration, and message count columns.
```

## list_tables

### 7.7 List all tables

```
Use Fledgling list_tables.

Expected: Returns 2 tables: raw_conversations and _help_sections. Each
entry should include database, schema, name, type, row_count_estimate,
and column_count.
```
