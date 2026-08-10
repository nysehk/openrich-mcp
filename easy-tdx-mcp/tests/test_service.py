from __future__ import annotations

import pandas as pd
import pytest

from easy_tdx_mcp.service import AnnouncementService, MarketDataService


class FakeClient:
    def __init__(self) -> None:
        self.kline_args = None
        self.quote_args = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def get_stock_kline(self, market, code, **kwargs):
        self.kline_args = (market, code, kwargs)
        return pd.DataFrame([{"date": "2026-08-07", "close": 12.34}])

    def get_stock_quotes(self, stocks):
        self.quote_args = stocks
        return pd.DataFrame([{"code": "000001", "price": 11.23}])


def test_kline_normalizes_dataframe_and_metadata():
    client = FakeClient()
    service = MarketDataService(lambda: client)

    result = service.kline("SH", "600519", count=30, period="5MIN", adjust="QFQ")

    assert result["source"] == "easy_tdx"
    assert result["period"] == "5MIN"
    assert result["adjust"] == "QFQ"
    assert result["returned_count"] == 1
    assert result["records"][0]["close"] == 12.34
    assert client.kline_args[1] == "600519"


def test_quote_parses_cli_compatible_symbol_string():
    client = FakeClient()
    service = MarketDataService(lambda: client)

    result = service.quote("SZ 000001,SH 600519")

    assert result["symbols"] == ["SZ 000001", "SH 600519"]
    assert len(client.quote_args) == 2
    assert result["records"] == [{"code": "000001", "price": 11.23}]


@pytest.mark.parametrize("symbols", ["000001", "XX 000001", "SZ ABCDEF", ""])
def test_quote_rejects_invalid_symbols(symbols):
    service = MarketDataService(lambda: FakeClient())

    with pytest.raises(ValueError):
        service.quote(symbols)


class FakeCninfoClient:
    def __init__(self) -> None:
        self.arguments = None

    def get_announcements(self, code, *, count, page):
        self.arguments = (code, count, page)
        return pd.DataFrame(
            [
                {
                    "title": "2025 年年度报告",
                    "type": "PDF",
                    "date": "2026-03-28",
                    "url": "http://www.cninfo.com.cn/new/disclosure/detail?stockCode=688017",
                    "pdf_url": "http://static.cninfo.com.cn/finalpage/report.PDF",
                }
            ]
        )


def test_announcement_normalizes_cninfo_records_and_provenance():
    client = FakeCninfoClient()
    service = AnnouncementService(lambda: client)

    result = service.search("688017", count=10, page=2)

    assert result["source"] == "cninfo"
    assert result["status"] == "available"
    assert result["source_mode"] == "live_mcp"
    assert result["returned_count"] == 1
    assert result["records"][0]["pdf_url"].endswith(".PDF")
    assert client.arguments == ("688017", 10, 2)


def test_announcement_reports_source_failure_without_fixture():
    class UnavailableClient:
        def get_announcements(self, code, *, count, page):
            raise OSError("network unavailable")

    result = AnnouncementService(lambda: UnavailableClient()).search("688017")

    assert result["status"] == "unavailable"
    assert result["records"] == []
    assert result["data_gaps"] == [
        "CNInfo announcement search failed: OSError"
    ]


@pytest.mark.parametrize(
    ("code", "count", "page"),
    [("68801", 30, 1), ("ABC017", 30, 1), ("688017", 0, 1), ("688017", 30, 0)],
)
def test_announcement_rejects_invalid_arguments(code, count, page):
    service = AnnouncementService(lambda: FakeCninfoClient())

    with pytest.raises(ValueError):
        service.search(code, count=count, page=page)
