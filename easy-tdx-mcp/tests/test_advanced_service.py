from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import easy_tdx_mcp.advanced_service as advanced
from easy_tdx_mcp.advanced_service import (
    AnalysisService,
    CompanyService,
    ExternalDataService,
    OfflineSyncService,
    RealtimeService,
    ServerService,
    resolve_write_path,
)


class ContextClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def _price_records(days: int = 80, offset: float = 0.0) -> list[dict[str, object]]:
    dates = pd.date_range("2025-01-01", periods=days, freq="D")
    return [
        {
            "datetime": date.isoformat(),
            "open": 10.0 + offset + index * 0.1,
            "high": 10.8 + offset + index * 0.1,
            "low": 9.5 + offset + index * 0.1,
            "close": 10.3 + offset + index * 0.1,
            "vol": 1000.0 + index,
            "amount": 10000.0 + index * 100,
        }
        for index, date in enumerate(dates)
    ]


def test_server_ping_dispatches_and_normalizes_latency(monkeypatch):
    monkeypatch.setattr(advanced, "ping_mac_all", lambda timeout: [("1.2.3.4", 0.012)])

    rows = ServerService().ping("mac", timeout=1.0)

    assert rows == [{"host": "1.2.3.4", "latency_ms": 12.0, "rank": 1}]


def test_company_section_resolves_name_and_reads_all_chunks():
    class Client(ContextClient):
        calls: list[tuple[int, int]] = []

        def get_company_info_category(self, market, code):
            return pd.DataFrame(
                [{"name": "公司大事", "filename": "600519.txt", "start": 100, "length": 40000}]
            )

        def get_company_info_content(self, market, code, filename, offset, length):
            self.calls.append((offset, length))
            return f"chunk-{offset}"

    client = Client()
    output = CompanyService(lambda: client).get_section("SH", "600519", "公司大事")

    assert client.calls == [(100, 30720), (30820, 9280)]
    assert output["content"] == "chunk-100chunk-30820"
    assert output["byte_length"] == 40000


def test_sina_report_validates_and_delegates():
    class Sina:
        def get_financial_report(self, code, report_type, *, num):
            return pd.DataFrame([{"报告期": "2025-12-31", "净利润": 123.0}])

    frame = ExternalDataService(sina_factory=Sina).sina_report("600519", "lrb", 4)

    assert frame.iloc[0]["净利润"] == 123.0


def test_write_path_rejects_escape(tmp_path):
    with pytest.raises(ValueError, match="写入路径必须位于"):
        resolve_write_path(tmp_path.parent / "outside", tmp_path)


def test_announcement_download_writes_only_inside_allowed_root(tmp_path, monkeypatch):
    monkeypatch.setenv("EASY_TDX_MCP_WRITE_ROOT", str(tmp_path))

    class Cninfo:
        def download_pdf(self, announcement, dest_dir, *, filename=None):
            target = Path(dest_dir) / (filename or "report.PDF")
            target.write_bytes(b"%PDF-test")
            return str(target.resolve())

    output = ExternalDataService(cninfo_factory=Cninfo).download_announcement(
        {"pdf_url": "https://example.invalid/report.pdf"},
        str(tmp_path / "downloads"),
        tmp_path,
        filename="report.PDF",
    )

    assert Path(output).read_bytes() == b"%PDF-test"


def test_factor_cross_section_report_and_rebalance():
    data = {
        f"code{i}": _price_records(80, offset=float(i))
        for i in range(6)
    }
    service = AnalysisService()

    cross = service.factor_cross_section(data, ["momentum_20d"], None, 5)
    factor_rows = cross["factor_data"].to_dict(orient="records")
    return_rows = cross["forward_returns"].to_dict(orient="records")
    report = service.factor_report(
        factor_rows, return_rows, "momentum_20d", "forward_5d", 3, "pearson", 3
    )
    portfolio = service.rebalance(
        data, "equal", "momentum_20d", 2, "M", 100000.0, 0.0003, 0.001, None, None
    )

    assert len(factor_rows) == 480
    assert "ic_mean" in report["report"]
    assert len(report["decay"]) == 3
    assert not portfolio.equity_curve.empty
    assert "total_return" in portfolio.performance


def test_multi_level_chanlun_returns_both_levels():
    records = _price_records(80)

    output = AnalysisService().multi_level_chanlun(
        "SH600519", "DAILY", records, "30MIN", records
    )

    assert output["high"]["code"] == "SH600519"
    assert output["low"]["frequency"] == "30MIN"
    assert "last_high_bi_low_level_structure" in output


def test_realtime_sampling_is_bounded_and_collects_events():
    class Client(ContextClient):
        def get_stock_quotes(self, stocks, fields=None):
            return pd.DataFrame(
                [{"market": 0, "code": "000001", "close": 12.3, "vol": 1000, "name": "平安银行"}]
            )

    events = RealtimeService(lambda: Client()).sample(
        [{"market": "SZ", "code": "000001"}], 1, 0.1, True
    )

    assert len(events) == 1
    assert events[0].code == "000001"
    assert events[0].price == 12.3


def test_offline_sync_daily_writes_inside_allowed_root(tmp_path, monkeypatch):
    monkeypatch.setenv("EASY_TDX_MCP_WRITE_ROOT", str(tmp_path))

    class Client(ContextClient):
        def get_security_bars(self, market, code, category, start, count):
            if start:
                return pd.DataFrame()
            return pd.DataFrame(
                [
                    {
                        "date": pd.Timestamp("2025-01-02"),
                        "open": 10.0,
                        "high": 11.0,
                        "low": 9.0,
                        "close": 10.5,
                        "vol": 1000.0,
                        "amount": 10000.0,
                    }
                ]
            )

    vipdoc = tmp_path / "vipdoc"
    output = OfflineSyncService(lambda: Client()).sync_daily(
        "SZ", "000001", str(vipdoc), tmp_path
    )

    target = Path(output["file"])
    assert output["written"] == 1
    assert target.is_file()
    assert target.stat().st_size == 32
