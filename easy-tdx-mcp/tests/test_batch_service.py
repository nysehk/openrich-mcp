from __future__ import annotations

import asyncio

import pandas as pd

from easy_tdx_mcp.batch_service import BatchMarketDataService


class FakeAsyncClient:
    active = 0
    max_active = 0
    hosts: list[str] = []

    def __init__(self, *, host: str) -> None:
        self.host = host
        self.__class__.hosts.append(host)

    async def __aenter__(self):
        self.__class__.active += 1
        self.__class__.max_active = max(
            self.__class__.max_active, self.__class__.active
        )
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.__class__.active -= 1
        return False

    async def get_stock_kline(self, market, code, **kwargs):
        await asyncio.sleep(0.01)
        return pd.DataFrame([{"date": "2026-08-26", "code": code, "close": 10.0}])

    async def goods_kline(self, market, code, **kwargs):
        await asyncio.sleep(0.01)
        if code == "FAIL":
            raise OSError("simulated source failure")
        return pd.DataFrame([{"date": "2026-08-26", "code": code, "close": 20.0}])


def test_batch_service_preserves_order_and_bounds_concurrency(monkeypatch):
    FakeAsyncClient.active = 0
    FakeAsyncClient.max_active = 0
    FakeAsyncClient.hosts = []
    monkeypatch.setattr(
        BatchMarketDataService,
        "_select_a_host",
        staticmethod(lambda *_: asyncio.sleep(0, result="a.example")),
    )
    monkeypatch.setattr(
        BatchMarketDataService,
        "_select_ex_host",
        staticmethod(lambda *_: asyncio.sleep(0, result="ex.example")),
    )
    service = BatchMarketDataService(
        a_client_factory=FakeAsyncClient,
        ex_client_factory=FakeAsyncClient,
    )

    result = asyncio.run(
        service.kline_batch(
            [
                {"market": "SH", "code": "600519"},
                {"market": "HK", "code": "700"},
                {"market": "US", "code": "AAPL"},
            ],
            concurrency=2,
        )
    )

    assert result["available_count"] == 3
    assert FakeAsyncClient.max_active == 2
    assert [(item["index"], item["code"]) for item in result["items"]] == [
        (0, "600519"),
        (1, "00700"),
        (2, "AAPL"),
    ]
    assert result["selected_hosts"] == {
        "a_share": "a.example",
        "extended": "ex.example",
    }


def test_batch_service_keeps_partial_success(monkeypatch):
    monkeypatch.setattr(
        BatchMarketDataService,
        "_select_ex_host",
        staticmethod(lambda *_: asyncio.sleep(0, result="ex.example")),
    )
    service = BatchMarketDataService(ex_client_factory=FakeAsyncClient)

    result = asyncio.run(
        service.kline_batch(
            [
                {"market": "US", "code": "AAPL"},
                {"market": "US", "code": "FAIL"},
            ],
            check_hosts=False,
        )
    )

    assert result["available_count"] == 1
    assert result["error_count"] == 1
    assert result["items"][1]["status"] == "unavailable"
    assert "simulated source failure" in result["items"][1]["error"]


def test_batch_service_can_return_compact_quant_metrics(monkeypatch):
    monkeypatch.setattr(
        BatchMarketDataService,
        "_select_a_host",
        staticmethod(lambda *_: asyncio.sleep(0, result="a.example")),
    )
    service = BatchMarketDataService(a_client_factory=FakeAsyncClient)

    result = asyncio.run(
        service.kline_batch(
            [{"market": "SH", "code": "600519"}],
            check_hosts=False,
            output="quant_metrics",
        )
    )

    item = result["items"][0]
    assert result["output"] == "quant_metrics"
    assert item["records"] == []
    assert item["metrics"]["last_close"] == 10.0
    assert item["returned_count"] == 1
