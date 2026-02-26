# Documentation Intelligence

**Extension**: [`duckdb_markdown`](https://github.com/teaguesterling/duckdb_markdown)

Structured access to markdown documentation — the documentation counterpart to sitting_duck's source code analysis. Provides selective section retrieval, code block extraction, and document structure overview.

## `doc_outline`

Get the structural outline (table of contents) of markdown files. Lets the agent decide what to read before committing tokens.

```sql
doc_outline(file_pattern, max_lvl := 3)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_pattern` | `string` | required | File path or glob pattern |
| `max_lvl` | `integer` | `3` | Maximum heading depth |

**Returns**: `file_path`, `section_id`, `section_path`, `level`, `title`, `start_line`, `end_line`

```sql
-- Table of contents for a file
SELECT * FROM doc_outline('README.md');

-- Only top-level sections across all docs
SELECT * FROM doc_outline('docs/**/*.md', 2);
```

## `read_doc_section`

Read a specific section from a markdown file by section ID.

```sql
read_doc_section(file_path, section_id)
```

**Returns**: `section_id`, `title`, `level`, `content`, `start_line`, `end_line`

Returns the matching section and its children (subsections).

```sql
-- Read just the installation section
SELECT * FROM read_doc_section('README.md', 'installation');

-- Read a nested section
SELECT * FROM read_doc_section('docs/guide.md', 'getting-started');
```

## `find_code_examples`

Extract code blocks from documentation, optionally filtered by language.

```sql
find_code_examples(file_pattern, lang := NULL)
```

**Returns**: `file_path`, `section`, `section_title`, `language`, `code`, `line_number`

```sql
-- All code blocks from docs
SELECT * FROM find_code_examples('docs/**/*.md');

-- Only SQL examples
SELECT * FROM find_code_examples('README.md', 'sql');
```

## `doc_stats`

Get statistics about markdown documentation files.

```sql
doc_stats(file_pattern)
```

**Returns**: `file_path`, `word_count`, `heading_count`, `code_block_count`, `link_count`, `reading_time_min`

Results ordered by `word_count` descending.

```sql
SELECT * FROM doc_stats('docs/**/*.md');
```
