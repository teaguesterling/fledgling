# Docs Tier Validation

## MDOutline

### 3.1 Full outline

```
Use Fledgling MDOutline on CLAUDE.md with no max_level filter.

Expected: Returns all headings from CLAUDE.md with section_id, level,
title, start_line, and end_line. Should include level 1, 2, and 3
headings. The top-level heading should be "Fledgling: Project Conventions".
```

### 3.2 Filtered by level

```
Use Fledgling MDOutline on CLAUDE.md with max_level=1.

Expected: Returns only the level 1 heading ("Fledgling: Project Conventions").
```

### 3.3 Multiple files

```
Use Fledgling MDOutline on docs/tasks/*.md with max_level=1.

Expected: Returns the top-level heading from each task document. Should
include task titles like "Security Profiles", "Init Script", etc.
```

### 3.4 SKILL.md outline

```
Use Fledgling MDOutline on SKILL.md with max_level=2.

Expected: Returns the skill guide structure with sections like
"Quick Reference", "File Navigation", "Code Intelligence", etc.
```

## MDSection

### 3.5 Read a section by ID

```
Use Fledgling MDSection to read the "architecture" section from CLAUDE.md.

Expected: Returns the content of the Architecture section. Should mention
"SQL macros first, MCP tools second" and mcp_publish_tool().
```

### 3.6 Read a deeper section

```
Use Fledgling MDSection to read the "duckdb-quirks" section from CLAUDE.md.

Expected: Returns the DuckDB Quirks section content listing known issues
and workarounds (sitting_duck, LATERAL UNNEST, etc.).
```

### 3.7 Nested section ID

```
First use Fledgling MDOutline on SKILL.md to find section IDs, then use
MDSection to read the "glob-patterns" section.

Expected: MDOutline returns section IDs. MDSection returns the glob
patterns guide with examples of glob syntax.
```
