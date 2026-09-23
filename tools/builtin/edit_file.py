from __future__ import annotations

import difflib

from pydantic import BaseModel, Field

from tools import errors
from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult
from utils.paths import is_binary_file, resolve_path


class EditFileParams(BaseModel):

    path: str = Field(
        ...,
        description="Path to the file to edit (relative to working directory or absolute)",
    )

    old_string: str = Field(
        ...,
        min_length=1,
        description=(
            "Exact text to find and replace. Must match the file's content exactly, "
            "including whitespace and indentation."
        ),
    )

    new_string: str = Field(
        ...,
        description="Text to replace old_string with.",
    )

    replace_all: bool = Field(
        False,
        description="Replace every occurrence of old_string instead of requiring exactly one match.",
    )


class EditFileTool(Tool):
    name = "edit_file"
    description = (
        "Edit an existing text file by replacing an exact string with a new one. "
        "The file must already exist — read it first to get the exact text to match. "
        "old_string must match the file's content exactly (including whitespace) and must be "
        "unique in the file unless replace_all is set."
    )
    kind = ToolKind.WRITE

    schema = EditFileParams

    MAX_FILE_SIZE = 1024 * 1024 * 10

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = EditFileParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        if not path.exists():
            return ToolResult.error_result(errors.edit_file_not_found(path))

        if not path.is_file():
            return ToolResult.error_result(errors.path_not_a_file(path))

        file_size = path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            return ToolResult.error_result(errors.file_too_large(file_size, self.MAX_FILE_SIZE))

        if is_binary_file(path):
            return ToolResult.error_result(errors.cannot_edit_binary_file(path.name))

        if params.old_string == params.new_string:
            return ToolResult.error_result(errors.no_op_edit())

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")

        occurrences = content.count(params.old_string)

        if occurrences == 0:
            return ToolResult.error_result(errors.old_string_not_found())

        if occurrences > 1 and not params.replace_all:
            lines = ", ".join(str(n) for n in self._occurrence_lines(content, params.old_string))
            return ToolResult.error_result(errors.old_string_ambiguous(occurrences, lines))

        replace_count = occurrences if params.replace_all else 1
        first_idx = content.find(params.old_string)
        new_content = content.replace(
            params.old_string, params.new_string, -1 if params.replace_all else 1
        )

        try:
            path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            return ToolResult.error_result(errors.write_failed(e))

        snippet = self._snippet_around(new_content, first_idx, len(params.new_string))
        diff = "".join(difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        ))

        return ToolResult.success_result(
            output=(
                f"Edited {path} ({replace_count} replacement{'s' if replace_count != 1 else ''}).\n\n"
                f"{snippet}"
            ),
            metadata={"path": str(path), "replacements": replace_count, "diff": diff},
        )

    @staticmethod
    def _occurrence_lines(content: str, needle: str) -> list[int]:
        """1-based line number each match of `needle` starts on (non-overlapping, matching str.count)."""
        line_numbers = []
        start = 0
        while True:
            idx = content.find(needle, start)
            if idx == -1:
                break
            line_numbers.append(content.count("\n", 0, idx) + 1)
            start = idx + len(needle)
        return line_numbers

    @staticmethod
    def _snippet_around(new_content: str, changed_idx: int, changed_len: int, context_lines: int = 3) -> str:
        lines = new_content.splitlines()
        start_line = new_content.count("\n", 0, changed_idx)
        end_line = new_content.count("\n", 0, changed_idx + changed_len)

        window_start = max(0, start_line - context_lines)
        window_end = min(len(lines), end_line + context_lines + 1)

        return "\n".join(f"{i + 1:6}|{lines[i]}" for i in range(window_start, window_end))
