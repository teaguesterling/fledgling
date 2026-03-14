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

SET VARIABLE _version = '0.1.0';
SET VARIABLE _base = 'https://raw.githubusercontent.com/teaguesterling/fledgling/main';

-- ── 2. Parse configuration ───────────────────────────────────────────

-- Default config (all feature modules, analyst profile)
SET VARIABLE _default_modules = ['source', 'code', 'docs', 'repo',
                                  'structural', 'conversations', 'help'];
SET VARIABLE _default_profile = 'analyst';

-- Read user config (set via -cmd before stdin)
SET VARIABLE _user_config = getvariable('fledgling_config');

SET VARIABLE _selected_modules = COALESCE(
    _user_config.modules,
    getvariable('_default_modules')
);
SET VARIABLE _profile = COALESCE(
    _user_config.profile,
    getvariable('_default_profile')
);

-- ── 3. Module registry ───────────────────────────────────────────────

CREATE TABLE _module_registry AS FROM (VALUES
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

-- Fetch tool publication SQL files
CREATE TABLE _tools AS
SELECT * FROM read_text(
    [format('{}/sql/tools/{}.sql', getvariable('_base'), t)
     FOR t IN getvariable('_tool_files')]
);

-- Fetch resources (SKILL.md, etc.)
CREATE TABLE _resources AS
SELECT * FROM read_text(
    [format('{}/{}', getvariable('_base'), r)
     FOR r IN getvariable('_resource_files')]
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
    || 'SET VARIABLE fledgling_version = ''' || getvariable('_version') || ''';' || E'\n'
    || 'SET VARIABLE fledgling_profile = ''' || profile || ''';' || E'\n'
    || 'SET VARIABLE fledgling_modules = ' || modules::VARCHAR || ';' || E'\n'
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
    || 'SELECT mcp_server_start(json(getvariable(''mcp_server_options'')));' || E'\n';

-- ── 7. Write output files ────────────────────────────────────────────

-- Write .fledgling-init.sql
COPY (
    SELECT _fledgling_header(
               getenv('PWD'), getvariable('_profile'),
               getvariable('_extensions'), getvariable('_all_modules'))
        || E'\n'
        || (SELECT string_agg(content, E'\n;\n' ORDER BY load_order DESC) FROM _ordered_macros)
        || E'\n;\n'
        || (SELECT string_agg(content, E'\n;\n') FROM _tools)
        || E'\n;\n'
        || _fledgling_footer(getenv('PWD'), getvariable('_profile'))
) TO '.fledgling-init.sql' (FORMAT csv, QUOTE '', HEADER false);

-- Write .fledgling-help.md (SKILL.md content for the help module)
COPY (
    SELECT content FROM _resources WHERE filename LIKE '%SKILL.md'
) TO '.fledgling-help.md' (FORMAT csv, QUOTE '', HEADER false);

-- Merge .mcp.json
COPY (
    SELECT json_pretty(json_merge_patch(
        COALESCE(
            (SELECT content FROM read_text(
                [f FOR f IN glob('.mcp.json') IF f IS NOT NULL]
            )),
            '{}'
        ),
        '{"mcpServers": {"fledgling": {
            "command": "duckdb",
            "args": ["-init", ".fledgling-init.sql"]
        }}}'
    ))
) TO '.mcp.json' (FORMAT csv, QUOTE '', HEADER false);

-- ── 8. Report ────────────────────────────────────────────────────────

.output
SELECT printf('Fledgling %s installed successfully!', getvariable('_version')) AS status;
SELECT printf('  Profile:    %s', getvariable('_profile')) AS info;
SELECT printf('  Modules:    %s', array_to_string(getvariable('_all_modules'), ', ')) AS info;
SELECT printf('  Extensions: %s', array_to_string(getvariable('_extensions'), ', ')) AS info;
SELECT '  Files written:' AS info;
SELECT '    .fledgling-init.sql' AS info;
SELECT '    .fledgling-help.md' AS info;
SELECT '    .mcp.json' AS info;
