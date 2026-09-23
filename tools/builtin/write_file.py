from __future__ import annotations

from pydantic import BaseModel, Field

from tools import errors
from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult
from utils.paths import resolve_path


class WriteFileParams(BaseModel):

    path: str = Field(
        ...,
        description="Path to the file to write (relative to working directory or absolute)",
    )

    content: str = Field(
        ...,
        description="Full content to write to the file.",
    )


class WriteFileTool(Tool):
    name = "write_file"
    description = (
        "Create a brand-new file or completely overwrite an existing file's content. "
        "Use this only for creating new files or for full-file rewrites — for a surgical, "
        "partial change to a file that already exists (e.g. changing a few lines), use "
        "edit_file instead. write_file replaces the entire content of an existing file "
        "with no confirmation of what was there before, so anything not included in the "
        "new content is permanently lost."
    )
    kind = ToolKind.WRITE

    schema = WriteFileParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WriteFileParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        if path.exists() and not path.is_file():
            return ToolResult.error_result(errors.path_not_a_file(path))

        created = not path.exists()

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(params.content, encoding="utf-8")
        except Exception as e:
            return ToolResult.error_result(errors.write_failed(e))

        bytes_written = len(params.content.encode("utf-8"))
        verb = "Created" if created else "Overwrote"

        return ToolResult.success_result(
            output=f"{verb} {path} ({bytes_written} bytes).",
            metadata={
                "path": str(path),
                "created": created,
                "bytes_written": bytes_written,
            },
        )
