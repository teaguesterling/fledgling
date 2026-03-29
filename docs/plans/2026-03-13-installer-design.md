# Fledgling Installer Design

**Date:** 2026-03-13
**Status:** Draft (brainstorming)

## Overview

A pure-DuckDB installer that fetches fledgling modules from GitHub, assembles
them into a self-contained init file, and configures the MCP server — no bash,
no Python, no PATH management.

## Install Command

Zero-config (all modules, analyst profile):

```bash
curl -sL https://raw.githubusercontent.com/.../install-fledgling.sql | duckdb
```

Customized:

```bash
curl -sL https://raw.githubusercontent.com/.../install-fledgling.sql \
  | duckdb -cmd "SET VARIABLE fledgling_config = {
      modules: ['source', 'code', 'docs', 'repo'],
      profile: 'analyst'
  }"
```

DuckDB's `-cmd` flag runs "before reading stdin", so the config variable is
available when the installer SQL executes.

## Output Files

The installer writes three files to the project directory:

| File | Purpose |
|------|---------|
| `.fledgling-init.sql` | Self-contained init file (all SQL assembled) |
| `.fledgling-help.md` | SKILL.md content (read by help module before lockdown) |
| `.mcp.json` | Merged with fledgling MCP server entry |

All fledgling artifacts are dot-prefixed (gitignore with `.fledgling*`).

## How It Works

The installer is a single SQL file. DuckDB reads it from stdin. The SQL:

1. `INSTALL httpfs; LOAD httpfs;`
2. Reads `fledgling_config` variable (or fills defaults)
3. Resolves module dependencies via the module registry
4. Fetches module SQL from GitHub via `read_text()` with list comprehensions
5. Fetches resources (SKILL.md) for modules that need them
6. Assembles header + ordered modules + tool publications + footer
7. Writes `.fledgling-init.sql` via `COPY TO`
8. Downloads `.fledgling-help.md` via `COPY TO`
9. Merges `.mcp.json` via `json_merge_patch()` + `json_pretty()` + `COPY TO`

The generated `.fledgling-init.sql` is fully self-contained — no network access
at runtime, no external dependencies. Just `duckdb -init .fledgling-init.sql`.

## Generated File Structure

```
┌─────────────────────────────────┐
│ 1. HEADER                       │  Generated: extensions, variables,
│    Extensions, variables,       │  _resolve(), _session_root()
│    literal-backed macros        │
├─────────────────────────────────┤
│ 2. CORE MODULES                 │  Fetched: sandbox, dr_fledgling
│    Always-included modules      │
├─────────────────────────────────┤
│ 3. FEATURE MACROS               │  Fetched: sql/{module}.sql per selection
│    Selected module macros       │  (self-contained: includes own bootstrap)
├─────────────────────────────────┤
│ 4. TOOL PUBLICATIONS            │  Fetched: sql/tools/{tool_file}.sql
│    Selected tool publications   │
├─────────────────────────────────┤
│ 5. FOOTER                       │  Generated: profile settings, lockdown,
│    Profile, lockdown, start     │  mcp_server_start()
└─────────────────────────────────┘
```

## Module System

Everything is a module. Each module is a self-contained SQL file hosted on
GitHub, fetched at install time, and inlined into the generated init file.

### Module registry

The installer contains a module registry as a VALUES table:

```sql
CREATE TABLE _module_registry AS FROM (VALUES
  -- (module,         kind,      extension_deps,                 module_deps,               tool_file,        resource)
  ('sandbox',       'core',    [],                              [],                        NULL,             NULL),
  ('dr_fledgling',  'core',    [],                              ['sandbox'],               NULL,             NULL),
  ('source',        'feature', ['read_lines'],                  ['sandbox'],               'files',          NULL),
  ('code',          'feature', ['sitting_duck'],                ['sandbox'],               'code',           NULL),
  ('docs',          'feature', ['markdown'],                    ['sandbox'],               'docs',           NULL),
  ('repo',          'feature', ['duck_tails'],                  ['sandbox'],               'git',            NULL),
  ('structural',    'feature', ['sitting_duck','duck_tails'],   ['sandbox','code','repo'], NULL,             NULL),
  ('conversations', 'feature', [],                              [],                        'conversations',  NULL),
  ('help',          'feature', ['markdown'],                    [],                        'help',           'SKILL.md')
) AS t(module, kind, extension_deps, module_deps, tool_file, resource);
```

### Dependency resolution

A recursive CTE resolves transitive dependencies and computes load order:

- Core modules are always included
- Selected feature modules pull in their `module_deps` transitively
- Required extensions are the union of all selected modules' `extension_deps`
- Load order is topological (depth of dependency chain)

```
depth 0: sandbox, conversations, help        (no module deps)
depth 1: source, code, docs, repo, dr_fledgling  (depend on sandbox)
depth 2: structural                          (depends on code + repo)
```

### Self-contained modules

Each module file includes its own bootstrap. No external table creation needed:

- **conversations.sql**: Bootstraps `raw_conversations` table at top (conditional
  JSONL load via `query()` dispatch), then defines macros against it.
- **help.sql**: Bootstraps `_help_sections` table from `.fledgling-help.md`
  (downloaded by installer), then defines the `help()` macro.
- **All others**: Pure macro definitions, no bootstrap needed.

### Module → tool file mapping

Not all modules have tool publications. The mapping is stored as a MAP variable:

```sql
SET VARIABLE _tool_map = MAP {
    'source': 'files', 'code': 'code', 'docs': 'docs',
    'repo': 'git', 'conversations': 'conversations', 'help': 'help'
};
```

Modules without entries (sandbox, dr_fledgling, structural) have no tool files.

## Fetching

Module SQL is fetched from GitHub using `read_text()` with list comprehensions.
No `query()` dispatch needed — list comprehensions with `getvariable()` work
directly as `read_text()` arguments.

```sql
SET VARIABLE _base = 'https://raw.githubusercontent.com/.../main';

-- Fetch macro files
CREATE TABLE _macros AS
SELECT * FROM read_text(
    [format('{}/sql/{}.sql', getvariable('_base'), m)
     FOR m IN getvariable('_modules')]
);

-- Fetch tool publication files
CREATE TABLE _tools AS
SELECT * FROM read_text(
    [format('{}/sql/tools/{}.sql', getvariable('_base'), t)
     FOR t IN getvariable('_tool_files')]
);

-- Fetch resources (SKILL.md, etc.)
CREATE TABLE _resources AS
SELECT * FROM read_text(
    [format('{}/{}', getvariable('_base'), r)
     FOR r IN getvariable('_resource_urls')]
);
```

### Extension inference

Extensions are inferred from selected modules — no manual extension config
needed. If you select `code`, the installer knows to `LOAD sitting_duck`.

```sql
SET VARIABLE _extensions = (
    SELECT list(DISTINCT ext)
    FROM (SELECT unnest(extension_deps) AS ext
          FROM _module_registry
          WHERE list_contains(getvariable('_all_modules'), module))
);
```

## Assembly

Two macros generate the static header and footer:

**`fledgling_header(session_root, profile, extensions)`** returns SQL text:
- Output suppression (`.headers off`, `.output /dev/null`)
- `LOAD duckdb_mcp` + selected extension `LOAD` statements
- `SET VARIABLE session_root`, `conversations_root`
- `CREATE MACRO _resolve(p)` and `_session_root()` with baked-in paths

**`fledgling_footer(session_root, profile)`** returns SQL text:
- `SET memory_limit` (per profile)
- `SET VARIABLE mcp_server_options` (per profile)
- `SET allowed_directories` with baked-in session root
- `SET enable_external_access = false`
- `.output` (re-enable)
- `SELECT mcp_server_start(...)`

The assembled init file is:

```sql
COPY (
    SELECT fledgling_header(root, profile, extensions)
        || E'\n;\n'
        || (SELECT string_agg(content, E'\n;\n' ORDER BY load_order) FROM _ordered_macros)
        || E'\n;\n'
        || (SELECT string_agg(content, E'\n;\n') FROM _tools)
        || E'\n;\n'
        || fledgling_footer(root, profile)
) TO '.fledgling-init.sql' (FORMAT csv, QUOTE '', HEADER false);
```

## .mcp.json Merge

Read existing JSON (if present), merge fledgling entry, pretty-print, write:

```sql
COPY (
    SELECT json_pretty(json_merge_patch(
        COALESCE((SELECT content FROM read_text('.mcp.json')), '{}'),
        '{"mcpServers": {"fledgling": {
            "command": "duckdb",
            "args": ["-init", ".fledgling-init.sql"]
        }}}'
    ))
) TO '.mcp.json' (FORMAT csv, QUOTE '', HEADER false);
```

Preserves existing MCP server entries. Uses `json_pretty()` for human-readable
output. CSV-with-no-quote is used because DuckDB's JSON COPY format always
wraps values in column names.

## Configuration

A single struct variable carries all configuration:

```sql
SET VARIABLE fledgling_config = {
    modules: ['source', 'code', 'docs', 'repo'],  -- feature modules
    profile: 'analyst'                              -- analyst or core
};
```

Defaults (when no config provided):
- modules: all feature modules
- profile: analyst
- memory_limit: per profile (4GB analyst, 2GB core)
- extensions: inferred from selected modules

## dr_fledgling

A macro-only core module for diagnostics. Surfaced through the Help tool.

```sql
CREATE OR REPLACE MACRO dr_fledgling() AS TABLE
    SELECT * FROM (VALUES
        ('version',    getvariable('fledgling_version')),
        ('profile',    getvariable('fledgling_profile')),
        ('root',       getvariable('session_root')),
        ('modules',    array_to_string(getvariable('fledgling_modules'), ', ')),
        ('extensions', (
            SELECT array_to_string(list(extension_name ORDER BY extension_name), ', ')
            FROM duckdb_extensions() WHERE installed AND loaded
            AND extension_name IN ('duckdb_mcp','read_lines','sitting_duck','markdown','duck_tails')
        ))
    ) AS t(key, value);
```

The installer bakes `fledgling_version`, `fledgling_modules`, and
`fledgling_profile` as variables into the generated header. The macro
reads those plus live extension state.

Version update checks can't happen at runtime (`enable_external_access = false`
blocks HTTP). The installer handles this instead — when re-run, it compares
the installed version against what it's about to install and reports the delta.

## Updates

Re-run the installer to update. The installer compares the installed version
(read from `.fledgling-init.sql` header comment) against the version it's
about to install and reports "upgrading 0.1.0 → 0.2.0" or "already up to date."

## "Try It" Mode

Same installer, but executes the assembled SQL instead of writing to disk:

```bash
curl -sL .../install-fledgling.sql \
  | duckdb -cmd "SET VARIABLE fledgling_mode = 'try'"
```

The installer detects `fledgling_mode = 'try'` and runs the modules directly.
User gets a DuckDB REPL with fledgling macros loaded against their current
directory.

## Open Questions

- [ ] PWD resolution in DuckDB (may not matter for per-project install)
- [ ] Web UI for generating the install command (future)
- [ ] Hosting: raw GitHub for now, CDN later
- [ ] .mcp.json: handle case where file doesn't exist yet (glob check)
- [ ] conversations_root: should this be configurable in fledgling_config?
- [ ] help.sql bootstrap: read `.fledgling-help.md` via resolve() or hardcoded path?
- [ ] Try-it mode: execute assembled SQL in-process vs write + exec
