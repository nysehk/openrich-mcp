from __future__ import annotations

import pandas as pd

from easy_tdx_mcp.serialization import jsonable
from easy_tdx_mcp.server import CLIENT_TOOL_NAMES, OFFLINE_TOOL_NAMES, mcp


def test_self_contained_client_surface_is_exposed_as_distinct_tools():
    names = {tool.name for tool in mcp._tool_manager.list_tools()}

    assert len(CLIENT_TOOL_NAMES) == 67
    assert "market_get_stock_kline" in names
    assert "standard_get_xdxr_info" in names
    assert "extended_goods_transaction_all" in names
    assert "extended_standard_get_markets" in names
    assert "extended_standard_get_history_instrument_bars_range" in names
    assert "analysis_compute_indicators" in names
    assert "analysis_chanlun" in names
    assert "backtest_run_builtin_strategy" in names
    assert len(OFFLINE_TOOL_NAMES) == 18
    assert "offline_read_daily_bars" in names
    assert "server_ping" in names
    assert "company_get_section" in names
    assert "sina_get_financial_report" in names
    assert "analysis_chanlun_multi_level" in names
    assert "factor_compute_cross_section" in names
    assert "factor_analyze" in names
    assert "portfolio_run_rebalance" in names
    assert "realtime_sample_quotes" in names
    assert "offline_sync_daily" in names
    assert "offline_sync_market_daily" in names


def test_generated_client_tool_has_only_llm_arguments_object():
    tool = next(
        tool for tool in mcp._tool_manager.list_tools() if tool.name == "market_get_stock_kline"
    )

    assert set(tool.parameters["properties"]) == {"arguments"}
    assert tool.parameters["required"] == ["arguments"]
    assert "get_stock_kline" in tool.description


def test_jsonable_converts_dataframe_nan_and_timestamp():
    frame = pd.DataFrame([{"datetime": pd.Timestamp("2026-08-18"), "value": float("nan")}])

    assert jsonable(frame) == [{"datetime": "2026-08-18T00:00:00", "value": None}]


def test_write_tools_are_not_marked_read_only():
    tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}

    for name in (
        "announcement_download_pdf",
        "offline_sync_daily",
        "offline_sync_market_daily",
    ):
        assert tools[name].annotations.readOnlyHint is False
        assert tools[name].annotations.destructiveHint is False
