-- Fledgling: Core Profile
--
-- Structured tools only. No raw SQL query access.
-- Used for Severance Protocol integration and restricted environments.

SET memory_limit = '2GB';

SET VARIABLE mcp_server_options = '{"enable_query_tool": false, "enable_describe_tool": false, "enable_list_tables_tool": false, "enable_database_info_tool": false, "enable_export_tool": false, "enable_execute_tool": false, "default_result_format": "markdown"}';
