-- Fledgling: Help System Macro
--
-- Provides agent-accessible skill documentation from a materialized
-- table. The _help_sections table must be created before this file
-- is loaded (see init-fledgling.sql).

-- help: Browse the Fledgling skill guide.
-- With no arguments, returns an outline (section IDs and titles).
-- With a section ID, returns matching sections with full content.
-- Supports path prefix matching so parent IDs return children.
--
-- Examples:
--   SELECT * FROM help();
--   SELECT * FROM help('workflows');
--   SELECT * FROM help('code-intelligence');
CREATE OR REPLACE MACRO help(target_id := NULL) AS TABLE
    SELECT
        section_id,
        title,
        level,
        CASE WHEN target_id IS NOT NULL THEN content END AS content
    FROM _help_sections
    WHERE (target_id IS NULL AND level <= 3)
       OR section_id = target_id
       OR section_path LIKE '%/' || target_id
       OR section_path LIKE '%/' || target_id || '/%'
    ORDER BY start_line;
