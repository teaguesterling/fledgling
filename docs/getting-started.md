# Getting Started

## Requirements

- [DuckDB](https://duckdb.org/) **1.5.2** (pinned — `duckdb==1.5.2`). The community
  extensions below are built per DuckDB version; 1.5.3 resolves them from a different
  versioned path where they aren't installed, which breaks FTS / `build_cache`. Stay on 1.5.2.
- Community extensions (installed automatically on first use):
    - `read_lines` — line-level file access
    - `sitting_duck` — AST-based code analysis
    - `duckdb_markdown` (loaded as `markdown`) — markdown parsing
    - `duck_tails` — git repository queries
    - `duckdb_mcp` — MCP server infrastructure

## Installation

Fledgling is currently a collection of SQL macro files. To use it:

```bash
git clone https://github.com/teaguesterling/fledgling.git
cd fledgling
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

-- Find all definitions
SELECT * FROM find_definitions('src/**/*.py');

-- Get the table of contents for all markdown files
SELECT * FROM doc_outline('docs/**/*.md');

-- Recent git history
SELECT * FROM recent_changes(10);
```

## MCP Server Setup

Add to your Claude Code settings:

```json
{
  "mcpServers": {
    "fledgling": {
      "command": "/path/to/fledgling/bin/fledgling",
      "args": ["serve", "--profile", "analyst"],
      "env": {
        "FLEDGLING_ROOT": "/path/to/your/project"
      }
    }
  }
}
```

Or invoke DuckDB directly (CWD must be the fledgling directory):

```bash
duckdb -init init/init-fledgling.sql
```

## Running Tests

```bash
pip install duckdb pytest
pytest
```
