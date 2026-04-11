-- Fledgling: Workflow Tool Publications
--
-- MCP tool publications for compound workflow query macros.
-- Wraps macros from sql/workflows.sql.
--
-- Each macro returns a single row with one nested STRUCT column called
-- `result`. We use the 'json' output format so the nested shape serializes
-- cleanly for the agent.
--
-- Embeds session_root via _resolve() at publish time. Must be loaded after
-- sandbox.sql and workflows.sql.

PRAGMA mcp_publish_tool(
    'ExploreProject',
    'First-contact project briefing. Bundles language breakdown, top-complexity definitions, doc outline, and recent git activity into one call. Use this before diving into specific files.',
    'SELECT * FROM explore_query(
        root := COALESCE(_resolve(NULLIF($root, ''null'')), _session_root()),
        code_pattern := COALESCE(NULLIF($code_pattern, ''null''), ''**/*.py''),
        doc_pattern := COALESCE(NULLIF($doc_pattern, ''null''), ''docs/**/*.md''),
        top_n := COALESCE(TRY_CAST(NULLIF($top_n, ''null'') AS INT), 20),
        recent_n := COALESCE(TRY_CAST(NULLIF($recent_n, ''null'') AS INT), 10)
    )',
    '{"root": {"type": "string", "description": "Project root directory. Default: session root."}, "code_pattern": {"type": "string", "description": "Glob for source files to summarize (e.g. src/**/*.rs). Default: **/*.py"}, "doc_pattern": {"type": "string", "description": "Glob for doc files to outline (e.g. doc/**/*.md). Default: docs/**/*.md"}, "top_n": {"type": "string", "description": "Max structure/docs entries. Default: 20"}, "recent_n": {"type": "string", "description": "Max recent commits. Default: 10"}}',
    '[]',
    'json'
);

PRAGMA mcp_publish_tool(
    'InvestigateSymbol',
    'Deep dive on a named symbol: definitions, enclosing-function callers, and individual call sites. Use when you need the full context around a function or class.',
    'SELECT * FROM investigate_query(
        $name,
        file_pattern := COALESCE(_resolve(NULLIF($file_pattern, ''null'')), ''**/*.py'')
    )',
    '{"name": {"type": "string", "description": "Symbol name to investigate. Supports SQL LIKE wildcards (e.g. parse% or %Config%)"}, "file_pattern": {"type": "string", "description": "Glob for files to search (e.g. src/**/*.py). Default: **/*.py"}}',
    '["name"]',
    'json'
);

PRAGMA mcp_publish_tool(
    'ReviewChanges',
    'Change review briefing between two git revisions. Returns changed files and the functions ranked by complexity that were affected. Use to prep for code review or understand what a branch introduces.',
    'SELECT * FROM review_query(
        from_rev := COALESCE(NULLIF($from_rev, ''null''), ''HEAD~1''),
        to_rev := COALESCE(NULLIF($to_rev, ''null''), ''HEAD''),
        file_pattern := COALESCE(_resolve(NULLIF($file_pattern, ''null'')), ''**/*.py''),
        repo := COALESCE(_resolve(NULLIF($repo, ''null'')), _session_root()),
        top_n := COALESCE(TRY_CAST(NULLIF($top_n, ''null'') AS INT), 20)
    )',
    '{"from_rev": {"type": "string", "description": "Starting git revision. Default: HEAD~1"}, "to_rev": {"type": "string", "description": "Ending git revision. Default: HEAD"}, "file_pattern": {"type": "string", "description": "Glob for source files whose functions to analyze. Default: **/*.py"}, "repo": {"type": "string", "description": "Repository root. Default: session root."}, "top_n": {"type": "string", "description": "Max function summary entries. Default: 20"}}',
    '[]',
    'json'
);

PRAGMA mcp_publish_tool(
    'SearchProject',
    'Multi-source search: finds matching definitions, call sites, and doc sections in one call. Use when you have a pattern (name or keyword) and want to see every place it appears.',
    'SELECT * FROM search_query(
        $pattern,
        file_pattern := COALESCE(_resolve(NULLIF($file_pattern, ''null'')), ''**/*.py''),
        doc_pattern := COALESCE(_resolve(NULLIF($doc_pattern, ''null'')), ''docs/**/*.md''),
        top_n := COALESCE(TRY_CAST(NULLIF($top_n, ''null'') AS INT), 50)
    )',
    '{"pattern": {"type": "string", "description": "Name pattern (SQL LIKE wildcards %) for definitions and calls — also used as substring/regex for doc sections"}, "file_pattern": {"type": "string", "description": "Glob for source files. Default: **/*.py"}, "doc_pattern": {"type": "string", "description": "Glob for doc files. Default: docs/**/*.md"}, "top_n": {"type": "string", "description": "Max results per section. Default: 50"}}',
    '["pattern"]',
    'json'
);

PRAGMA mcp_publish_tool(
    'PssRender',
    'Render code matched by a CSS selector as markdown: file:range headings followed by fenced code blocks. Each match shows the signature line (peek) from the AST — use when you want to see what matches a selector. For full function bodies, use ViewCode.',
    'SELECT * FROM pss_render(
        _resolve($source),
        $selector
    )',
    '{"source": {"type": "string", "description": "Glob for files to search (e.g. src/**/*.py)"}, "selector": {"type": "string", "description": "CSS selector: .func, #name, :has(...), ::callers, etc."}}',
    '["source", "selector"]',
    'text'
);

PRAGMA mcp_publish_tool(
    'AstSelectRender',
    'Render selector query results grouped under a selector heading with per-match sub-headings (symbol name plus file:range). Same matches as PssRender but with a layout grouped by selector. Signature-level code blocks via AST peek.',
    'SELECT * FROM ast_select_render(
        _resolve($source),
        $selector
    )',
    '{"source": {"type": "string", "description": "Glob for files to search (e.g. src/**/*.py)"}, "selector": {"type": "string", "description": "CSS selector: .func, #name, :has(...), ::callers, etc."}}',
    '["source", "selector"]',
    'text'
);
