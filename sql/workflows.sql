-- Fledgling: Workflow Query Macros (workflows tier)
--
-- Composed query macros that bundle several existing macros into a single
-- call returning a nested STRUCT with one field per section. These are the
-- "query" half of the compound workflows — cache, formatting, hints, and
-- session state live in squawkit's Python workflow objects.
--
-- Each macro returns a single row with a single `result` struct column.
-- Python consumers unpack via DuckDB's struct->dict conversion. MCP tool
-- publications use the 'json' output format for nested data.
--
-- All macros depend only on macros already defined in source.sql, code.sql,
-- docs.sql, repo.sql, and structural.sql — no new primitives.

-- explore_query: First-contact project briefing.
-- Bundles project_overview + code_structure (top N by complexity)
-- + doc_outline + recent_changes into one struct.
--
-- Examples:
--   SELECT * FROM explore_query();
--   SELECT * FROM explore_query(root := '/path/to/project');
--   SELECT * FROM explore_query(code_pattern := 'src/**/*.rs', doc_pattern := 'doc/**/*.md');
CREATE OR REPLACE MACRO explore_query(
    root := '.',
    code_pattern := '**/*.py',
    doc_pattern := 'docs/**/*.md',
    top_n := 20,
    recent_n := 10
) AS TABLE
    WITH
        pov AS (
            SELECT LIST({
                language: p.language,
                file_count: p.file_count
            }) AS items
            FROM project_overview(root) AS p
        ),
        structure AS (
            SELECT LIST({
                file_path: cs.file_path,
                name: cs.name,
                kind: cs.kind,
                start_line: cs.start_line,
                end_line: cs.end_line,
                line_count: cs.line_count,
                cyclomatic_complexity: cs.cyclomatic_complexity
            }) AS items
            FROM (
                SELECT *
                FROM code_structure(code_pattern)
                ORDER BY cyclomatic_complexity DESC NULLS LAST, line_count DESC
                LIMIT top_n
            ) cs
        ),
        docs AS (
            SELECT LIST({
                file_path: d.file_path,
                section_id: d.section_id,
                level: d.level,
                title: d.title,
                start_line: d.start_line,
                end_line: d.end_line
            }) AS items
            FROM (
                SELECT *
                FROM doc_outline(doc_pattern, max_lvl := 2)
                LIMIT top_n
            ) d
        ),
        recent AS (
            SELECT LIST({
                hash: r.hash,
                author: r.author,
                date: r.date,
                message: r.message
            }) AS items
            FROM recent_changes(recent_n) AS r
        )
    SELECT {
        languages: pov.items,
        structure: structure.items,
        docs: docs.items,
        recent: recent.items
    } AS result
    FROM pov, structure, docs, recent;

-- investigate_query: Deep dive on a named symbol.
-- Returns definitions + callers + call sites for `name` within `file_pattern`.
-- The callers list is enclosing-function-level (from function_callers);
-- the call_sites list is individual call expressions (from find_calls).
--
-- Examples:
--   SELECT * FROM investigate_query('load_sql');
--   SELECT * FROM investigate_query('validate', 'src/**/*.py');
CREATE OR REPLACE MACRO investigate_query(
    name,
    file_pattern := '**/*.py'
) AS TABLE
    WITH
        defs AS (
            SELECT LIST({
                file_path: fd.file_path,
                name: fd.name,
                kind: fd.kind,
                start_line: fd.start_line,
                end_line: fd.end_line,
                signature: fd.signature
            }) AS items
            FROM find_definitions(file_pattern, name_pattern := name) AS fd
        ),
        callers AS (
            SELECT LIST({
                file_path: fc.file_path,
                call_line: fc.call_line,
                caller_name: fc.caller_name,
                caller_kind: fc.caller_kind
            }) AS items
            FROM function_callers(file_pattern, name) AS fc
        ),
        call_sites AS (
            SELECT LIST({
                file_path: cs.file_path,
                name: cs.name,
                start_line: cs.start_line,
                call_expression: cs.call_expression
            }) AS items
            FROM find_calls(file_pattern, name_pattern := name) AS cs
        )
    SELECT {
        definitions: defs.items,
        callers: callers.items,
        call_sites: call_sites.items
    } AS result
    FROM defs, callers, call_sites;

-- review_query: Change review briefing between two git revisions.
-- Bundles file_changes + changed_function_summary (top N by complexity)
-- into one struct. The Python workflow layer adds file_diff output for
-- top-ranked files; this macro returns only the summary data.
--
-- Examples:
--   SELECT * FROM review_query();                          -- HEAD~1..HEAD
--   SELECT * FROM review_query('main', 'HEAD');
--   SELECT * FROM review_query('v1.0', 'v1.1', 'src/**/*.py');
CREATE OR REPLACE MACRO review_query(
    from_rev := 'HEAD~1',
    to_rev := 'HEAD',
    file_pattern := '**/*.py',
    repo := '.',
    top_n := 20
) AS TABLE
    WITH
        changes AS (
            SELECT LIST({
                file_path: fc.file_path,
                status: fc.status,
                old_size: fc.old_size,
                new_size: fc.new_size
            }) AS items
            FROM file_changes(from_rev, to_rev, repo) AS fc
        ),
        functions AS (
            SELECT LIST({
                file_path: f.file_path,
                name: f.name,
                kind: f.kind,
                lines: f.lines,
                cyclomatic: f.cyclomatic,
                change_status: f.change_status
            }) AS items
            FROM (
                SELECT *
                FROM changed_function_summary(from_rev, to_rev, file_pattern, repo)
                ORDER BY cyclomatic DESC, file_path, name
                LIMIT top_n
            ) f
        )
    SELECT {
        changed_files: changes.items,
        function_summary: functions.items
    } AS result
    FROM changes, functions;

-- search_query: Multi-source search over definitions, call sites, and docs.
-- For each source, the `pattern` is used as a LIKE pattern against names
-- (for definitions and calls) and as a substring/regex search (for docs,
-- via doc_outline's search parameter).
--
-- Examples:
--   SELECT * FROM search_query('parse');
--   SELECT * FROM search_query('connect%', file_pattern := 'src/**/*.py');
CREATE OR REPLACE MACRO search_query(
    pattern,
    file_pattern := '**/*.py',
    doc_pattern := 'docs/**/*.md',
    top_n := 50
) AS TABLE
    WITH
        defs AS (
            SELECT LIST({
                file_path: fd.file_path,
                name: fd.name,
                kind: fd.kind,
                start_line: fd.start_line
            }) AS items
            FROM (
                SELECT *
                FROM find_definitions(file_pattern, name_pattern := pattern)
                LIMIT top_n
            ) fd
        ),
        calls AS (
            SELECT LIST({
                file_path: fc.file_path,
                name: fc.name,
                start_line: fc.start_line,
                call_expression: fc.call_expression
            }) AS items
            FROM (
                SELECT *
                FROM find_calls(file_pattern, name_pattern := pattern)
                LIMIT top_n
            ) fc
        ),
        docs AS (
            SELECT LIST({
                file_path: d.file_path,
                section_id: d.section_id,
                level: d.level,
                title: d.title,
                start_line: d.start_line
            }) AS items
            FROM (
                SELECT *
                FROM doc_outline(doc_pattern, search := pattern)
                LIMIT top_n
            ) d
        )
    SELECT {
        definitions: defs.items,
        call_sites: calls.items,
        doc_sections: docs.items
    } AS result
    FROM defs, calls, docs;
