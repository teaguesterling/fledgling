-- Fledgling: FTS Rebuild Script
--
-- Fully rebuilds fts.content from markdown files and AST nodes, then
-- (re)creates the BM25 inverted index.
--
-- Assumes sql/fts.sql has been loaded (schema + table + search macros
-- exist) and that resolve() + session_root are set (init-fledgling-base
-- does both).
--
-- Parameters (optional; set via SET VARIABLE before .read):
--   fts_docs_glob — markdown file glob (default '**/*.md')
--   fts_code_glob — code file glob    (default '**/*.py')
--
-- Usage:
--   SET VARIABLE fts_code_glob = 'src/**/*.py';
--   .read sql/fts_rebuild.sql

-- Defaults (preserve caller-set values).
SET VARIABLE fts_docs_glob = COALESCE(getvariable('fts_docs_glob'), '**/*.md');
SET VARIABLE fts_code_glob = COALESCE(getvariable('fts_code_glob'), '**/*.py');

-- Wipe existing content.
DELETE FROM fts.content;

-- Populate from all three sources in one INSERT (monotonic row_number
-- across the union gives a clean, gap-free PK).
INSERT INTO fts.content
WITH all_rows AS (
    -- Markdown sections
    SELECT
        file_path,
        start_line,
        end_line,
        'markdown'::VARCHAR     AS extractor,
        'doc_section'::VARCHAR  AS kind,
        title                   AS name,
        CAST(level AS INTEGER)  AS ordinal,
        json_object(
            'section_id',   section_id,
            'section_path', section_path,
            'level',        level
        )                       AS attrs,
        COALESCE(title, '') || chr(10) || COALESCE(content, '') AS text
    FROM read_markdown_sections(
        resolve(getvariable('fts_docs_glob')),
        include_content := true,
        include_filepath := true
    )
    WHERE (title IS NOT NULL AND title != '')
       OR (content IS NOT NULL AND content != '')

    UNION ALL

    -- Code definitions (functions, classes, modules) — high-signal named nodes
    SELECT
        file_path,
        start_line,
        end_line,
        'sitting_duck'::VARCHAR AS extractor,
        'definition'::VARCHAR   AS kind,
        name,
        CAST(node_id AS INTEGER) AS ordinal,
        json_object(
            'semantic_type', semantic_type_to_string(semantic_type),
            'depth',         depth,
            'parent_id',     parent_id
        )                       AS attrs,
        COALESCE(name, '') || ' ' || COALESCE(peek, '') AS text
    FROM read_ast(resolve(getvariable('fts_code_glob')))
    WHERE name IS NOT NULL
      AND name != ''
      AND (is_function_definition(semantic_type)
        OR is_class_definition(semantic_type)
        OR is_module_definition(semantic_type))

    UNION ALL

    -- Code comments — tree-sitter comment nodes only (not docstrings,
    -- which are string literals in Python). See 'string' branch below.
    SELECT
        file_path,
        start_line,
        end_line,
        'sitting_duck'::VARCHAR AS extractor,
        'comment'::VARCHAR      AS kind,
        NULL                    AS name,
        CAST(node_id AS INTEGER) AS ordinal,
        json_object(
            'semantic_type', semantic_type_to_string(semantic_type),
            'depth',         depth,
            'parent_id',     parent_id
        )                       AS attrs,
        peek                    AS text
    FROM read_ast(resolve(getvariable('fts_code_glob')))
    WHERE is_comment(semantic_type)
      AND peek IS NOT NULL
      AND peek != ''

    UNION ALL

    -- Code string literals — includes Python docstrings (which tree-sitter
    -- classifies as string nodes, not comment nodes), URLs, SQL queries,
    -- error messages, etc. Length filter (>= 8) trims trivial noise like
    -- 'x', '/', single-char constants; meaningful short strings like 'auth'
    -- are covered by definition names already.
    --
    -- is_string_literal matches both the outer string node ("foo") and the
    -- inner string_content (foo). QUALIFY keeps the longest peek per
    -- (file, line span), which is the outer — preserves quoting context
    -- and avoids duplicate hits for the same literal.
    SELECT
        file_path,
        start_line,
        end_line,
        'sitting_duck'::VARCHAR AS extractor,
        'string'::VARCHAR       AS kind,
        NULL                    AS name,
        CAST(node_id AS INTEGER) AS ordinal,
        json_object(
            'semantic_type', semantic_type_to_string(semantic_type),
            'depth',         depth,
            'parent_id',     parent_id
        )                       AS attrs,
        peek                    AS text
    FROM read_ast(resolve(getvariable('fts_code_glob')))
    WHERE is_string_literal(semantic_type)
      AND peek IS NOT NULL
      AND length(peek) >= 8
    QUALIFY row_number() OVER (
        PARTITION BY file_path, start_line, end_line
        ORDER BY length(peek) DESC
    ) = 1
)
SELECT
    row_number() OVER () AS id,
    file_path,
    start_line,
    end_line,
    extractor,
    kind,
    name,
    ordinal,
    attrs,
    text
FROM all_rows;

-- (Re)create BM25 index. overwrite = 1 replaces any existing index
-- with the same target, so this works for both first-build and rebuild.
PRAGMA create_fts_index('fts.content', 'id', 'text', overwrite = 1);
