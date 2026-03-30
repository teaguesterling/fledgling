"""MCP tool registration for fledgling-edit."""

from __future__ import annotations

from typing import Optional

import duckdb


def register_edit_tools(mcp, con: duckdb.DuckDBPyConnection) -> None:
    """Register fledgling-edit tools on a FastMCP server.

    All tools default to mode="preview" (return diff).
    Use mode="apply" to write changes to disk.
    """
    from fledgling.edit.builder import Editor

    ed = Editor(con)

    @mcp.tool()
    async def EditDefinition(
        file_pattern: str,
        name: str,
        new_content: str,
        mode: str = "preview",
    ) -> str:
        """Replace a definition's body by name.

        Args:
            file_pattern: Glob pattern (e.g., "**/*.py").
            name: Definition name to find.
            new_content: The new code to replace the definition with.
            mode: "preview" returns diff, "apply" writes files.
        """
        cs = ed.definitions(file_pattern, name).replace_with(new_content)
        if mode == "apply":
            paths = cs.apply()
            return f"Applied to: {', '.join(paths)}"
        return cs.diff() or "No changes."

    @mcp.tool()
    async def RemoveDefinition(
        file_pattern: str,
        name: str,
        mode: str = "preview",
    ) -> str:
        """Remove a definition by name.

        Args:
            file_pattern: Glob pattern.
            name: Definition name to remove.
            mode: "preview" returns diff, "apply" writes files.
        """
        cs = ed.definitions(file_pattern, name).remove()
        if mode == "apply":
            paths = cs.apply()
            return f"Applied to: {', '.join(paths)}"
        return cs.diff() or "No changes."

    @mcp.tool()
    async def MoveDefinition(
        file_pattern: str,
        name: str,
        destination_file: str,
        mode: str = "preview",
    ) -> str:
        """Move a definition to another file.

        Args:
            file_pattern: Glob pattern for source files.
            name: Definition name to move.
            destination_file: Target file path.
            mode: "preview" returns diff, "apply" writes files.
        """
        cs = ed.definitions(file_pattern, name).move_to(destination_file)
        if mode == "apply":
            paths = cs.apply()
            return f"Applied to: {', '.join(paths)}"
        return cs.diff() or "No changes."

    @mcp.tool()
    async def RenameSymbol(
        file_pattern: str,
        name: str,
        new_name: str,
        mode: str = "preview",
    ) -> str:
        """Rename a definition (within its own body).

        Args:
            file_pattern: Glob pattern.
            name: Current name.
            new_name: New name.
            mode: "preview" returns diff, "apply" writes files.
        """
        cs = ed.definitions(file_pattern, name).rename(new_name)
        if mode == "apply":
            paths = cs.apply()
            return f"Applied to: {', '.join(paths)}"
        return cs.diff() or "No changes."

    @mcp.tool()
    async def MatchReplace(
        file_pattern: str,
        pattern: str,
        template: str,
        language: str,
        mode: str = "preview",
    ) -> str:
        """Pattern match/replace using AST matching with template substitution.

        Use __NAME__ wildcards in the pattern to capture AST nodes.
        Use the same __NAME__ wildcards in the template to substitute
        the captured source text.

        Args:
            file_pattern: Glob pattern.
            pattern: Code pattern with __NAME__ wildcards.
            template: Replacement template (empty string to remove matches).
            language: Language for pattern parsing (e.g., "python").
            mode: "preview" returns diff, "apply" writes files.
        """
        from fledgling.edit.locate import match_replace as _match_replace
        cs = _match_replace(con, file_pattern, pattern, template, language)
        if mode == "apply":
            paths = cs.apply()
            return f"Applied to: {', '.join(paths)}"
        return cs.diff() or "No changes."
