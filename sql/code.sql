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
    metrics AS (
        SELECT * FROM ast_function_metrics(ast)
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
        m.cyclomatic AS cyclomatic_complexity
    FROM defs d
    LEFT JOIN metrics m ON d.file_path = m.file_path AND d.name = m.name
    ORDER BY d.file_path, d.start_line;

-- complexity_hotspots: Find the most complex functions in a codebase.
-- Returns functions ranked by cyclomatic complexity with structural metrics.
-- Useful for identifying code that needs refactoring or careful review.
--
-- Note: requires materializing the AST into a temp table because
-- ast_function_metrics takes a table reference, not a file pattern.
-- This macro handles that internally.
--
-- Examples:
--   SELECT * FROM complexity_hotspots('src/**/*.py');
--   SELECT * FROM complexity_hotspots('src/**/*.py', 10);
CREATE OR REPLACE MACRO complexity_hotspots(file_pattern, n := 20) AS TABLE
    WITH ast AS (
        SELECT * FROM read_ast(file_pattern)
    ),
    metrics AS (
        SELECT * FROM ast_function_metrics(ast)
    )
    SELECT
        file_path,
        name,
        lines,
        cyclomatic,
        conditionals,
        loops,
        return_count,
        max_depth
    FROM metrics
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

