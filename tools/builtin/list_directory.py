from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult
from utils.paths import resolve_path


class ListDirectoryParams(BaseModel):

    path: Optional[str] = Field(
        None,
        description=(
            "Directory to list, relative to the working directory or absolute. "
            "Defaults to the current working directory if not given."
        ),
    )

    recursive: bool = Field(
        False,
        description=(
            "If true, list nested subdirectories recursively instead of just the top level."
        ),
    )

    max_depth: Optional[int] = Field(
        None,
        ge=1,
        description=(
            "When recursive, cap how many levels deep to descend. Ignored if recursive is false."
        ),
    )


class ListDirectoryTool(Tool):
    name = "list_directory"
    description = (
        "List the contents of a directory, with subdirectories marked distinctly from files "
        "(subdirectories are shown with a trailing '/'). By default lists only the immediate "
        "top-level contents of the target directory. Set recursive=true to also descend into "
        "subdirectories, indenting nested entries to show the tree structure; optionally cap "
        "how far it descends with max_depth (max_depth=1 means: show the top-level entries, "
        "and for every subdirectory found there, also show *its* immediate contents — one "
        "level of recursion beyond the plain top-level listing — but do not descend any "
        "further; higher values allow correspondingly more levels). Lists everything under the "
        "target directory faithfully with no hardcoded filtering of hidden files or directories "
        "like .git or node_modules. The listing is capped at a reasonable number of entries to "
        "avoid huge output; if the cap is hit the output text is truncated but the metadata "
        "still reports the true total counts."
    )
    kind = ToolKind.READ

    schema = ListDirectoryParams

    MAX_ENTRIES = 2000

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ListDirectoryParams(**invocation.params)

        if params.path:
            target = resolve_path(invocation.cwd, params.path)
        else:
            target = Path(invocation.cwd).resolve()

        if not target.exists():
            return ToolResult.error_result(f"Directory not found: {target}")

        if not target.is_dir():
            return ToolResult.error_result(f"Path is not a directory: {target}")

        header = target.name if target.name else str(target)
        lines: list[str] = [f"{header}/"]
        counts = {"count": 0, "directories": 0, "files": 0}

        try:
            self._walk(
                target,
                recursion_level=0,
                indent_level=1,
                recursive=params.recursive,
                max_depth=params.max_depth,
                lines=lines,
                counts=counts,
            )
        except (OSError, PermissionError) as e:
            return ToolResult.error_result(f"Failed to list directory {target}: {e}")

        if counts["count"] == 0:
            lines.append("  (empty)")

        entry_lines = lines[1:]
        truncated = False
        if len(entry_lines) > self.MAX_ENTRIES:
            shown = entry_lines[: self.MAX_ENTRIES]
            output_lines = [lines[0]] + shown
            output = "\n".join(output_lines) + (
                f"\n... [truncated: showing {self.MAX_ENTRIES} of {len(entry_lines)} listed "
                f"lines; {counts['count']} entries total]"
            )
            truncated = True
        else:
            output = "\n".join(lines)

        metadata: dict[str, Any] = {
            "path": str(target),
            "count": counts["count"],
            "directories": counts["directories"],
            "files": counts["files"],
        }

        return ToolResult.success_result(output=output, truncated=truncated, metadata=metadata)

    @classmethod
    def _walk(
        cls,
        dir_path: Path,
        recursion_level: int,
        indent_level: int,
        recursive: bool,
        max_depth: Optional[int],
        lines: list[str],
        counts: dict,
    ) -> None:
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: p.name.lower())
        except (PermissionError, OSError) as e:
            lines.append(f"{'  ' * indent_level}[error reading directory: {e}]")
            return

        for entry in entries:
            indent = "  " * indent_level
            try:
                is_dir = entry.is_dir()
            except OSError:
                is_dir = False

            if is_dir:
                lines.append(f"{indent}{entry.name}/")
                counts["directories"] += 1
                counts["count"] += 1
                if recursive and (max_depth is None or recursion_level < max_depth):
                    cls._walk(
                        entry,
                        recursion_level + 1,
                        indent_level + 1,
                        recursive,
                        max_depth,
                        lines,
                        counts,
                    )
            else:
                lines.append(f"{indent}{entry.name}")
                counts["files"] += 1
                counts["count"] += 1
