# Help Tier Validation

## Help

### 6.1 Table of contents

```
Use Fledgling Help with no arguments.

Expected: Returns the skill guide table of contents with section_id,
title, and level columns. Should include sections for each tool category
(File Navigation, Code Intelligence, Documentation, Git) plus Workflows
and Tips sections. Content column should be NULL (TOC mode).
```

### 6.2 Read a specific section

```
Use Fledgling Help with section=quick-reference.

Expected: Returns the Quick Reference section content with a summary
of all available tools and their key parameters.
```

### 6.3 Read a workflow section

```
Use Fledgling Help with section=explore-an-unfamiliar-codebase.

Expected: Returns a workflow guide describing how to use multiple
Fledgling tools together to explore an unfamiliar codebase. Should
reference specific tool names and suggest an order of operations.
```

### 6.4 Invalid section ID

```
Use Fledgling Help with section=nonexistent-section-xyz.

Expected: Returns an empty result (no rows), not an error.
```
