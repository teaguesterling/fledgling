-- Fledgling: Full-Text Search Macros (fts)
--
-- BM25-based search over markdown documents and code (definitions and
-- comments). Materializes extracted content into the fts.content table
-- and builds an inverted index via PRAGMA create_fts_index.
--
-- Tables live in the `fts` schema of the current database. Persistence
-- is caller-controlled: an in-memory DB gives an ephemeral index,
-- a persistent DB gives a persistent index.
--
-- Schema columns:
--   id         BIGINT     — primary key (assigned at rebuild time)
--   file_path  VARCHAR    — source file (from read_ast / read_markdown_sections)
--   start_line INTEGER
--   end_line   INTEGER
--   extractor  VARCHAR    — 'markdown' | 'sitting_duck'
--   kind       VARCHAR    — 'doc_section' | 'definition' | 'comment' | 'string'
--   name       VARCHAR    — displayable identifier (symbol or heading title)
--   ordinal    INTEGER    — extractor-defined opaque int (see conventions below)
--   attrs      JSON       — extractor-defined extras
--   text       VARCHAR    — FTS target column
--
-- Per-extractor conventions for opaque fields (not enforced):
--   markdown/doc_section:
--     name    = section title
--     ordinal = heading level (1-6)
--     attrs   = {section_id, section_path, level}
--     text    = title || '\n' || content
--   sitting_duck/definition:
--     name    = symbol name
--     ordinal = AST node_id (for back-reference via read_ast)
--     attrs   = {semantic_type, depth, parent_id}
--     text    = name || ' ' || peek  (symbol + one-line signature)
--   sitting_duck/comment:
--     name    = NULL (comments have no name)
--     ordinal = AST node_id
--     attrs   = {semantic_type, depth, parent_id}
--     text    = comment text (peek)
--   sitting_duck/string:
--     name    = NULL (string literals have no name)
--     ordinal = AST node_id
--     attrs   = {semantic_type, depth, parent_id}
--     text    = string literal (peek) — includes Python docstrings,
--               URLs, SQL, error messages. Filtered to length >= 8.
--
-- Rebuild is triggered externally (via sql/fts_rebuild.sql). This file
-- installs only the schema, table, and search-side macros. Macros are
-- lazy, so defining them is safe even before the index exists — but
-- calling search_* before rebuild will error because the FTS index
-- schema (fts_fts_content) doesn't exist yet.

CREATE SCHEMA IF NOT EXISTS fts;

CREATE TABLE IF NOT EXISTS fts.content (
    id         BIGINT PRIMARY KEY,
    file_path  VARCHAR,
    start_line INTEGER,
    end_line   INTEGER,
    extractor  VARCHAR,
    kind       VARCHAR,
    name       VARCHAR,
    ordinal    INTEGER,
    attrs      JSON,
    text       VARCHAR
);

-- Create a stub BM25 index so fts_fts_content.match_bm25 exists when
-- the search macros below are parsed. DuckDB validates function refs
-- at macro-definition time, so the target has to exist already.
-- overwrite = 1 makes this idempotent across reloads; the rebuild
-- script replaces this with a real index over the populated table.
PRAGMA create_fts_index('fts.content', 'id', 'text', overwrite = 1);

-- search_content: BM25 search across all indexed content.
-- Optional filters narrow by kind and/or extractor.
--
-- Examples:
--   SELECT * FROM search_content('authentication');
--   SELECT * FROM search_content('auth', filter_kind := 'doc_section');
--   SELECT * FROM search_content('login', filter_extractor := 'sitting_duck');
CREATE OR REPLACE MACRO search_content(
    query,
    filter_kind := NULL,
    filter_extractor := NULL,
    limit_n := 20
) AS TABLE
    SELECT *
    FROM (
        SELECT
            c.id,
            c.file_path,
            c.start_line,
            c.end_line,
            c.extractor,
            c.kind,
            c.name,
            c.ordinal,
            c.attrs,
            c.text,
            fts_fts_content.match_bm25(c.id, query) AS score
        FROM fts.content c
    ) scored
    WHERE scored.score IS NOT NULL
      AND (filter_kind IS NULL OR scored.kind = filter_kind)
      AND (filter_extractor IS NULL OR scored.extractor = filter_extractor)
    ORDER BY scored.score DESC
    LIMIT limit_n;

-- search_docs: FTS over markdown sections.
--
-- Examples:
--   SELECT * FROM search_docs('installation');
CREATE OR REPLACE MACRO search_docs(query, limit_n := 20) AS TABLE
    SELECT * FROM search_content(
        query,
        filter_kind := 'doc_section',
        limit_n := limit_n
    );

-- search_code: FTS over code content (definitions, comments, strings).
-- Optional filter_kind narrows to 'definition', 'comment', or 'string'.
--
-- Examples:
--   SELECT * FROM search_code('auth');
--   SELECT * FROM search_code('auth', filter_kind := 'comment');
CREATE OR REPLACE MACRO search_code(query, filter_kind := NULL, limit_n := 20) AS TABLE
    SELECT * FROM search_content(
        query,
        filter_kind := filter_kind,
        filter_extractor := 'sitting_duck',
        limit_n := limit_n
    );

-- fts_stats: Row counts per extractor/kind. Diagnostic view of what's
-- currently in the index. Does NOT require the FTS index to exist —
-- just reads the content table directly.
--
-- Examples:
--   SELECT * FROM fts_stats();
CREATE OR REPLACE MACRO fts_stats() AS TABLE
    SELECT
        extractor,
        kind,
        count(*) AS row_count,
        count(DISTINCT file_path) AS file_count
    FROM fts.content
    GROUP BY extractor, kind
    ORDER BY extractor, kind;
