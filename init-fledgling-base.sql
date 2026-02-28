-- Fledgling: Base Init (shared setup)
--
-- Loads extensions, configures sandbox, loads macros and tool publications.
-- Does NOT lock down the filesystem or start the MCP server — those are
-- handled by per-profile entry points (init-fledgling-core.sql, etc.).
--
-- Not intended to be used directly. Use a profile entry point instead.

-- Suppress output during initialization
.headers off
.mode csv
.output /dev/null

-- Load extensions (must happen before sandbox lockdown; see duckdb#17136)
LOAD duckdb_mcp;
LOAD read_lines;
LOAD sitting_duck;
LOAD markdown;
LOAD duck_tails;

-- Capture project root before lockdown.
-- Priority: pre-set variable > FLEDGLING_ROOT env var > CWD.
SET VARIABLE session_root = COALESCE(
    getvariable('session_root'),
    NULLIF(getenv('FLEDGLING_ROOT'), ''),
    getenv('PWD')
);

-- Additional allowed directories (set before this point if needed).
-- Example: SET VARIABLE extra_dirs = ['/data/shared', '/opt/models'];

-- Path resolution macro (resolve relative paths against session_root)
.read sql/sandbox.sql

-- Load macro definitions
.read sql/source.sql
.read sql/code.sql
.read sql/docs.sql
.read sql/repo.sql

-- Publish MCP tools (comment out a line to disable that category)
.read sql/tools/files.sql
.read sql/tools/code.sql
.read sql/tools/docs.sql
.read sql/tools/git.sql
