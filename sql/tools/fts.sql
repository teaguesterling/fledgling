-- Fledgling: FTS Tool Publications
--
-- MCP tool publications for full-text search. Wraps macros from
-- sql/fts.sql. Rebuild is not exposed as an MCP tool — it lives in
-- sql/fts_rebuild.sql and is triggered by the CLI or a Python helper.

SELECT mcp_publish_tool(
    'SearchContent',
    'BM25 full-text search across all indexed content (markdown sections, code definitions, code comments, code string literals). Requires a populated FTS index — call the rebuild script first. Optional filters: kind (doc_section/definition/comment/string), extractor (markdown/sitting_duck).',
    'SELECT file_path || '':'' || start_line || ''-'' || end_line AS location,
            extractor, kind, name, score, text
     FROM search_content(
         $query,
         filter_kind := NULLIF($kind, ''null''),
         filter_extractor := NULLIF($extractor, ''null''),
         limit_n := COALESCE(TRY_CAST(NULLIF($limit, ''null'') AS INT), 20)
     )',
    '{
        "query": {"type": "string", "description": "BM25 search query"},
        "kind": {"type": "string", "description": "Filter by kind: doc_section, definition, comment, or string"},
        "extractor": {"type": "string", "description": "Filter by extractor: markdown or sitting_duck"},
        "limit": {"type": "integer", "description": "Max rows (default 20)"}
    }',
    '["query"]',
    'markdown'
);

SELECT mcp_publish_tool(
    'SearchDocs',
    'BM25 search over markdown documentation sections. Requires a populated FTS index.',
    'SELECT file_path || '':'' || start_line || ''-'' || end_line AS location,
            name AS heading, score, text
     FROM search_docs(
         $query,
         limit_n := COALESCE(TRY_CAST(NULLIF($limit, ''null'') AS INT), 20)
     )',
    '{
        "query": {"type": "string", "description": "BM25 search query"},
        "limit": {"type": "integer", "description": "Max rows (default 20)"}
    }',
    '["query"]',
    'markdown'
);

SELECT mcp_publish_tool(
    'SearchCode',
    'BM25 search over code (definitions, comments, string literals including docstrings). Requires a populated FTS index. Optional kind filter: definition, comment, or string.',
    'SELECT file_path || '':'' || start_line || ''-'' || end_line AS location,
            kind, name, score, text
     FROM search_code(
         $query,
         filter_kind := NULLIF($kind, ''null''),
         limit_n := COALESCE(TRY_CAST(NULLIF($limit, ''null'') AS INT), 20)
     )',
    '{
        "query": {"type": "string", "description": "BM25 search query"},
        "kind": {"type": "string", "description": "Filter by code kind: definition, comment, or string"},
        "limit": {"type": "integer", "description": "Max rows (default 20)"}
    }',
    '["query"]',
    'markdown'
);

SELECT mcp_publish_tool(
    'FtsStats',
    'Counts per extractor/kind of what is currently in the FTS index. Useful for checking whether the index is populated before searching.',
    'SELECT * FROM fts_stats()',
    '{}',
    '[]',
    'markdown'
);
