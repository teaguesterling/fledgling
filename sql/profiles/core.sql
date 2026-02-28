-- Fledgling: Core Profile
--
-- Structured tools only. No raw SQL query access.
-- Used for Severance Protocol integration and restricted environments.
--
-- Profile contract: every profile must set exactly two things:
--   1. memory_limit   — DuckDB memory cap for this profile
--   2. mcp_server_options — JSON string passed to mcp_server_start()
--
-- Available mcp_server_options keys (all boolean, default false):
--   enable_query_tool, enable_describe_tool, enable_list_tables_tool,
--   enable_database_info_tool, enable_export_tool, enable_execute_tool
-- Plus: default_result_format (string, typically "markdown")

SET memory_limit = '2GB';

SET VARIABLE mcp_server_options = '{"enable_query_tool": false, "enable_describe_tool": false, "enable_list_tables_tool": false, "enable_database_info_tool": false, "enable_export_tool": false, "enable_execute_tool": false, "default_result_format": "markdown"}';
