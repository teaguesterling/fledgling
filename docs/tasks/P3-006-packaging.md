# P3-006: Packaging and Distribution

**Status:** Not started
**Depends on:** P2-007 (profile integration)
**Estimated scope:** New files (CLI wrapper, config parser, packaging metadata)

## Motivation

Fledgling currently runs via `duckdb -init init-fledgling.sql` with the
working directory as the implicit project root. This works for development
and Claude Code integration, but has friction for distribution:

- Users must know the correct `duckdb` invocation and init script path
- Profile selection requires using a different init script
- There's no way to pass configuration (exclude patterns, extra dirs) without
  editing SQL files
- No `--help`, no discoverability

A thin CLI wrapper and config file support would make Fledgling installable
and runnable without understanding the DuckDB internals.

## Design

### CLI (`fledgling` command)

A small Python or shell script that:
1. Resolves the project root (CWD or `--root` flag)
2. Reads config file if present (`fledgling.yaml` or `.fledgling.yaml`)
3. Selects profile (`--profile core|analyst`, default from config or `core`)
4. Builds the correct `duckdb -init` invocation
5. Passes through to DuckDB

```
fledgling serve [--root PATH] [--profile PROFILE] [--transport stdio|sse]
fledgling info [--root PATH]      # Show what would be indexed (file counts, etc.)
```

This is intentionally thin — Fledgling is NOT a Python application. The CLI
is a launcher, not a runtime. All logic stays in SQL.

### Config file

```yaml
# fledgling.yaml (or .fledgling.yaml in project root)
profile: core                     # Default profile
exclude_patterns:                 # Patterns to exclude (beyond .gitignore)
  - "*.pyc"
  - "__pycache__"
  - "node_modules"
extra_dirs: []                    # Additional allowed directories
transport: stdio                  # stdio or sse
```

Config values are injected as DuckDB variables before the init script runs.

### Packaging

- `pyproject.toml` with `[project.scripts]` entry point for `fledgling`
- Depends on: `duckdb` (plus extensions, which DuckDB auto-installs)
- Optionally: `pyyaml` for config parsing, `click` for CLI

### SSE transport

`mcp_server_start('sse', ...)` is already supported by `duckdb_mcp`. The
CLI just needs to pass the transport choice through. Port configuration
via `--port` flag or config file.

## Tools

No new MCP tools. This task is about the distribution layer around the
existing tools.

## Files

| File | Action | Description |
|------|--------|-------------|
| `fledgling/__init__.py` | Create | Package marker |
| `fledgling/cli.py` | Create | CLI entry point |
| `fledgling/config.py` | Create | Config file parser |
| `pyproject.toml` | Create | Package metadata + entry points |
| `init-fledgling.sql` | Update | Accept injected variables from CLI |

## Acceptance Criteria

- `fledgling serve` starts the MCP server (stdio transport)
- `fledgling serve --profile analyst` starts with analyst profile
- `fledgling info` prints file count and detected languages for CWD
- Config file is read if present, CLI flags override config values
- `pip install -e .` makes the `fledgling` command available
- Existing `duckdb -init` workflow continues to work unchanged
