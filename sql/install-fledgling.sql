-- install-fledgling.sql: Pure-DuckDB installer for Fledgling
--
-- Usage:
--   curl -sL https://raw.githubusercontent.com/.../install-fledgling.sql | duckdb
--
-- Customized:
--   curl -sL .../install-fledgling.sql | duckdb -cmd "SET VARIABLE fledgling_config = {
--       modules: ['source', 'code', 'docs', 'repo'],
--       profile: 'analyst'
--   }"
--
-- The -cmd flag runs before stdin, so fledgling_config is available when
-- this SQL executes.

-- ── 1. Setup ─────────────────────────────────────────────────────────

INSTALL httpfs;
LOAD httpfs;

SET VARIABLE _version = '0.7.1';
SET VARIABLE _base = 'https://raw.githubusercontent.com/teaguesterling/fledgling/main';

-- ── 2. Parse configuration ───────────────────────────────────────────

-- Default config (all feature modules, analyst profile)
SET VARIABLE _default_modules = ['source', 'code', 'docs', 'repo',
                                  'structural', 'workflows',
                                  'conversations', 'help'];
SET VARIABLE _default_profile = 'analyst';

-- Read user config (set via -cmd before stdin)
-- DuckDB structs are typed: {modules: [...]} has no .profile field, so
-- accessing it is a binder error (not NULL). Cast to JSON for safe access.
SET VARIABLE _config_json = CASE
    WHEN getvariable('fledgling_config') IS NOT NULL
    THEN getvariable('fledgling_config')::JSON
    ELSE NULL END;

SET VARIABLE _selected_modules = COALESCE(
    CASE WHEN getvariable('_config_json') IS NOT NULL
         AND json_type(getvariable('_config_json'), 'modules') = 'ARRAY'
         THEN json_extract_string(getvariable('_config_json'), 'modules')::VARCHAR[]
         ELSE NULL END,
    getvariable('_default_modules')
);
SET VARIABLE _profile = COALESCE(
    json_extract_string(getvariable('_config_json'), '$.profile'),
    getvariable('_default_profile')
);
SET VARIABLE _install_cli = COALESCE(
    json_extract_string(getvariable('_config_json'), '$.cli') = 'true',
    false
);

-- ── 3. Module registry ───────────────────────────────────────────────

CREATE TABLE _module_registry AS FROM (VALUES
    ('sandbox',       'core',    [],                              [],                                                NULL,             NULL),
    ('dr_fledgling',  'core',    [],                              ['sandbox'],                                       NULL,             NULL),
    ('source',        'feature', ['read_lines'],                  ['sandbox'],                                       'files',          NULL),
    ('code',          'feature', ['sitting_duck'],                ['sandbox'],                                       'code',           NULL),
    ('docs',          'feature', ['markdown'],                    ['sandbox'],                                       'docs',           NULL),
    ('repo',          'feature', ['duck_tails'],                  ['sandbox'],                                       'git',            NULL),
    ('structural',    'feature', ['sitting_duck','duck_tails'],   ['sandbox','code','repo'],                         NULL,             NULL),
    ('workflows',     'feature', [],                              ['sandbox','source','code','docs','repo','structural'], 'workflows',      NULL),
    ('conversations', 'feature', [],                              [],                                                'conversations',  NULL),
    ('help',          'feature', ['markdown'],                    [],                                                'help',           'SKILL.md')
) AS t(module, kind, extension_deps, module_deps, tool_file, resource);

-- ── 4. Dependency resolution ─────────────────────────────────────────

CREATE TABLE _resolved AS
WITH RECURSIVE deps AS (
    -- Core modules always included
    SELECT module, 0 AS depth
    FROM _module_registry WHERE kind = 'core'
    UNION ALL
    -- Selected feature modules
    SELECT module, 0 AS depth
    FROM _module_registry
    WHERE kind = 'feature'
      AND list_contains(getvariable('_selected_modules'), module)
    UNION ALL
    -- Transitive dependencies
    SELECT dep.module, d.depth + 1
    FROM deps d
    JOIN _module_registry dep
      ON list_contains(
        (SELECT module_deps FROM _module_registry WHERE module = d.module),
        dep.module
      )
    WHERE d.depth < 10
)
SELECT module, max(depth) AS load_order
FROM deps GROUP BY module;

-- Compute ordered module list and inferred extensions
-- Higher load_order = deeper dependency = load first (ORDER BY DESC)
SET VARIABLE _all_modules = (
    SELECT list(module ORDER BY load_order DESC, module) FROM _resolved
);

SET VARIABLE _extensions = (
    SELECT list(DISTINCT ext ORDER BY ext)
    FROM (SELECT unnest(extension_deps) AS ext
          FROM _module_registry
          WHERE list_contains(getvariable('_all_modules'), module))
);

-- Tool file mapping
SET VARIABLE _tool_map = MAP {
    'source': 'files', 'code': 'code', 'docs': 'docs',
    'repo': 'git', 'conversations': 'conversations', 'help': 'help'
};

SET VARIABLE _tool_files = [element_at(getvariable('_tool_map'), m)[1]
                            FOR m IN getvariable('_all_modules')
                            IF element_at(getvariable('_tool_map'), m)[1] IS NOT NULL];

-- Resources to download
SET VARIABLE _resource_files = (
    SELECT list(resource)
    FROM _module_registry
    WHERE list_contains(getvariable('_all_modules'), module)
      AND resource IS NOT NULL
);

-- ── 5. Fetch from GitHub ─────────────────────────────────────────────

-- Fetch module SQL files
CREATE TABLE _macros AS
SELECT * FROM read_text(
    [format('{}/sql/{}.sql', getvariable('_base'), m)
     FOR m IN getvariable('_all_modules')]
);

-- Fetch tool publication SQL files (skip if none selected)
-- Build URL list as a string for query() dispatch — avoids read_text(NULL)
SET VARIABLE _tool_urls = [format('{}/sql/tools/{}.sql', getvariable('_base'), t)
                           FOR t IN getvariable('_tool_files')];
CREATE TABLE _tools AS
SELECT * FROM query(
    CASE WHEN len(getvariable('_tool_urls')) > 0
    THEN 'SELECT * FROM read_text(getvariable(''_tool_urls''))'
    ELSE 'SELECT * FROM read_text([]::VARCHAR[]) WHERE false'
    END
);

-- Fetch resources (SKILL.md, etc.) — skip if none needed
SET VARIABLE _resource_urls = COALESCE(
    [format('{}/{}', getvariable('_base'), r)
     FOR r IN getvariable('_resource_files')],
    []::VARCHAR[]
);
CREATE TABLE _resources AS
SELECT * FROM query(
    CASE WHEN len(getvariable('_resource_urls')) > 0
    THEN 'SELECT * FROM read_text(getvariable(''_resource_urls''))'
    ELSE 'SELECT * FROM read_text([]::VARCHAR[]) WHERE false'
    END
);

-- ── 6. Assembly macros ───────────────────────────────────────────────

-- Order macros: higher load_order (deeper deps) load first
CREATE TABLE _ordered_macros AS
SELECT m.content, r.load_order
FROM _macros m
JOIN _resolved r ON m.filename LIKE '%/' || r.module || '.sql'
ORDER BY r.load_order DESC, r.module;

-- Header: extensions, variables, literal-backed macros
CREATE OR REPLACE MACRO _fledgling_header(root, profile, extensions, modules) AS
    '-- .fledgling-init.sql — generated by install-fledgling.sql v' || getvariable('_version') || E'\n'
    || '-- Profile: ' || profile || E'\n'
    || '-- Modules: ' || array_to_string(modules, ', ') || E'\n\n'
    || E'.headers off\n.mode csv\n.output /dev/null\n\n'
    || E'LOAD duckdb_mcp;\n'
    || array_to_string([format('LOAD {};', e) FOR e IN extensions], E'\n')
    || E'\n\n'
    || 'SET VARIABLE session_root = COALESCE(getvariable(''session_root''), NULLIF(getenv(''FLEDGLING_ROOT''), ''''), getenv(''PWD''));' || E'\n'
    || 'SET VARIABLE conversations_root = COALESCE(getvariable(''conversations_root''), NULLIF(getenv(''CONVERSATIONS_ROOT''), ''''), getenv(''HOME'') || ''/.claude/projects'');' || E'\n'
    || E'\n-- Literal-backed macros for MCP tool templates (getvariable returns NULL in that context)\n'
    || 'CREATE OR REPLACE MACRO _resolve(p) AS CASE WHEN p IS NULL THEN NULL WHEN p[1] = ''/'' THEN p ELSE ''' || root || '/'' || p END;' || E'\n'
    || 'CREATE OR REPLACE MACRO _session_root() AS ''' || root || ''';' || E'\n'
    || 'SET VARIABLE fledgling_version = ''' || getvariable('_version') || ''';' || E'\n'
    || 'SET VARIABLE fledgling_profile = ''' || profile || ''';' || E'\n'
    || 'SET VARIABLE fledgling_modules = [' || array_to_string([format('''{}''', m) FOR m IN modules], ', ') || '];' || E'\n'
    || 'SET VARIABLE _help_path = ''.fledgling-help.md'';' || E'\n';

-- Footer: profile settings, lockdown, server start
CREATE OR REPLACE MACRO _fledgling_footer(root, profile) AS
    CASE profile
        WHEN 'analyst' THEN 'SET memory_limit = ''4GB'';' || E'\n'
            || 'SET VARIABLE mcp_server_options = ''{"built_in_tools": {"query": true, "describe": true, "list_tables": true}}'';' || E'\n'
        ELSE 'SET memory_limit = ''2GB'';' || E'\n'
            || 'SET VARIABLE mcp_server_options = ''{"built_in_tools": {"query": false, "describe": false, "list_tables": false}}'';' || E'\n'
    END
    || E'\n'
    || E'.output\n'
    || 'SELECT mcp_server_start(COALESCE(getvariable(''transport''), ''stdio''), getvariable(''mcp_server_options'')) WHERE COALESCE(getvariable(''transport''), ''stdio'') <> ''none'';' || E'\n';

-- ── 7. Write output files ────────────────────────────────────────────

-- Show what will be written before doing it
.output
.mode list
.separator ""
.headers off
SELECT unnest([line FOR line IN [
    '',
    'Installing Fledgling ' || getvariable('_version') || ' in ' || getenv('PWD'),
    '',
    '  Will write:',
    '    .fledgling-init.sql  — DuckDB init script (all macros + tools)',
    '    .fledgling-help.md   — skill guide for the agent',
    CASE WHEN getvariable('_has_mcp_json')
        THEN '    .mcp.json            — merge fledgling server into existing config'
        ELSE '    .mcp.json            — create MCP server config' END,
    CASE WHEN getvariable('_install_cli')
        THEN '    .fledgling-cli       — CLI wrapper (move to ~/.local/bin/fledgling)'
        ELSE NULL END,
    ''
] IF line IS NOT NULL]) AS info;
.output /dev/null

-- Write .fledgling-init.sql
COPY (
    SELECT _fledgling_header(
               getenv('PWD'), getvariable('_profile'),
               getvariable('_extensions'), getvariable('_all_modules'))
        || E'\n'
        || (SELECT string_agg(content, E'\n;\n' ORDER BY load_order DESC) FROM _ordered_macros)
        || E'\n;\n'
        || COALESCE((SELECT string_agg(content, E'\n;\n') FROM _tools), '')
        || E'\n;\n'
        || _fledgling_footer(getenv('PWD'), getvariable('_profile'))
) TO '.fledgling-init.sql' (FORMAT csv, QUOTE '', HEADER false);

-- Write .fledgling-help.md (SKILL.md content for the help module)
-- Only write if we fetched the resource
COPY (
    SELECT content FROM _resources WHERE filename LIKE '%SKILL.md'
    UNION ALL SELECT '' WHERE NOT EXISTS (SELECT 1 FROM _resources WHERE filename LIKE '%SKILL.md')
) TO '.fledgling-help.md' (FORMAT csv, QUOTE '', HEADER false);

-- Merge .mcp.json
-- glob() is a table function — use a subquery to get existing file list
SET VARIABLE _has_mcp_json = (SELECT count(*) > 0 FROM glob('.mcp.json'));
COPY (
    SELECT json_pretty(json_merge_patch(
        CASE WHEN getvariable('_has_mcp_json')
             THEN (SELECT content FROM read_text('.mcp.json'))
             ELSE '{}' END,
        '{"mcpServers": {"fledgling": {
            "command": "duckdb",
            "args": ["-init", ".fledgling-init.sql"]
        }}}'
    ))
) TO '.mcp.json' (FORMAT csv, QUOTE '', HEADER false);

-- ── 8. Optional CLI install ───────────────────────────────────────────

-- Fetch and install fledgling-cli to ~/.local/bin/fledgling if requested.
-- COPY TO requires a literal path, so we use query() to conditionally
-- write the script. The CLI is a bash wrapper that translates shell
-- commands to DuckDB SQL using .fledgling-init.sql.
SET VARIABLE _cli_path = getenv('HOME') || '/.local/bin/fledgling';
SET VARIABLE _cli_installed = false;

CREATE TABLE _cli_script AS SELECT * FROM read_text([]::VARCHAR[]) WHERE false;
INSERT INTO _cli_script
SELECT * FROM query(
    CASE WHEN getvariable('_install_cli')
    THEN 'SELECT * FROM read_text(''' || getvariable('_base') || '/bin/fledgling-cli'')'
    ELSE 'SELECT * FROM read_text([]::VARCHAR[]) WHERE false'
    END
);

-- Write CLI to project directory first, then report how to install globally.
-- We can't use COPY TO with a variable path, and ~/.local/bin may not exist.
COPY (
    SELECT content FROM _cli_script WHERE content IS NOT NULL
    UNION ALL SELECT NULL WHERE NOT EXISTS (SELECT 1 FROM _cli_script WHERE content IS NOT NULL)
) TO '.fledgling-cli' (FORMAT csv, QUOTE '', HEADER false);
SET VARIABLE _cli_installed = (SELECT count(*) > 0 FROM _cli_script WHERE content IS NOT NULL);

-- ── 9. Report ────────────────────────────────────────────────────────

.output
.mode list
.separator ""
.headers off
SELECT unnest([line for line in [
    '',
    printf('Fledgling %s installed successfully!', getvariable('_version')),
    '',
    printf('  Profile:    %s', getvariable('_profile')),
    printf('  Modules:    %s', array_to_string(getvariable('_all_modules'), ', ')),
    printf('  Extensions: %s', array_to_string(getvariable('_extensions'), ', ')),
    '',
    '  Files written:',
    '    .fledgling-init.sql  — DuckDB init script',
    '    .fledgling-help.md   — skill guide',
    '    .mcp.json            — MCP server config',
    CASE WHEN getvariable('_cli_installed') THEN '    .fledgling-cli       — CLI wrapper' ELSE NULL END,
    '',
    CASE WHEN getvariable('_cli_installed') THEN '  To install the CLI globally:' ELSE NULL END,
    CASE WHEN getvariable('_cli_installed') THEN '    chmod +x .fledgling-cli && mv .fledgling-cli ~/.local/bin/fledgling' ELSE NULL END,
    CASE WHEN getvariable('_cli_installed') THEN '' ELSE NULL END,
    CASE WHEN getvariable('_cli_installed') THEN '  CLI examples:' ELSE NULL END,
    CASE WHEN getvariable('_cli_installed') THEN '    fledgling help                              # list commands' ELSE NULL END,
    CASE WHEN getvariable('_cli_installed') THEN '    fledgling find-definitions ''src/**/*.py''    # search code' ELSE NULL END,
    CASE WHEN getvariable('_cli_installed') THEN '    fledgling recent-changes 10 -c hash,message # git history' ELSE NULL END,
    CASE WHEN getvariable('_cli_installed') THEN '    fledgling query "SELECT * FROM sessions()"  # raw SQL' ELSE NULL END,
    ''
] IF line IS NOT NULL]) AS info;
