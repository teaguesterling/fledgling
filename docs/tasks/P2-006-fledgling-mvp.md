# P2-006: Security Profiles — Tool Allowlisting and Access Control

**Status:** Implemented
**Depends on:** P2-005 (init script, sandbox)
**Estimated scope:** New SQL files + init script update + tests

> **Note:** This task supersedes the original P2-006 spec ("Fledgling MVP —
> Code Navigation MCP Server"), which described a greenfield Python server
> architecture. The codebase evolved to use a SQL-first approach (DuckDB macros
> backed by extensions), and all the functional capabilities P2-006
> described — file access, code navigation, search, symbol extraction, imports,
> documentation, git access — are already implemented across the P2-001 through
> P2-005 tasks. What remains from P2-006's vision is the security profile
> system and the tool allowlisting model.

## Goal

Implement a profile system that controls which MCP tools are exposed and what
resource limits apply. Profiles are the access control layer: a **core**
profile gives agents structured code navigation tools, while an **analyst**
profile adds raw SQL query access. This is the foundation for Severance
Protocol integration (Innie = core, Outie = analyst or custom).

## Design

### How profiles work today (implicit)

`init-fledgling.sql` loads everything unconditionally. Tool exposure is
controlled by which `.read` lines are present and by `mcp_server_start()`
options like `enable_query_tool`. This is all-or-nothing — there's no way
to run a restricted tool set without editing the init script.

### What profiles add

A profile is a named configuration that controls:
1. **Which tool files are loaded** (which `.read sql/tools/*.sql` lines run)
2. **DuckDB resource limits** (`memory_limit`, `query_timeout`)
3. **MCP server options** (`enable_query_tool`, `enable_execute_tool`, etc.)
4. **Additional restrictions** (views that limit visible data, if needed)

### Approach: parameterized init with profile SQL files

The init script accepts a `profile` variable (default: `core`) and loads
a profile-specific SQL file that sets limits and declares the tool allowlist.
Tool files are then loaded conditionally based on the allowlist.

```
sql/
  profiles/
    core.sql          # Default: code nav tools, tight limits
    analyst.sql       # Core + raw SQL query, wider limits
```

Profile files set DuckDB variables that the init script reads:

```sql
-- sql/profiles/core.sql
-- Default profile: structured code navigation only.
-- No raw SQL, tight resource limits.

SET memory_limit = '2GB';
SET VARIABLE query_timeout_seconds = 30;

-- Tool categories to load (init script checks these)
SET VARIABLE load_files_tools = true;
SET VARIABLE load_code_tools = true;
SET VARIABLE load_docs_tools = true;
SET VARIABLE load_git_tools = true;

-- MCP server options
SET VARIABLE enable_query_tool = false;
SET VARIABLE enable_execute_tool = false;
```

```sql
-- sql/profiles/analyst.sql
-- Extended profile: all core tools + raw SQL query access.

SET memory_limit = '4GB';
SET VARIABLE query_timeout_seconds = 60;

-- All tool categories
SET VARIABLE load_files_tools = true;
SET VARIABLE load_code_tools = true;
SET VARIABLE load_docs_tools = true;
SET VARIABLE load_git_tools = true;

-- Raw query access
SET VARIABLE enable_query_tool = true;
SET VARIABLE enable_execute_tool = false;
```

### Init script changes

The init script reads the profile variable and conditionally loads tools:

```sql
-- Load profile (default: core)
-- Override: SET VARIABLE profile = 'analyst';
.read sql/profiles/${profile}.sql    -- if DuckDB supports variable interpolation
-- OR: load a dispatcher that reads getvariable('profile')
```

**Open question:** DuckDB's `.read` command does NOT support variable
interpolation in file paths. Options:
1. **Separate entry-point scripts** per profile (`init-fledgling-core.sql`,
   `init-fledgling-analyst.sql`) that share a common base via `.read`.
2. **Single script with conditional SQL** — DuckDB has no `IF` statement,
   but `CASE` in a `SELECT` can be used to conditionally call
   `mcp_publish_tool()`. However, `.read` is unconditional.
3. **Python test harness handles profiles** — For the MCP server (which runs
   via `duckdb -init`), use separate entry points. For tests, the fixture
   controls what's loaded.

Recommendation: **Option 1 (separate entry points)** is simplest and most
transparent. A `sql/profiles/base.sql` contains extensions + sandbox + macros.
Each profile script `.read`s the base, then loads its tool set.

## Files

| File | Action | Description |
|------|--------|-------------|
| `sql/profiles/core.sql` | Create | Core profile: resource limits + tool config |
| `sql/profiles/analyst.sql` | Create | Analyst profile: wider limits + query access |
| `init-fledgling.sql` | Update | Refactor into base + profile pattern |
| `init-fledgling-core.sql` | Create | Entry point for core profile |
| `init-fledgling-analyst.sql` | Create | Entry point for analyst profile |
| `tests/conftest.py` | Update | Profile-aware fixtures |
| `tests/test_profiles.py` | Create | Profile enforcement tests |

## Technical Details

### Profile enforcement

The key security property: a core profile agent **cannot** access raw SQL.
This means:
- `enable_query_tool = false` in `mcp_server_start()`
- `enable_execute_tool = false`
- Even if the agent knows the SQL, it has no tool to submit it through

The analyst profile adds query access but keeps `access_mode = 'read_only'`
(DuckDB built-in) and filesystem sandbox (from P2-005). The analyst can
query any table but cannot write to disk or modify the database.

### Backward compatibility

The existing `init-fledgling.sql` should continue to work as-is (defaulting
to the most permissive profile, or becoming an alias for the analyst entry
point). No existing workflows should break.

## Acceptance Criteria

These tests in `test_profiles.py` must pass:

- `TestCoreProfile` (3+ tests):
  - Core tools (ListFiles, ReadLines, FindDefinitions, etc.) are accessible
  - Raw query tool is NOT accessible (tool not listed in `tools/list`)
  - Resource limits are set correctly (`memory_limit`, timeout)
- `TestAnalystProfile` (3+ tests):
  - All core tools are accessible
  - Raw query tool IS accessible
  - Can execute SELECT queries via query tool
  - Cannot execute INSERT/UPDATE/DELETE (read-only mode)
- `TestProfileIsolation` (2+ tests):
  - Two separate connections with different profiles see different tool sets
  - Profile choice is set at startup, not changeable after init

Existing tests (all tiers) must continue to pass unchanged. The `mcp_server`
fixture in `conftest.py` should use the analyst profile (to maintain current
test coverage of query tool).

## What this task does NOT include

These are deferred to P2-007 (Profile Integration and Polish):
- Updating `config/claude-code.example.json` with profile variants
- Documenting the custom profile convention
- End-to-end smoke test of `duckdb -init init-fledgling-core.sql`
- Severance Protocol profile design
