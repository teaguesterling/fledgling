-- Fledgling: Code Intelligence Macros (sitting_duck)
--
-- Semantic code analysis powered by sitting_duck's AST parsing.
-- Replaces grep-based code search with structure-aware queries.

-- find_definitions: Find function, class, or variable definitions.
-- The core code search tool — replaces grep for "where is X defined?"
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
    WHERE is_definition(semantic_type)
      AND name LIKE name_pattern
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

-- code_structure: Get a structural overview of files.
-- Shows the top-level definitions in a file/directory.
--
-- Examples:
--   SELECT * FROM code_structure('src/main.py');
--   SELECT * FROM code_structure('src/**/*.py');
CREATE OR REPLACE MACRO code_structure(file_pattern) AS TABLE
    SELECT
        file_path,
        name,
        semantic_type_to_string(semantic_type) AS kind,
        start_line,
        end_line,
        end_line - start_line + 1 AS line_count
    FROM read_ast(file_pattern)
    WHERE is_definition(semantic_type)
      AND depth <= 2
    ORDER BY file_path, start_line;
