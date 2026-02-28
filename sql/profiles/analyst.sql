-- Fledgling: Analyst Profile
--
-- All structured tools plus raw SQL query access.
-- Default profile for unrestricted use.
--
-- See core.sql for the profile contract documentation.

SET memory_limit = '4GB';

SET VARIABLE mcp_server_options = '{"enable_query_tool": true, "enable_describe_tool": true, "enable_list_tables_tool": true, "enable_database_info_tool": false, "enable_export_tool": false, "enable_execute_tool": false, "default_result_format": "markdown"}';
