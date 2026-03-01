# Fledgling Validation Prompts

Structured prompts for validating each Fledgling MCP tool. Each file covers
one tier of tools with test cases that exercise core functionality, edge cases,
and parameter combinations.

## How to use

1. Start a Claude Code session with Fledgling configured in `.mcp.json`
2. Copy a prompt from any file below and paste it into the session
3. Verify the output matches the expected behavior described in the prompt
4. Each prompt is self-contained — run them in any order

## Alternative: blq harness

For non-interactive validation, use the `fledgling-tool` blq command:

```sh
blq run fledgling-tool --args tool=ListFiles --extra "pattern=sql/*.sql"
```

## Files

| File | Tools covered |
|---|---|
| `01-files.md` | ListFiles, ReadLines, ReadAsTable |
| `02-code.md` | FindDefinitions, FindCalls, FindImports, CodeStructure |
| `03-docs.md` | MDOutline, MDSection |
| `04-git.md` | GitChanges, GitBranches |
| `05-conversations.md` | ChatSessions, ChatSearch, ChatToolUsage, ChatDetail |
| `06-help.md` | Help |
| `07-analyst.md` | query, describe, list_tables (built-in analyst tools) |
| `08-integration.md` | Multi-tool workflows that combine tools across tiers |
