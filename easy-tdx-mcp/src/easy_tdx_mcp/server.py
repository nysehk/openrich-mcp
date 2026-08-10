from __future__ import annotations

import os
from pathlib import Path


STATE_ROOT = Path(
    os.environ.get("EASY_TDX_MCP_STATE_DIR", Path.cwd() / ".easy-tdx-state")
).resolve()
STATE_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("EASY_TDX_CONFIG_DIR", str(STATE_ROOT / "easy_tdx"))

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel
from typing import Any

from .service import (
    AdjustName,
    AnnouncementService,
    MarketDataService,
    MarketName,
    PeriodName,
)


mcp = FastMCP(
    "easy-tdx-market-data",
    instructions=(
        "Read-only A-share K-line, real-time quote, and CNInfo announcement tools "
        "backed by easy_tdx."
    ),
)
service = MarketDataService()
announcement_service = AnnouncementService()
READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


class KlineResult(BaseModel):
    source: str
    market: str
    code: str
    period: str
    adjust: str
    requested_count: int
    returned_count: int
    retrieved_at: str
    records: list[dict[str, Any]]


class QuoteResult(BaseModel):
    source: str
    symbols: list[str]
    returned_count: int
    retrieved_at: str
    records: list[dict[str, Any]]


class AnnouncementResult(BaseModel):
    status: str
    source: str
    source_mode: str
    code: str
    page: int
    requested_count: int
    returned_count: int
    retrieved_at: str
    records: list[dict[str, Any]]
    data_gaps: list[str]


@mcp.tool(
    name="kline",
    description=(
        "Get A-share K-line records. Market is SZ/SH/BJ; period supports DAILY, "
        "1MIN, 5MIN, 15MIN, 30MIN, 60MIN, WEEKLY, MONTHLY; adjust is NONE/QFQ/HFQ."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
def kline(
    market: MarketName,
    code: str,
    count: int = 30,
    period: PeriodName = "DAILY",
    adjust: AdjustName = "NONE",
) -> KlineResult:
    result = service.kline(
        market,
        code,
        count=count,
        period=period,
        adjust=adjust,
    )
    return KlineResult.model_validate(result)


@mcp.tool(
    name="quote",
    description='Get real-time quotes. Symbols format: "SZ 000001,SH 600519".',
    annotations=READ_ONLY,
    structured_output=True,
)
def quote(symbols: str) -> QuoteResult:
    return QuoteResult.model_validate(service.quote(symbols))


@mcp.tool(
    name="announcement",
    description=(
        "Search listed-company announcements from CNInfo by six-digit stock code. "
        "Returns direct detail and PDF URLs without downloading files."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
def announcement(
    code: str,
    count: int = 30,
    page: int = 1,
) -> AnnouncementResult:
    return AnnouncementResult.model_validate(
        announcement_service.search(code, count=count, page=page)
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
