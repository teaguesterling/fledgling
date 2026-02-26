# Code Intelligence

**Extension**: [`sitting_duck`](https://github.com/teaguesterling/sitting_duck)

Semantic code analysis powered by sitting_duck's AST parsing. Replaces grep-based code search with structure-aware queries across 27 programming languages.

## `find_definitions`

Find function, class, or variable definitions by name pattern.

```sql
find_definitions(file_pattern, name_pattern := '%')
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_pattern` | `string` | required | File path or glob pattern |
| `name_pattern` | `string` | `'%'` (all) | SQL LIKE pattern for name |

**Returns**: `file_path`, `name`, `kind`, `start_line`, `end_line`, `signature`

```sql
-- All definitions in a file
SELECT * FROM find_definitions('src/main.py');

-- Functions matching a pattern
SELECT * FROM find_definitions('src/**/*.py', 'parse%');
```

## `find_calls`

Find function/method call sites.

```sql
find_calls(file_pattern, name_pattern := '%')
```

**Returns**: `file_path`, `name`, `start_line`, `call_expression`

```sql
-- Find all calls to 'connect' functions
SELECT * FROM find_calls('src/**/*.py', 'connect%');
```

## `find_imports`

Find import/include statements.

```sql
find_imports(file_pattern)
```

**Returns**: `file_path`, `name`, `import_statement`, `start_line`

!!! note
    Due to [sitting_duck#23](https://github.com/teaguesterling/sitting_duck/issues/23), Python import `name` fields may be empty. Use `import_statement` for reliable matching.

```sql
SELECT * FROM find_imports('src/**/*.py');
```

## `code_structure`

Get a structural overview of files — top-level definitions only.

```sql
code_structure(file_pattern)
```

**Returns**: `file_path`, `name`, `kind`, `start_line`, `end_line`, `line_count`

```sql
-- Overview of a file's structure
SELECT * FROM code_structure('src/main.py');

-- Overview of an entire directory
SELECT * FROM code_structure('src/**/*.py');
```
