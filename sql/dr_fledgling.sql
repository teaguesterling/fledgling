-- Fledgling: Diagnostics Module (dr_fledgling)
--
-- Self-contained: materializes extension info at load time (before sandbox
-- lockdown blocks access to the extensions directory). The dr_fledgling()
-- macro reads from the materialized table at call time.

-- Bootstrap: snapshot loaded fledgling extensions before lockdown.
-- duckdb_extensions() requires filesystem access to the extensions dir,
-- which is blocked after enable_external_access = false.
CREATE TABLE IF NOT EXISTS _fledgling_extensions AS
SELECT array_to_string(list(extension_name ORDER BY extension_name), ', ') AS extensions
FROM duckdb_extensions() WHERE installed AND loaded
AND extension_name IN ('duckdb_mcp','read_lines','sitting_duck','markdown','duck_tails');

-- dr_fledgling: Runtime diagnostic summary.
-- Returns key-value pairs: version, profile, root, modules, extensions.
--
-- Examples:
--   SELECT * FROM dr_fledgling();
CREATE OR REPLACE MACRO dr_fledgling() AS TABLE
    SELECT * FROM (VALUES
        ('version',    getvariable('fledgling_version')),
        ('profile',    getvariable('fledgling_profile')),
        ('root',       getvariable('session_root')),
        ('modules',    array_to_string(getvariable('fledgling_modules'), ', ')),
        ('extensions', (SELECT extensions FROM _fledgling_extensions))
    ) AS t(key, value);
