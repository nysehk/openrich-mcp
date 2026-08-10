from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from .service import FlashNewsService, fixture_fetcher


mcp = FastMCP(
    "openrich-financial-news",
    instructions="Read-only financial flash news with a bounded time window and evidence metadata.",
)
READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


class NewsSearchResult(BaseModel):
    source: str
    source_url: str
    retrieved_at: str
    window_hours: int
    query: str
    count: int
    items: list[dict[str, Any]]


def _service() -> FlashNewsService:
    fixture = os.environ.get("OPENRICH_NEWS_FIXTURE")
    now_value = os.environ.get("OPENRICH_NEWS_NOW")
    now = None
    if now_value:
        parsed = datetime.fromisoformat(now_value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)

        def fixed_now() -> datetime:
            return parsed

        now = fixed_now
    if fixture:
        return FlashNewsService(fetch_json=fixture_fetcher(Path(fixture)), now=now)
    return FlashNewsService(now=now)


@mcp.tool(
    name="search",
    description=(
        "Search recent financial flash news. Use a company or topic as query; "
        "hours defaults to the latest 24 hours. Results include evidence metadata."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
def search(query: str = "", hours: int = 24, limit: int = 30) -> NewsSearchResult:
    return NewsSearchResult.model_validate(
        _service().search(query=query, hours=hours, limit=limit)
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
