-- Fledgling: Documentation Intelligence Macros (duckdb_markdown)
--
-- Structured access to markdown documentation. The documentation
-- counterpart to sitting_duck's source code analysis.

-- doc_outline: Get the structural outline (table of contents) of markdown files.
-- Lets the agent decide what to read before committing tokens.
-- Optional search parameter filters to sections whose title or content
-- matches the term. Search modes:
--   'term'     — case-insensitive substring match (ILIKE)
--   '/regex/'  — regular expression match (regexp_matches)
--
-- Examples:
--   SELECT * FROM doc_outline('**/*.md');
--   SELECT * FROM doc_outline('docs/**/*.md', 2);
--   SELECT * FROM doc_outline('**/*.md', search := 'install');
--   SELECT * FROM doc_outline('**/*.md', search := '/^## (API|CLI)/');
-- `include_filepath := true` yields a column named `filename`, not `file_path`.
-- Every macro here aliases it back, because `file_path` is the OUTPUT contract
-- these macros publish: the tests assert it by name and squackit indexes
-- results by it (workflows.py does def_cols.index("file_path")). Renaming the
-- output instead of aliasing the input would break every consumer quietly.
CREATE OR REPLACE MACRO doc_outline(file_pattern, max_lvl := 3, search := NULL) AS TABLE
    SELECT
        filename AS file_path,
        section_id,
        section_path,
        level,
        title,
        start_line,
        end_line
    FROM read_markdown_sections(
        file_pattern,
        include_content := true,
        max_level := max_lvl,
        include_filepath := true
    )
    WHERE search IS NULL
       OR (search LIKE '/%/' AND (
              regexp_matches(title, search[2:-2], 'i')
              OR regexp_matches(content, search[2:-2], 'i')
           ))
       OR (search NOT LIKE '/%/' AND (
              title ILIKE '%' || search || '%'
              OR content ILIKE '%' || search || '%'
           ))
    ORDER BY file_path, start_line;

-- read_doc_section: Read a specific section from a markdown file.
-- Uses section ID or path prefix matching for flexible section access.
-- Parameter named target_id (not section_id) to avoid shadowing the
-- column s.section_id in the WHERE clause.
--
-- Examples:
--   SELECT * FROM read_doc_section('README.md', 'installation');
--   SELECT * FROM read_doc_section('docs/guide.md', 'getting-started');
CREATE OR REPLACE MACRO read_doc_section(file_path, target_id) AS TABLE
    SELECT
        s.section_id,
        s.title,
        s.level,
        s.content,
        s.start_line,
        s.end_line
    FROM read_markdown_sections(
        file_path,
        content_mode := 'full',
        include_content := true,
        include_filepath := false
    ) s
    WHERE s.section_id = target_id
       OR s.section_path LIKE '%/' || target_id
       OR s.section_path LIKE target_id || '/%';

-- find_code_examples: Extract code blocks from documentation.
-- Optionally filter by language.
--
-- Examples:
--   SELECT * FROM find_code_examples('docs/**/*.md');
--   SELECT * FROM find_code_examples('README.md', 'sql');
CREATE OR REPLACE MACRO find_code_examples(file_pattern, lang := NULL) AS TABLE
    SELECT
        s.filename AS file_path,          -- see doc_outline: the reader emits `filename`
        s.section_id AS section,
        s.title AS section_title,
        cb.language,
        cb.code,
        cb.line_number
    FROM read_markdown_sections(
        file_pattern,
        include_content := true,
        include_filepath := true
    ) s,
    LATERAL (
        SELECT u.language, u.code, u.line_number
        FROM (SELECT UNNEST(md_extract_code_blocks(s.content)) AS u)
    ) cb
    WHERE lang IS NULL OR cb.language = lang;

-- doc_stats: Get statistics about markdown documentation files.
--
-- Examples:
--   SELECT * FROM doc_stats('docs/**/*.md');
CREATE OR REPLACE MACRO doc_stats(file_pattern) AS TABLE
    SELECT
        filename AS file_path,            -- read_markdown drifted the same way
        md_stats(content).word_count AS word_count,
        md_stats(content).heading_count AS heading_count,
        md_stats(content).code_block_count AS code_block_count,
        md_stats(content).link_count AS link_count,
        md_stats(content).reading_time_minutes AS reading_time_min
    FROM read_markdown(file_pattern, include_filepath := true)
    ORDER BY word_count DESC;
