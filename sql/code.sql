-- Fledgling: Code Intelligence Macros (sitting_duck)
--
-- Semantic code analysis powered by sitting_duck's AST parsing.
-- Replaces grep-based code search with structure-aware queries.

-- find_definitions: Find function, class, or variable definitions.
-- The core code search tool — replaces grep for "where is X defined?"
--
-- Default behavior (no name_pattern): returns only function, class, and module
-- definitions at depth <= 2, filtering out inner variable assignments.
-- When name_pattern is provided (not '%'): also includes variable definitions,
-- allowing targeted search for specific named variables.
--
-- Examples:
--   SELECT * FROM find_definitions('**/*.py');
--   SELECT * FROM find_definitions('src/**/*.py', 'parse%');
CREATE OR REPLACE MACRO find_definitions(file_pattern, name_pattern := '%') AS TABLE
    SELECT
        file_path,
        name,
        semantic_type_to_string(semantic_type) AS kind,
        start_line,
        end_line,
        peek AS signature
    FROM read_ast(file_pattern)
    WHERE name != ''
      AND name LIKE name_pattern
      AND (
          -- When name_pattern is '%' (default): only structural definitions at top level
          (name_pattern = '%'
              AND (is_function_definition(semantic_type)
                   OR is_class_definition(semantic_type)
                   OR is_module_definition(semantic_type))
              AND depth <= 2)
          OR
          -- When name_pattern is provided: include variable definitions too
          (name_pattern != '%'
              AND is_definition(semantic_type))
      )
    ORDER BY file_path, start_line;

-- find_calls: Find function/method call sites.
-- Answers "where is this function called?"
--
-- Examples:
--   SELECT * FROM find_calls('**/*.py');
--   SELECT * FROM find_calls('src/**/*.py', 'connect%');
CREATE OR REPLACE MACRO find_calls(file_pattern, name_pattern := '%') AS TABLE
    SELECT
        file_path,
        name,
        start_line,
        peek AS call_expression
    FROM read_ast(file_pattern)
    WHERE is_call(semantic_type)
      AND name LIKE name_pattern
    ORDER BY file_path, start_line;

-- find_imports: Find import/include statements.
-- Answers "what does this file depend on?"
--
-- Examples:
--   SELECT * FROM find_imports('**/*.py');
CREATE OR REPLACE MACRO find_imports(file_pattern) AS TABLE
    SELECT
        file_path,
        name,
        peek AS import_statement,
        start_line
    FROM read_ast(file_pattern)
    WHERE is_import(semantic_type)
    ORDER BY file_path, start_line;

-- find_in_ast: Search AST by semantic category.
-- Generalizes find_calls, find_imports, and other AST queries into a
-- single parameterized search. The kind parameter maps to sitting_duck's
-- semantic type predicates.
--
-- Supported kinds:
--   'calls'       — function/method call sites (is_call)
--   'imports'     — import/include statements (is_import)
--   'definitions' — all definitions (is_definition)
--   'loops'       — loop constructs (is_loop)
--   'conditionals'— if/switch/ternary (is_conditional)
--   'strings'     — string literals (is_string_literal)
--   'comments'    — comments and docstrings (is_comment)
--
-- Examples:
--   SELECT * FROM find_in_ast('src/**/*.py', 'calls');
--   SELECT * FROM find_in_ast('src/**/*.py', 'calls', 'connect%');
--   SELECT * FROM find_in_ast('src/**/*.py', 'imports');
CREATE OR REPLACE MACRO find_in_ast(file_pattern, kind, name_pattern := '%') AS TABLE
    SELECT
        file_path,
        name,
        start_line,
        peek AS context
    FROM read_ast(file_pattern)
    WHERE name LIKE name_pattern
      AND CASE kind
          WHEN 'calls' THEN is_call(semantic_type)
          WHEN 'imports' THEN is_import(semantic_type)
          WHEN 'definitions' THEN is_definition(semantic_type)
          WHEN 'loops' THEN is_loop(semantic_type)
          WHEN 'conditionals' THEN is_conditional(semantic_type)
          WHEN 'strings' THEN is_string_literal(semantic_type)
          WHEN 'comments' THEN is_comment(semantic_type)
          ELSE false
      END
    ORDER BY file_path, start_line;

-- find_code: Search code using CSS selector syntax (via ast_select).
-- NOTE: Requires sitting_duck with ast_select support (not yet in community extensions).
-- Returns a compact listing: location, name, type, and one-line preview.
-- The selector follows sitting_duck's CSS selector syntax:
--   .func, .class, .call, .import, .loop, .if  (semantic types)
--   #name                                       (name filter)
--   :has(child), :not(:has(child))              (structural)
--   ::callers, ::callees, ::parent              (navigation)
--
-- Examples:
--   SELECT * FROM find_code('**/*.py', '.func');
--   SELECT * FROM find_code('**/*.py', '.func#validate');
--   SELECT * FROM find_code('**/*.py', '.func:has(.call#execute)');
--   SELECT * FROM find_code('**/*.py', '.func:has(.call#execute):not(:has(try))');
--   SELECT * FROM find_code('**/*.py', '.func#validate::callers');
CREATE OR REPLACE MACRO find_code(file_pattern, selector, lang := NULL) AS TABLE
    SELECT
        file_path,
        start_line,
        end_line,
        name,
        semantic_type_to_string(semantic_type) AS kind,
        type AS node_type,
        peek
    FROM ast_select(file_pattern, selector, language := lang)
    ORDER BY file_path, start_line;

-- view_code: Read source for code matched by CSS selector.
-- NOTE: Requires sitting_duck with ast_select support (not yet in community extensions).
-- Like find_code but returns the actual source lines with context.
-- Each result block is prefixed with a header: # file.py:start-end
--
-- Examples:
--   SELECT * FROM view_code('**/*.py', '.func#main');
--   SELECT * FROM view_code('**/*.py', '.func#validate', ctx := 5);
--   SELECT * FROM view_code('**/*.py', '.func::callers');
CREATE OR REPLACE MACRO view_code(file_pattern, selector, lang := NULL, ctx := 0) AS TABLE
    WITH matches AS (
        SELECT DISTINCT file_path, start_line, end_line, name
        FROM ast_select(file_pattern, selector, language := lang)
        ORDER BY file_path, start_line
    )
    SELECT
        m.file_path,
        m.name,
        m.start_line AS match_start,
        m.end_line AS match_end,
        r.line_number,
        r.content
    FROM matches m,
    LATERAL (
        SELECT line_number, content
        FROM read_lines(
            m.file_path,
            CAST(greatest(1, m.start_line - ctx) AS VARCHAR)
                || '-'
                || CAST(m.end_line + ctx AS VARCHAR)
        )
    ) r
    ORDER BY m.file_path, m.start_line, r.line_number;

-- code_structure: Get a structural overview of files with complexity metrics.
-- Shows top-level definitions with size and complexity indicators for triage.
-- Use this to answer "which functions are large or complex?" before reading code.
-- Use find_definitions for navigation ("where is X defined?").
--
-- Examples:
--   SELECT * FROM code_structure('src/main.py');
--   SELECT * FROM code_structure('src/**/*.py');
CREATE OR REPLACE MACRO code_structure(file_pattern) AS TABLE
    WITH ast AS (
        SELECT * FROM read_ast(file_pattern)
    ),
    defs AS (
        SELECT
            file_path,
            name,
            node_id,
            semantic_type,
            start_line,
            end_line,
            descendant_count,
            children_count
        FROM ast
        WHERE is_definition(semantic_type)
          AND name != ''
          AND depth <= 2
    ),
    func_complexity AS (
        SELECT
            d.node_id,
            count(CASE WHEN is_conditional(n.semantic_type)
                AND (n.type LIKE '%_statement' OR n.type LIKE '%_clause'
                     OR n.type LIKE '%_expression' OR n.type LIKE '%_arm'
                     OR n.type LIKE '%_case' OR n.type LIKE '%_branch')
                THEN 1 END) AS conditionals,
            count(CASE WHEN is_loop(n.semantic_type)
                AND (n.type LIKE '%_statement' OR n.type LIKE '%_expression'
                     OR n.type LIKE '%_loop')
                THEN 1 END) AS loops
        FROM defs d
        JOIN ast n ON n.node_id > d.node_id
                  AND n.node_id <= d.node_id + d.descendant_count
        WHERE is_function_definition(d.semantic_type)
        GROUP BY d.node_id
    )
    SELECT
        d.file_path,
        d.name,
        semantic_type_to_string(d.semantic_type) AS kind,
        d.start_line,
        d.end_line,
        d.end_line - d.start_line + 1 AS line_count,
        d.descendant_count,
        d.children_count,
        CASE WHEN is_function_definition(d.semantic_type)
             THEN fc.conditionals + fc.loops + 1
             ELSE NULL END AS cyclomatic_complexity
    FROM defs d
    LEFT JOIN func_complexity fc ON d.node_id = fc.node_id
    ORDER BY d.file_path, d.start_line;

-- find_class_members: List direct members of a class node.
-- Returns function/method definitions, class-level assignments, nested
-- classes, and top-level expression statements (docstrings) inside a
-- class body. Thin wrapper around sitting_duck's `ast_class_members`
-- macro — pulls `read_ast` into a CTE so callers only pass a file path
-- and the target class's node_id.
--
-- The class_node_id must come from a prior query that identifies the
-- class node (e.g. via find_definitions or direct read_ast on the file).
-- Callers typically filter the result further by `type` to show only the
-- kinds of members they care about.
--
-- Examples:
--   -- Find Connection class's direct members
--   WITH target AS (
--     SELECT node_id FROM find_definitions('src/foo.py', 'Connection')
--     LIMIT 1
--   )
--   SELECT m.name, m.type, m.start_line
--   FROM target t, find_class_members('src/foo.py', t.node_id) m
--   WHERE m.type IN ('function_definition', 'method_definition');
CREATE OR REPLACE MACRO find_class_members(file_path, class_node_id) AS TABLE
    WITH ast AS (
        SELECT * FROM read_ast(file_path)
    )
    SELECT
        node_id,
        type,
        name,
        start_line,
        end_line,
        language,
        peek,
        descendant_count,
        depth,
        parent_id
    FROM ast_class_members(ast, class_node_id)
    ORDER BY start_line;

-- complexity_hotspots: Find the most complex functions in a codebase.
-- Returns functions ranked by cyclomatic complexity with structural metrics.
-- Useful for identifying code that needs refactoring or careful review.
-- Inlines the complexity calculation (avoids CTE-as-table-ref issue with
-- ast_function_metrics in some execution paths).
--
-- Examples:
--   SELECT * FROM complexity_hotspots('src/**/*.py');
--   SELECT * FROM complexity_hotspots('src/**/*.py', 10);
CREATE OR REPLACE MACRO complexity_hotspots(file_pattern, n := 20) AS TABLE
    WITH ast AS (
        SELECT * FROM read_ast(file_pattern)
    ),
    funcs AS (
        SELECT node_id, file_path, name, start_line, end_line, depth AS func_depth, descendant_count
        FROM ast
        WHERE is_function_definition(semantic_type)
          AND name IS NOT NULL AND name != ''
    ),
    func_metrics AS (
        SELECT
            f.node_id,
            f.file_path,
            f.name,
            f.start_line,
            f.end_line,
            (f.end_line - f.start_line + 1) AS lines,
            count(CASE WHEN n.type = 'return_statement' THEN 1 END) AS return_count,
            count(CASE WHEN is_conditional(n.semantic_type)
                AND (n.type LIKE '%_statement' OR n.type LIKE '%_clause'
                     OR n.type LIKE '%_expression' OR n.type LIKE '%_arm'
                     OR n.type LIKE '%_case' OR n.type LIKE '%_branch')
                THEN 1 END) AS conditionals,
            count(CASE WHEN is_loop(n.semantic_type)
                AND (n.type LIKE '%_statement' OR n.type LIKE '%_expression'
                     OR n.type LIKE '%_loop')
                THEN 1 END) AS loops,
            COALESCE(CAST(max(n.depth) AS INTEGER) - CAST(f.func_depth AS INTEGER), 0) AS max_depth
        FROM funcs f
        LEFT JOIN ast n ON n.node_id > f.node_id
                       AND n.node_id <= f.node_id + f.descendant_count
        GROUP BY f.node_id, f.file_path, f.name, f.start_line, f.end_line, f.func_depth
    )
    SELECT
        file_path,
        name,
        lines,
        conditionals + loops + 1 AS cyclomatic,
        conditionals,
        loops,
        return_count,
        max_depth
    FROM func_metrics
    ORDER BY cyclomatic DESC
    LIMIT n;

-- function_callers: Find all call sites for a named function across a codebase.
-- Answers "who calls X?" — the reverse of find_calls which shows what a file calls.
-- Groups by calling file and shows the enclosing function for each call site.
--
-- Examples:
--   SELECT * FROM function_callers('src/**/*.py', 'parse_config');
--   SELECT * FROM function_callers('**/*.py', 'validate');
CREATE OR REPLACE MACRO function_callers(file_pattern, func_name) AS TABLE
    WITH calls AS (
        SELECT
            file_path,
            start_line,
            node_id
        FROM read_ast(file_pattern)
        WHERE is_call(semantic_type)
          AND name = func_name
    ),
    enclosing AS (
        SELECT
            file_path,
            name,
            semantic_type_to_string(semantic_type) AS kind,
            start_line AS def_start,
            end_line AS def_end
        FROM read_ast(file_pattern)
        WHERE is_definition(semantic_type)
          AND semantic_type_to_string(semantic_type) IN
              ('DEFINITION_FUNCTION', 'DEFINITION_CLASS', 'DEFINITION_MODULE')
          AND name != ''
    ),
    matched AS (
        SELECT
            c.file_path,
            c.start_line AS call_line,
            e.name AS caller_name,
            e.kind AS caller_kind,
            e.def_end - e.def_start AS scope_size,
            row_number() OVER (
                PARTITION BY c.file_path, c.start_line
                ORDER BY e.def_end - e.def_start
            ) AS rn
        FROM calls c
        LEFT JOIN enclosing e
            ON c.file_path = e.file_path
           AND c.start_line BETWEEN e.def_start AND e.def_end
    )
    SELECT file_path, call_line, caller_name, caller_kind
    FROM matched
    WHERE rn = 1
    ORDER BY file_path, call_line;

-- module_dependencies: Map internal import relationships across a codebase.
-- Shows which modules import which, with fan-in count (how many modules
-- depend on each target). Filters to imports matching a given package prefix.
--
-- Examples:
--   SELECT * FROM module_dependencies('src/**/*.py', 'myapp');
--   SELECT * FROM module_dependencies('lib/**/*.py', 'lib');
CREATE OR REPLACE MACRO module_dependencies(file_pattern, package_prefix) AS TABLE
    WITH raw_imports AS (
        SELECT DISTINCT
            file_path,
            regexp_extract(peek, 'from (' || package_prefix || '[a-zA-Z0-9_.]*)', 1)::VARCHAR AS target_module
        FROM read_ast(file_pattern)
        WHERE is_import(semantic_type)
          AND peek LIKE '%from ' || package_prefix || '%'
    ),
    edges AS (
        SELECT
            replace(replace(
                regexp_extract(file_path, '((?:' || package_prefix || ')[a-zA-Z0-9_./]*)\.py$', 1),
            '/', '.'), '__init__', '') AS source_module,
            target_module
        FROM raw_imports
        WHERE target_module != ''
    )
    SELECT
        source_module,
        target_module,
        count(*) OVER (PARTITION BY target_module) AS fan_in
    FROM edges
    WHERE source_module != ''
    ORDER BY source_module, target_module;

