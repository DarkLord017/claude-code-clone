from __future__ import annotations

import os
from typing import Any, Tuple

import httpx
from pydantic import BaseModel, Field

from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult

LANGSEARCH_SEARCH_URL = "https://api.langsearch.com/v1/web-search"


def _format_results(data: dict) -> Tuple[str, list]:
    """Turn a LangSearch web-search API JSON response into (output_text, metadata_results).

    Defensive against missing/unexpected shape: returns an empty results list
    (never raises) when the expected structure isn't present.
    """
    response_data = data.get("data")
    if not isinstance(response_data, dict):
        return "", []

    web_pages = response_data.get("webPages")
    if not isinstance(web_pages, dict):
        return "", []

    raw_results = web_pages.get("value")
    if not isinstance(raw_results, list):
        return "", []

    results: list = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "title": item.get("name") or "",
                "url": item.get("url") or "",
                "snippet": item.get("snippet") or item.get("text") or "",
            }
        )

    if not results:
        return "", []

    lines = []
    for i, r in enumerate(results, start=1):
        lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}")
    output = "\n\n".join(lines)
    return output, results


class WebSearchParams(BaseModel):

    query: str = Field(
        ...,
        description="The search query.",
    )

    count: int = Field(
        10,
        ge=1,
        le=50,
        description="Number of results to return.",
    )


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web using the LangSearch API and return a list of matching results "
        "(titles, URLs, and short snippets). Requires the LANGSEARCH_API_KEY environment "
        "variable to be configured with a valid LangSearch API key. The same structured "
        "results (title/url/snippet per item) are also available in the tool result's "
        "metadata under 'results', alongside the original 'query'."
    )
    kind = ToolKind.NETWORK

    schema = WebSearchParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebSearchParams(**invocation.params)

        api_key = os.environ.get("LANGSEARCH_API_KEY")
        if not api_key:
            return ToolResult.error_result(
                "Web search is not configured: the LANGSEARCH_API_KEY environment variable "
                "is not set. Get a free API key at https://langsearch.com/ and set it in "
                "your environment."
            )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    LANGSEARCH_SEARCH_URL,
                    json={"query": params.query, "count": params.count},
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
        except (httpx.TimeoutException, httpx.HTTPError, OSError) as e:
            return ToolResult.error_result(f"Web search request failed: {e}")

        if response.status_code in (401, 403):
            return ToolResult.error_result(
                f"Web search failed: the LangSearch API key appears to be invalid "
                f"(HTTP {response.status_code})."
            )

        if response.status_code >= 400:
            body_preview = ""
            try:
                body_preview = response.text[:1000]
            except Exception:
                body_preview = ""
            message = f"Web search failed: HTTP {response.status_code}"
            if body_preview.strip():
                message += f"\n\nResponse body (truncated):\n{body_preview}"
            return ToolResult.error_result(message)

        try:
            data: Any = response.json()
        except ValueError as e:
            return ToolResult.error_result(f"Web search failed: could not parse response JSON ({e}).")

        if not isinstance(data, dict):
            return ToolResult.error_result(
                "Web search failed: unexpected response shape from LangSearch API."
            )

        if data.get("code") not in (200, None):
            msg = data.get("msg") or f"error code {data.get('code')}"
            return ToolResult.error_result(f"Web search failed: {msg}")

        output, results = _format_results(data)

        if not results:
            if "data" not in data:
                return ToolResult.error_result(
                    "Web search failed: unexpected response shape from LangSearch API "
                    "(no 'data' field found)."
                )
            return ToolResult.success_result(
                output=f"No results found for '{params.query}'.",
                metadata={"query": params.query, "results": []},
            )

        return ToolResult.success_result(
            output=output,
            metadata={"query": params.query, "results": results},
        )
