from __future__ import annotations

import json
import re

import httpx
from pydantic import BaseModel, Field

from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult

USER_AGENT = "claude-code-clone/1.0 (+https://github.com/anthropics/claude-code)"

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_LINES_RE = re.compile(r"\n\s*\n+")
_TRAILING_SPACE_RE = re.compile(r"[ \t]+\n")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def strip_html(html: str) -> str:
    """Very small, good-enough HTML-to-text extraction.

    Removes <script>/<style> blocks first (so their contents never leak into the
    output), strips remaining tags, unescapes the most common HTML entities, and
    collapses excess whitespace so the result reads as plain prose.
    """
    text = _SCRIPT_STYLE_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", text)

    entities = {
        "&nbsp;": " ",
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&apos;": "'",
    }
    for entity, replacement in entities.items():
        text = text.replace(entity, replacement)

    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _TRAILING_SPACE_RE.sub("\n", text)
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


class WebFetchParams(BaseModel):

    url: str = Field(
        ...,
        description="The URL to fetch. Must start with http:// or https://.",
    )

    max_chars: int = Field(
        20000,
        ge=1000,
        le=200000,
        description="Maximum characters of extracted text content to return. Longer pages are truncated.",
    )


class WebFetchTool(Tool):
    name = "web_fetch"
    description = (
        "Fetch a URL over the network and return its readable text content. Handles HTML pages "
        "(stripping markup down to readable prose), plain text, and JSON (pretty-printed). Very "
        "long pages are truncated to max_chars. This tool makes a real outbound HTTP request to "
        "the given URL, so it requires user approval before it runs."
    )
    kind = ToolKind.NETWORK

    schema = WebFetchParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebFetchParams(**invocation.params)
        url = params.url

        if not (url.startswith("http://") or url.startswith("https://")):
            return ToolResult.error_result(
                f"Invalid URL scheme: '{url}'. web_fetch only supports http:// and https:// URLs."
            )

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
                response = await client.get(url, headers={"User-Agent": USER_AGENT})
        except (httpx.TimeoutException, httpx.HTTPError, OSError) as e:
            return ToolResult.error_result(f"Failed to fetch {url}: {e}")

        content_type_header = response.headers.get("content-type", "")
        content_type = content_type_header.split(";")[0].strip().lower()

        if response.status_code >= 400:
            body_preview = ""
            try:
                body_preview = response.text[:1000]
            except Exception:
                body_preview = ""
            message = f"Failed to fetch {url}: HTTP {response.status_code}"
            if body_preview.strip():
                message += f"\n\nResponse body (truncated):\n{body_preview}"
            return ToolResult.error_result(message)

        is_html = "html" in content_type
        is_json = content_type == "application/json" or content_type.endswith("+json")
        is_text = content_type.startswith("text/") or content_type in (
            "application/xml",
            "application/javascript",
        )

        if not (is_html or is_json or is_text):
            return ToolResult.error_result(
                f"Cannot fetch {url}: unsupported content type '{content_type_header or 'unknown'}'. "
                "This tool only handles text, HTML, and JSON content."
            )

        raw_text = response.text

        if is_html:
            extracted = strip_html(raw_text)
        elif is_json:
            try:
                parsed = json.loads(raw_text)
                extracted = json.dumps(parsed, indent=2)
            except (json.JSONDecodeError, ValueError):
                extracted = raw_text
        else:
            extracted = raw_text

        metadata = {
            "url": url,
            "status_code": response.status_code,
            "content_type": content_type_header,
        }

        total_chars = len(extracted)
        truncated = total_chars > params.max_chars
        if truncated:
            extracted = extracted[: params.max_chars]
            extracted += f"\n... [truncated, {total_chars} total characters]"

        return ToolResult.success_result(
            output=extracted,
            truncated=truncated,
            metadata=metadata,
        )
