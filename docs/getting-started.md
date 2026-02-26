# Getting Started

## Requirements

- [DuckDB](https://duckdb.org/) >= 1.4.4
- Community extensions (installed automatically on first use):
    - `read_lines` — line-level file access
    - `sitting_duck` — AST-based code analysis
    - `duckdb_markdown` (loaded as `markdown`) — markdown parsing
    - `duck_tails` — git repository queries
    - `duckdb_mcp` — MCP server infrastructure

## Installation

Source Sextant is currently a collection of SQL macro files. To use it:

```bash
git clone https://github.com/teaguesterling/source-sextant.git
cd source-sextant
```

## Usage with DuckDB

Load extensions and macro files in a DuckDB session:

```sql
LOAD read_lines;
LOAD sitting_duck;
LOAD markdown;
LOAD duck_tails;

-- Fix sitting_duck/read_lines collision
DROP MACRO TABLE IF EXISTS read_lines;

-- Load macro definitions
.read sql/source.sql
.read sql/code.sql
.read sql/docs.sql
.read sql/repo.sql
```

Then use the macros:

```sql
-- Read lines 10-20 from a file
SELECT * FROM read_source('src/main.py', '10-20');

-- Find all class definitions
SELECT * FROM find_definitions('src/**/*.py', '%', 'class');

-- Get the table of contents for all markdown files
SELECT * FROM doc_outline('docs/**/*.md');

-- Recent git history
SELECT * FROM recent_changes(10);
```

## MCP Server Setup

!!! note
    MCP server integration is coming soon. The init script and tool publications are the next development phase.

Once available, add to your Claude Code settings:

```json
{
  "mcpServers": {
    "source_sextant": {
      "command": "duckdb",
      "args": ["-init", "/path/to/source-sextant/init-source-sextant.sql"]
    }
  }
}
```

## Running Tests

```bash
pip install duckdb pytest
pytest
```

All 63 tests should pass across the 4 macro tiers.
