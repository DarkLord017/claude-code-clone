from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult
from utils.paths import is_binary_file, resolve_path


class SearchParams(BaseModel):

    pattern: str = Field(
        ...,
        description=(
            "For mode='content': a Python regular expression to search file contents for. "
            "For mode='filename': a glob pattern (e.g. '**/*.py') to match file paths against."
        ),
    )

    mode: str = Field(
        "content",
        description=(
            "'content' to search file contents by regex (like grep), or 'filename' to match "
            "file paths by glob pattern (like glob)."
        ),
    )

    path: Optional[str] = Field(
        None,
        description="Directory to search within, relative to the working directory or absolute. Defaults to the working directory.",
    )

    case_sensitive: bool = Field(
        True,
        description="For content mode: whether the regex match is case-sensitive.",
    )

    max_results: int = Field(
        100,
        ge=1,
        le=1000,
        description="Cap on the number of matches returned.",
    )


class SearchTool(Tool):
    name = "search"
    description = (
        "Search for text within files or search for files by name, within a directory tree. "
        "Two modes, selected via the `mode` param: "
        "'content' (default) searches file contents using a Python regular expression — use this "
        "like grep, to find where a symbol, string, or pattern appears across the codebase. "
        "'filename' matches file paths against a glob pattern (e.g. '**/*.py', 'src/**/*.ts') — use "
        "this like glob/find, to locate files by name or extension without caring about their contents. "
        "Binary files are skipped in content mode. Returns both a human-readable text listing in "
        "`output` and structured results in `metadata['results']` (a list of {path, line, text} for "
        "content mode, or {path} for filename mode) along with `metadata['match_count']`."
    )
    kind = ToolKind.READ

    schema = SearchParams

    VALID_MODES = {"content", "filename"}

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = SearchParams(**invocation.params)

        if params.mode not in self.VALID_MODES:
            return ToolResult.error_result(
                f"Invalid mode: '{params.mode}'. Must be one of: {', '.join(sorted(self.VALID_MODES))}."
            )

        root = resolve_path(invocation.cwd, params.path) if params.path else resolve_path(invocation.cwd, ".")

        if not root.exists():
            return ToolResult.error_result(f"Path not found: {root}")

        if not root.is_dir():
            return ToolResult.error_result(f"Path is not a directory: {root}")

        if params.mode == "content":
            return self._search_content(root, params)
        else:
            return self._search_filename(root, params)

    def _search_content(self, root, params: SearchParams) -> ToolResult:
        flags = 0 if params.case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(params.pattern, flags)
        except re.error as e:
            return ToolResult.error_result(f"Invalid regular expression: {e}")

        results: list[dict] = []
        capped = False

        for file_path in sorted(root.rglob("*")):
            if capped:
                break

            if not file_path.is_file():
                continue

            if is_binary_file(file_path):
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    content = file_path.read_text(encoding="latin-1")
                except Exception:
                    continue
            except Exception:
                continue

            for line_number, line in enumerate(content.splitlines(), start=1):
                if regex.search(line):
                    results.append(
                        {
                            "path": self._relativize(file_path, root),
                            "line": line_number,
                            "text": line,
                        }
                    )
                    if len(results) >= params.max_results:
                        capped = True
                        break

        if not results:
            output = "No matches found."
        else:
            lines_out = [f"{r['path']}:{r['line']}: {r['text'].strip()}" for r in results]
            if capped:
                lines_out.append(f"\n... results capped at {params.max_results}")
            output = "\n".join(lines_out)

        return ToolResult.success_result(
            output=output,
            truncated=capped,
            metadata={
                "mode": params.mode,
                "pattern": params.pattern,
                "match_count": len(results),
                "results": results,
            },
        )

    def _search_filename(self, root, params: SearchParams) -> ToolResult:
        results: list[dict] = []
        capped = False

        try:
            matches = root.glob(params.pattern)
        except Exception as e:
            return ToolResult.error_result(f"Invalid glob pattern: {e}")

        for match_path in sorted(matches):
            results.append({"path": self._relativize(match_path, root)})
            if len(results) >= params.max_results:
                capped = True
                break

        if not results:
            output = "No matches found."
        else:
            lines_out = [r["path"] for r in results]
            if capped:
                lines_out.append(f"\n... results capped at {params.max_results}")
            output = "\n".join(lines_out)

        return ToolResult.success_result(
            output=output,
            truncated=capped,
            metadata={
                "mode": params.mode,
                "pattern": params.pattern,
                "match_count": len(results),
                "results": results,
            },
        )

    @staticmethod
    def _relativize(path, root) -> str:
        try:
            return str(path.relative_to(root))
        except ValueError:
            return str(path)
