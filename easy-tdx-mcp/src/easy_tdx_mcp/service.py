from __future__ import annotations

from datetime import UTC, datetime
import json
import re
from typing import Any, Callable, Literal

import pandas as pd
from easy_tdx import Adjust, Market, Period, UnifiedTdxClient


MarketName = Literal["SZ", "SH", "BJ"]
PeriodName = Literal[
    "1MIN",
    "5MIN",
    "15MIN",
    "30MIN",
    "60MIN",
    "DAILY",
    "WEEKLY",
    "MONTHLY",
]
AdjustName = Literal["NONE", "QFQ", "HFQ"]

MARKETS: dict[str, Market] = {"SZ": Market.SZ, "SH": Market.SH, "BJ": Market.BJ}
PERIODS: dict[str, Period] = {
    "1MIN": Period.MIN_1,
    "5MIN": Period.MIN_5,
    "15MIN": Period.MIN_15,
    "30MIN": Period.MIN_30,
    "60MIN": Period.MIN_60,
    "DAILY": Period.DAILY,
    "WEEKLY": Period.WEEKLY,
    "MONTHLY": Period.MONTHLY,
}
ADJUSTMENTS: dict[str, Adjust] = {
    "NONE": Adjust.NONE,
    "QFQ": Adjust.QFQ,
    "HFQ": Adjust.HFQ,
}
SYMBOL_PATTERN = re.compile(r"^(SZ|SH|BJ)\s+([0-9]{6})$", re.IGNORECASE)


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", date_format="iso", force_ascii=False))


def _retrieved_at() -> str:
    return datetime.now(UTC).isoformat()


def _cninfo_client() -> Any:
    try:
        from easy_tdx.cninfo import CninfoClient
    except ImportError:
        from .cninfo_compat import CninfoHttpClient

        return CninfoHttpClient()
    else:
        return CninfoClient()


class MarketDataService:
    def __init__(self, client_factory: Callable[..., Any] = UnifiedTdxClient) -> None:
        self.client_factory = client_factory

    def kline(
        self,
        market: MarketName,
        code: str,
        *,
        count: int = 30,
        period: PeriodName = "DAILY",
        adjust: AdjustName = "NONE",
    ) -> dict[str, Any]:
        normalized_market = market.upper()
        normalized_period = period.upper()
        normalized_adjust = adjust.upper()
        if not re.fullmatch(r"[0-9]{6}", code):
            raise ValueError("code must contain exactly 6 digits")
        if not 1 <= count <= 800:
            raise ValueError("count must be between 1 and 800")

        with self.client_factory() as client:
            frame = client.get_stock_kline(
                MARKETS[normalized_market],
                code,
                period=PERIODS[normalized_period],
                count=count,
                adjust=ADJUSTMENTS[normalized_adjust],
            )
        rows = _records(frame)
        return {
            "source": "easy_tdx",
            "market": normalized_market,
            "code": code,
            "period": normalized_period,
            "adjust": normalized_adjust,
            "requested_count": count,
            "returned_count": len(rows),
            "retrieved_at": _retrieved_at(),
            "records": rows,
        }

    def quote(self, symbols: str) -> dict[str, Any]:
        parsed: list[tuple[Market, str]] = []
        normalized_symbols: list[str] = []
        for raw_symbol in symbols.split(","):
            match = SYMBOL_PATTERN.fullmatch(raw_symbol.strip())
            if match is None:
                raise ValueError(
                    'symbols must use the format "SZ 000001,SH 600519"'
                )
            market_name, code = match.groups()
            market_name = market_name.upper()
            parsed.append((MARKETS[market_name], code))
            normalized_symbols.append(f"{market_name} {code}")
        if not parsed:
            raise ValueError("at least one symbol is required")
        if len(parsed) > 20:
            raise ValueError("at most 20 symbols may be requested at once")

        with self.client_factory() as client:
            frame = client.get_stock_quotes(parsed)
        rows = _records(frame)
        return {
            "source": "easy_tdx",
            "symbols": normalized_symbols,
            "returned_count": len(rows),
            "retrieved_at": _retrieved_at(),
            "records": rows,
        }


class AnnouncementService:
    """Read-only announcement search backed by easy_tdx's CNInfo client."""

    def __init__(self, client_factory: Callable[[], Any] = _cninfo_client) -> None:
        self.client_factory = client_factory

    def search(
        self,
        code: str,
        *,
        count: int = 30,
        page: int = 1,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9]{6}", code):
            raise ValueError("code must contain exactly 6 digits")
        if not 1 <= count <= 100:
            raise ValueError("count must be between 1 and 100")
        if not 1 <= page <= 1000:
            raise ValueError("page must be between 1 and 1000")

        try:
            client = self.client_factory()
            frame = client.get_announcements(code, count=count, page=page)
        except Exception as exc:
            return {
                "status": "unavailable",
                "source": "cninfo",
                "source_mode": "live_mcp",
                "code": code,
                "page": page,
                "requested_count": count,
                "returned_count": 0,
                "retrieved_at": _retrieved_at(),
                "records": [],
                "data_gaps": [f"CNInfo announcement search failed: {type(exc).__name__}"],
            }
        rows = _records(frame)
        return {
            "status": "available",
            "source": "cninfo",
            "source_mode": "live_mcp",
            "code": code,
            "page": page,
            "requested_count": count,
            "returned_count": len(rows),
            "retrieved_at": _retrieved_at(),
            "records": rows,
            "data_gaps": [],
        }
