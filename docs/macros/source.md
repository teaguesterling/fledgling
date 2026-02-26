# Source Retrieval

**Extension**: [`read_lines`](https://duckdb.org/community_extensions/extensions/read_lines)

Thin wrappers around `read_lines` that provide convenient interfaces for the common file-reading patterns agents use most. Replaces `cat`, `head`, `tail`, and `sed -n` bash commands.

!!! note
    When both `sitting_duck` and `read_lines` are loaded, `sitting_duck`'s `read_lines` macro shadows the extension. Drop it first: `DROP MACRO TABLE IF EXISTS read_lines;`
    See [sitting_duck#22](https://github.com/teaguesterling/sitting_duck/issues/22).

## `read_source`

Read lines from a file with optional line selection.

```sql
read_source(file_path, lines := NULL, ctx := 0)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | `string` | required | Path to file |
| `lines` | `string` | `NULL` (all) | Line selection: `'10-20'`, `'42'`, `'42 +/-5'` |
| `ctx` | `integer` | `0` | Context lines around selection |

**Returns**: `line_number`, `content`

```sql
-- Read entire file
SELECT * FROM read_source('src/main.py');

-- Read lines 10-20
SELECT * FROM read_source('src/main.py', '10-20');

-- Read line 42 with 5 lines of context
SELECT * FROM read_source('src/main.py', '42 +/-5');
```

## `read_source_batch`

Multi-file batch read via glob patterns. Like `read_source` but includes `file_path` column.

```sql
read_source_batch(file_pattern, lines := NULL, ctx := 0)
```

**Returns**: `file_path`, `line_number`, `content`

```sql
-- First 10 lines of all Python files in src/
SELECT * FROM read_source_batch('src/**/*.py', '1-10');
```

## `read_context`

Read lines centered around a specific line number. Optimized for error investigation.

```sql
read_context(file_path, center_line, ctx := 5)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | `string` | required | Path to file |
| `center_line` | `integer` | required | Center line number |
| `ctx` | `integer` | `5` | Lines before and after |

**Returns**: `line_number`, `content`, `is_center`

```sql
-- Show 5 lines of context around line 42
SELECT * FROM read_context('src/main.py', 42);

-- Show 10 lines of context
SELECT * FROM read_context('src/main.py', 42, 10);
```

## `file_line_count`

Get line counts for files matching a pattern.

```sql
file_line_count(file_pattern)
```

**Returns**: `file_path`, `line_count` (ordered by line_count DESC)

```sql
SELECT * FROM file_line_count('src/**/*.py');
```
