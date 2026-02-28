-- Fledgling: Default Init Script
--
-- Alias for the analyst profile (backward compatible).
-- See init-fledgling-core.sql for the restricted profile.
--
-- Usage:
--   duckdb -init /path/to/fledgling/init-fledgling.sql
--
-- The MCP client must set cwd to the fledgling directory so
-- .read paths resolve correctly (they are relative to CWD, not to
-- this init script). The target project root is passed separately
-- via the FLEDGLING_ROOT environment variable, or by
-- pre-setting the session_root DuckDB variable.

.read init-fledgling-analyst.sql
