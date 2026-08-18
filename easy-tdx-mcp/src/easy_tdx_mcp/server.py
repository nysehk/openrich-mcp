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

from .client_tools import register_client_tools
from .advanced_tools import register_advanced_tools
from .offline_tools import register_offline_tools
from .research_tools import register_research_tools
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
        "Self-contained Easy TDX fork for A-share, Hong Kong, US and futures market "
        "data, indicators, Chanlun analysis and research backtests. Use market_* for "
        "the recommended Mac protocol, standard_* for legacy standard-protocol-only "
        "features, and extended_* for Hong Kong/US/futures. Tool arguments containing "
        "protocol method parameters are named 'arguments'. This server is for research "
        "only and does not provide trading or investment advice."
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

CLIENT_TOOL_NAMES = register_client_tools(mcp)
OFFLINE_TOOL_NAMES = register_offline_tools(mcp)
register_research_tools(mcp)
ADVANCED_TOOL_NAMES = register_advanced_tools(mcp, STATE_ROOT)


@mcp.resource(
    "resource://easy-tdx/capabilities",
    name="easy_tdx_capabilities",
    description="自包含 fork 的 MCP 工具命名、覆盖范围和选用建议。",
    mime_type="application/json",
)
def capabilities() -> dict[str, Any]:
    return {
        "implementation": "self-contained source fork",
        "upstream": {
            "repository": "https://github.com/handsomejustin/easy_tdx",
            "baseline_commit": "e533b70",
            "baseline_version": "1.20.6",
            "license": "MIT",
        },
        "client_tools": CLIENT_TOOL_NAMES,
        "offline_tools": OFFLINE_TOOL_NAMES,
        "advanced_tools": ADVANCED_TOOL_NAMES,
        "tool_prefixes": {
            "market_": "推荐的 A 股 Mac 协议：复权 K 线、分类报价、板块、竞价、异动等",
            "standard_": "标准协议独有功能：证券列表、F10、除权、历史财务、市场统计等",
            "extended_": "港股、美股、期货等扩展市场",
            "analysis_": "纯计算指标与缠论，可直接传入 OHLCV records",
            "backtest_": "研究型历史回测",
        },
        "catalog_resources": [
            "resource://easy-tdx/indicators",
            "resource://easy-tdx/strategies",
            "resource://easy-tdx/factors",
        ],
        "disclaimer": "仅供学习和技术研究，不构成投资建议。",
    }


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
