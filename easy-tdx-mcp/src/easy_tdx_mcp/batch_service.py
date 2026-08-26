from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import re
from time import perf_counter
from typing import Any, Callable

import pandas as pd
from easy_tdx import Adjust, AsyncMacClient, AsyncMacExClient, ExMarket, Market, Period
from easy_tdx.config import (
    get_best_mac_ex_host,
    get_best_mac_host,
    get_mac_ex_hosts,
    get_mac_hosts,
    save_best_mac_ex_host,
    save_best_mac_host,
)


A_SHARE_MARKETS = {"SH": Market.SH, "SZ": Market.SZ, "BJ": Market.BJ}
EXTENDED_MARKETS = {
    "HK_MAIN_BOARD": ExMarket.HK_MAIN_BOARD,
    "US_STOCK": ExMarket.US_STOCK,
}
MARKET_ALIASES = {"HK": "HK_MAIN_BOARD", "US": "US_STOCK"}
PERIODS = {
    "MIN_1": Period.MIN_1,
    "MIN_5": Period.MIN_5,
    "MIN_15": Period.MIN_15,
    "MIN_30": Period.MIN_30,
    "MIN_60": Period.MIN_60,
    "DAILY": Period.DAILY,
    "WEEKLY": Period.WEEKLY,
    "MONTHLY": Period.MONTHLY,
    "QUARTERLY": Period.QUARTERLY,
    "YEARLY": Period.YEARLY,
}
ADJUSTMENTS = {"NONE": Adjust.NONE, "QFQ": Adjust.QFQ, "HFQ": Adjust.HFQ}


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return json.loads(
        frame.to_json(orient="records", date_format="iso", force_ascii=False)
    )


def _retrieved_at() -> str:
    return datetime.now(UTC).isoformat()


def _signed_streak(values: list[float | None], *, positive: bool) -> int:
    count = 0
    for value in reversed(values):
        if value is None or (value <= 0 if positive else value >= 0):
            break
        count += 1
    return count


def _return(closes: list[float], days: int) -> float | None:
    if len(closes) <= days or closes[-days - 1] == 0:
        return None
    return round((closes[-1] / closes[-days - 1] - 1) * 100, 3)


def _quant_metrics(frame: pd.DataFrame | None) -> dict[str, Any] | None:
    if frame is None or frame.empty:
        return None
    source = frame.copy()
    date_column = "date" if "date" in source.columns else "datetime"
    if date_column not in source.columns or "close" not in source.columns:
        return None
    source["date"] = pd.to_datetime(source[date_column], errors="coerce")
    source["close"] = pd.to_numeric(source["close"], errors="coerce")
    source = source.dropna(subset=["date", "close"])
    source = source[source["close"] > 0].sort_values("date")
    if source.empty:
        return None
    volume_column = "volume" if "volume" in source.columns else "vol"
    if volume_column in source.columns:
        source["volume"] = pd.to_numeric(source[volume_column], errors="coerce")
    else:
        source["volume"] = None
    if "amount" in source.columns:
        source["amount"] = pd.to_numeric(source["amount"], errors="coerce")
    else:
        source["amount"] = source["close"] * source["volume"]

    closes = [float(value) for value in source["close"].tolist()]
    changes: list[float | None] = [None]
    for previous, current in zip(closes, closes[1:]):
        changes.append((current / previous - 1) * 100 if previous else None)
    amounts = [None if pd.isna(value) else float(value) for value in source["amount"]]
    amount_changes: list[float | None] = [None]
    for previous, current in zip(amounts, amounts[1:]):
        amount_changes.append(
            None if previous is None or current is None else current - previous
        )
    amount_up = _signed_streak(amount_changes, positive=True)
    amount_down = _signed_streak(amount_changes, positive=False)
    last_date = source.iloc[-1]["date"]
    year_rows = source[source["date"].dt.year == last_date.year]
    ytd = None
    if not year_rows.empty and float(year_rows.iloc[0]["close"]) != 0:
        ytd = round(
            (closes[-1] / float(year_rows.iloc[0]["close"]) - 1) * 100,
            3,
        )
    last_volume = source.iloc[-1]["volume"]
    last_amount = source.iloc[-1]["amount"]
    return {
        "last_date": last_date.date().isoformat(),
        "last_close": round(closes[-1], 4),
        "last_volume": None if pd.isna(last_volume) else float(last_volume),
        "last_amount": None if pd.isna(last_amount) else float(last_amount),
        "pchg_1": round(changes[-1], 3) if changes[-1] is not None else None,
        "ret_5": _return(closes, 5),
        "ret_10": _return(closes, 10),
        "ret_20": _return(closes, 20),
        "ret_60": _return(closes, 60),
        "ret_120": _return(closes, 120),
        "ret_250": _return(closes, 250),
        "ytd": ytd,
        "up_streak": _signed_streak(changes, positive=True),
        "amt_up_streak": amount_up,
        "amt_down_streak": amount_down,
    }


class BatchMarketDataService:
    """High-throughput K-line fetcher used by the MCP batch tool.

    Host selection happens once per batch. Each worker owns one async TCP client,
    preserving the proven legacy concurrency model while keeping the application
    behind the MCP boundary. The easy-tdx async clients handle reconnect and
    cross-host failover for request-time connection failures.
    """

    def __init__(
        self,
        *,
        a_client_factory: Callable[..., Any] = AsyncMacClient,
        ex_client_factory: Callable[..., Any] = AsyncMacExClient,
    ) -> None:
        self.a_client_factory = a_client_factory
        self.ex_client_factory = ex_client_factory

    @staticmethod
    async def _select_a_host(check_hosts: bool, ping_timeout: float) -> str:
        if not check_hosts:
            return get_best_mac_host()
        ranked = await asyncio.to_thread(
            AsyncMacClient.ping_all, get_mac_hosts(), None, ping_timeout
        )
        if not ranked:
            raise RuntimeError("no available A-share MAC market-data host")
        save_best_mac_host(ranked[0][0])
        return ranked[0][0]

    @staticmethod
    async def _select_ex_host(check_hosts: bool, ping_timeout: float) -> str:
        if not check_hosts:
            return get_best_mac_ex_host()
        ranked = await asyncio.to_thread(
            AsyncMacExClient.ping_all, get_mac_ex_hosts(), 7727, ping_timeout
        )
        if not ranked:
            raise RuntimeError("no available extended MAC market-data host")
        save_best_mac_ex_host(ranked[0][0])
        return ranked[0][0]

    async def kline_batch(
        self,
        securities: list[dict[str, str]],
        *,
        count: int = 800,
        period: str = "DAILY",
        adjust: str = "QFQ",
        concurrency: int = 50,
        check_hosts: bool = True,
        ping_timeout: float = 5.0,
        output: str = "records",
    ) -> dict[str, Any]:
        if not securities:
            raise ValueError("at least one security is required")
        if len(securities) > 500:
            raise ValueError("at most 500 securities may be requested at once")
        if not 1 <= int(count) <= 800:
            raise ValueError("count must be between 1 and 800")
        normalized_period = str(period).strip().upper()
        normalized_adjust = str(adjust).strip().upper()
        if normalized_period not in PERIODS:
            raise ValueError(f"unsupported period: {period}")
        if normalized_adjust not in ADJUSTMENTS:
            raise ValueError(f"unsupported adjust mode: {adjust}")
        normalized_output = str(output).strip().lower()
        if normalized_output not in {"records", "quant_metrics"}:
            raise ValueError("output must be records or quant_metrics")
        bounded_concurrency = max(1, min(int(concurrency), 100))
        normalized: list[dict[str, Any]] = []
        needs_a = False
        needs_ex = False
        for index, item in enumerate(securities):
            market = MARKET_ALIASES.get(
                str(item.get("market", "")).strip().upper(),
                str(item.get("market", "")).strip().upper(),
            )
            code = str(item.get("code", "")).strip().upper()
            if market in A_SHARE_MARKETS:
                if not re.fullmatch(r"[0-9]{6}", code):
                    raise ValueError(f"invalid A-share code at index {index}: {code}")
                needs_a = True
            elif market == "HK_MAIN_BOARD":
                if not re.fullmatch(r"[0-9]{1,5}", code):
                    raise ValueError(f"invalid Hong Kong code at index {index}: {code}")
                code = code.zfill(5)
                needs_ex = True
            elif market == "US_STOCK":
                if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", code):
                    raise ValueError(f"invalid US ticker at index {index}: {code}")
                needs_ex = True
            else:
                raise ValueError(f"unsupported market at index {index}: {market}")
            normalized.append({"index": index, "market": market, "code": code})

        selected_hosts: dict[str, str] = {}
        if needs_a:
            selected_hosts["a_share"] = await self._select_a_host(
                check_hosts, ping_timeout
            )
        if needs_ex:
            selected_hosts["extended"] = await self._select_ex_host(
                check_hosts, ping_timeout
            )

        semaphore = asyncio.Semaphore(bounded_concurrency)
        started = perf_counter()

        async def fetch(item: dict[str, Any]) -> dict[str, Any]:
            item_started = perf_counter()
            market = item["market"]
            code = item["code"]
            try:
                async with semaphore:
                    if market in A_SHARE_MARKETS:
                        client = self.a_client_factory(host=selected_hosts["a_share"])
                        async with client as connected:
                            frame = await connected.get_stock_kline(
                                A_SHARE_MARKETS[market],
                                code,
                                period=PERIODS[normalized_period],
                                count=int(count),
                                adjust=ADJUSTMENTS[normalized_adjust],
                            )
                    else:
                        client = self.ex_client_factory(host=selected_hosts["extended"])
                        async with client as connected:
                            frame = await connected.goods_kline(
                                EXTENDED_MARKETS[market],
                                code,
                                period=PERIODS[normalized_period],
                                count=int(count),
                                adjust=ADJUSTMENTS[normalized_adjust],
                            )
                metrics = _quant_metrics(frame) if normalized_output == "quant_metrics" else None
                rows = _records(frame) if normalized_output == "records" else []
                available = metrics is not None if normalized_output == "quant_metrics" else bool(rows)
                return {
                    **item,
                    "status": "available" if available else "unavailable",
                    "records": rows,
                    "metrics": metrics,
                    "returned_count": len(frame) if frame is not None else 0,
                    "retrieved_at": _retrieved_at(),
                    "duration_ms": int((perf_counter() - item_started) * 1000),
                    "error": None if available else "empty K-line response",
                }
            except Exception as exc:
                return {
                    **item,
                    "status": "unavailable",
                    "records": [],
                    "metrics": None,
                    "returned_count": 0,
                    "retrieved_at": _retrieved_at(),
                    "duration_ms": int((perf_counter() - item_started) * 1000),
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                }

        items = await asyncio.gather(*(fetch(item) for item in normalized))
        available = sum(item["status"] == "available" for item in items)
        return {
            "status": "available" if available else "unavailable",
            "source": "easy_tdx",
            "request_type": "kline_batch",
            "requested_count": len(items),
            "available_count": available,
            "error_count": len(items) - available,
            "period": normalized_period,
            "adjust": normalized_adjust,
            "bar_count": int(count),
            "output": normalized_output,
            "concurrency": bounded_concurrency,
            "selected_hosts": selected_hosts,
            "duration_ms": int((perf_counter() - started) * 1000),
            "retrieved_at": _retrieved_at(),
            "items": items,
        }
