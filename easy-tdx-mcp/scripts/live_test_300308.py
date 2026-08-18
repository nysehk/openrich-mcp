from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = ROOT / ".easy-tdx-state" / "live-test-300308"
VIPDOC = STATE_ROOT / "vipdoc"
DAILY_FILE = VIPDOC / "sz" / "lday" / "sz300308.day"
REPORT_PATH = ROOT / "reports" / "live-test-300308.json"


def synthetic_records(days: int = 180, offset: float = 0.0, slope: float = 0.08) -> list[dict[str, Any]]:
    start = datetime(2025, 1, 1)
    records: list[dict[str, Any]] = []
    for index in range(days):
        date = start + timedelta(days=index)
        wave = ((index % 12) - 6) * 0.07
        close = 30.0 + offset + index * slope + wave
        records.append(
            {
                "datetime": date.isoformat(),
                "open": close - 0.2,
                "high": close + 0.8,
                "low": close - 0.7,
                "close": close,
                "vol": 1_000_000 + index * 1000,
                "amount": (1_000_000 + index * 1000) * close,
            }
        )
    return records


RECORDS = synthetic_records()
MULTI_DATA = {
    code: synthetic_records(offset=float(index), slope=0.04 + index * 0.01)
    for index, code in enumerate(["300308", "000001", "600519", "600036", "000858", "002594"])
}
FACTOR_DATA = [
    {"date": 20250101 + day, "code": f"code{code}", "momentum_20d": code + day * 0.1}
    for day in range(6)
    for code in range(6)
]
RETURN_DATA = [
    {"date": 20250101 + day, "code": f"code{code}", "forward_5d": code * 0.01 + day * 0.001}
    for day in range(6)
    for code in range(6)
]


def dynamic_arguments() -> dict[str, dict[str, Any]]:
    sz = "SZ"
    code = "300308"
    hk = "HK_MAIN_BOARD"
    return {
        # Standard A-share protocol
        "standard_get_block_info": {"filename": "block_gn.dat"},
        "standard_get_company_info_category": {"market": sz, "code": code},
        "standard_get_company_info_content": {
            "market": sz, "code": code, "filename": "300308.txt", "offset": 0, "length": 512,
        },
        "standard_get_finance_info": {"market": sz, "code": code},
        "standard_get_financial_file_list": {},
        "standard_get_fund_flow": {"market": sz, "code": code},
        "standard_get_history_fund_flow": {"market": sz, "code": code, "start": 0, "count": 20},
        "standard_get_history_minute_time_data": {"market": sz, "code": code, "date": 20260818},
        "standard_get_history_transaction_data": {
            "market": sz, "code": code, "date": 20260818, "start": 0, "count": 20,
        },
        "standard_get_index_bars": {
            "market": sz, "code": "399001", "category": "DAY", "start": 0, "count": 20,
        },
        "standard_get_market_stat": {},
        "standard_get_minute_time_data": {"market": sz, "code": code},
        "standard_get_price_limits": {
            "market": sz, "code": code, "name": "中际旭创", "pre_close": 150.0,
        },
        "standard_get_security_bars": {
            "market": sz, "code": code, "category": "DAY", "start": 0, "count": 30,
        },
        "standard_get_security_count": {"market": sz},
        "standard_get_security_list": {"market": sz, "start": 0},
        "standard_get_security_list_all": {"pages": 1},
        "standard_get_security_quotes": {"stocks": [{"market": sz, "code": code}]},
        "standard_get_transaction_data": {"market": sz, "code": code, "start": 0, "count": 20},
        "standard_get_xdxr_info": {"market": sz, "code": code},
        # Recommended Mac A-share protocol
        "market_get_auction": {"market": sz, "code": code},
        "market_get_belong_board": {"market": sz, "code": code},
        "market_get_board_change_ranking": {
            "board_type": "HY", "days": 5, "top_n": 3, "ascending": False,
        },
        "market_get_board_list": {"board_type": "HY", "count": 5},
        "market_get_board_members": {"board_symbol": "881001", "count": 5},
        "market_get_board_ranking": {"board_type": "HY", "top_n": 3},
        "market_get_board_summary": {"board_symbol": "881001"},
        "market_get_capital_flow": {"market": sz, "code": code},
        "market_get_chart_sampling": {"market": sz, "code": code},
        "market_get_file_meta": {"filename": "gbbq"},
        "market_get_goods_list": {"market": hk, "start": 0, "count": 5},
        "market_get_kline_offset": {"offset": 0, "count": 5},
        "market_get_server_info": {},
        "market_get_stock_kline": {
            "market": sz, "code": code, "period": "DAILY", "count": 30, "adjust": "QFQ",
        },
        "market_get_stock_kline_with_indicators": {
            "market": sz, "code": code, "indicators": ["MACD", "KDJ", "RSI"],
            "period": "DAILY", "count": 20, "adjust": "QFQ",
        },
        "market_get_stock_quotes": {"stocks": [{"market": sz, "code": code}]},
        "market_get_stock_quotes_list": {"category": "CYB", "count": 5},
        "market_get_symbol_info": {"market": sz, "code": code},
        "market_get_tick_chart": {"market": sz, "code": code},
        "market_get_tick_charts": {"market": sz, "code": code, "days": 2},
        "market_get_transactions": {"market": sz, "code": code, "count": 20},
        "market_get_unusual": {"market": sz, "start": 0, "count": 10},
        # Mac extended protocol
        "extended_goods_chart_sampling": {"market": hk, "code": "00700"},
        "extended_goods_count": {"market": hk},
        "extended_goods_kline": {"market": hk, "code": "00700", "period": "DAILY", "count": 10},
        "extended_goods_list": {"market": hk, "start": 0, "count": 5},
        "extended_goods_quotes": {"stocks": [{"market": hk, "code": "00700"}]},
        "extended_goods_quotes_list": {"market": hk, "count": 5},
        "extended_goods_tick_chart": {"market": hk, "code": "00700"},
        "extended_goods_transaction": {"market": hk, "code": "00700", "count": 10},
        # Standard extended protocol
        "extended_standard_get_history_instrument_bars_range": {
            "market": hk, "code": "00700", "start_date": 20260801, "end_date": 20260818,
        },
        "extended_standard_get_history_minute_time_data": {
            "market": hk, "code": "00700", "date": 20260818,
        },
        "extended_standard_get_history_transaction_data": {
            "market": hk, "code": "00700", "date": 20260818, "count": 10,
        },
        "extended_standard_get_instrument_bars": {
            "category": "DAY", "market": hk, "code": "00700", "count": 10,
        },
        "extended_standard_get_instrument_count": {},
        "extended_standard_get_instrument_info": {"start": 0, "count": 5},
        "extended_standard_get_instrument_quote": {"market": hk, "code": "00700"},
        "extended_standard_get_instrument_quote_list": {
            "market": hk, "category": 4, "start": 0, "count": 5,
        },
        "extended_standard_get_markets": {},
        "extended_standard_get_minute_time_data": {"market": hk, "code": "00700"},
        "extended_standard_get_transaction_data": {"market": hk, "code": "00700", "count": 10},
    }


def direct_arguments() -> dict[str, dict[str, Any]]:
    return {
        "kline": {"market": "SZ", "code": "300308", "count": 30, "period": "DAILY", "adjust": "QFQ"},
        "quote": {"symbols": "SZ 300308"},
        "announcement": {"code": "300308", "count": 3, "page": 1},
        "analysis_compute_indicators": {
            "records": RECORDS, "indicators": ["MACD", "KDJ", "RSI", "ZHUOYAO"], "tail": 5,
        },
        "analysis_chanlun": {"records": RECORDS, "code": "SZ300308", "frequency": "DAILY"},
        "analysis_chanlun_multi_level": {
            "code": "SZ300308", "high_frequency": "DAILY", "high_records": RECORDS,
            "low_frequency": "30MIN", "low_records": RECORDS,
        },
        "backtest_run_builtin_strategy": {
            "records": RECORDS, "strategy": "ma_cross", "cash": 100000.0, "warmup_bars": 30,
        },
        "factor_compute": {"records": RECORDS, "factors": ["momentum_20d", "rsi_14"]},
        "factor_compute_cross_section": {"data": MULTI_DATA, "factors": ["momentum_20d"], "forward_period": 5},
        "factor_analyze": {
            "factor_data": FACTOR_DATA, "return_data": RETURN_DATA, "factor_col": "momentum_20d",
            "return_col": "forward_5d", "n_quantiles": 3, "method": "pearson", "max_lag": 3,
        },
        "portfolio_optimize_weights": {
            "factor_scores": [{"code": code, "score": index + 1.0} for index, code in enumerate(MULTI_DATA)],
            "optimizer": "factor_weighted", "n_stocks": 3,
        },
        "portfolio_estimate_risk": {
            "return_records": [
                {code: 0.001 * (index + 1) * ((day % 5) - 2) for index, code in enumerate(MULTI_DATA)}
                for day in range(80)
            ],
            "weights": {code: 1 / len(MULTI_DATA) for code in MULTI_DATA},
            "method": "shrinkage", "window": 60,
        },
        "portfolio_run_rebalance": {
            "data": MULTI_DATA, "optimizer": "equal", "factor_name": "momentum_20d",
            "n_stocks": 3, "rebalance_freq": "M", "cash": 100000.0,
        },
        "server_ping": {"protocol": "mac", "timeout": 1.0},
        "company_get_section": {"market": "SZ", "code": "300308", "section": "最新提示"},
        "sina_get_financial_report": {"code": "300308", "report_type": "lrb", "num": 2},
        "realtime_sample_quotes": {
            "symbols": [{"market": "SZ", "code": "300308"}], "iterations": 1,
            "interval": 0.1, "dedup": True,
        },
        "offline_sync_daily": {"market": "SZ", "code": "300308", "vipdoc": str(VIPDOC)},
        "offline_sync_market_daily": {"vipdoc": str(VIPDOC), "start": 0, "limit": 1},
        "offline_detect_tdx_home": {"arguments": {}},
        "offline_resolve_vipdoc": {"arguments": {"path": str(VIPDOC)}},
        "offline_find_daily_bar_file": {
            "arguments": {"market": "SZ", "code": "300308", "vipdoc": str(VIPDOC)},
        },
        "offline_find_5min_bar_file": {
            "arguments": {"market": "SZ", "code": "300308", "vipdoc": str(VIPDOC)},
        },
        "offline_find_lc1_bar_file": {
            "arguments": {"market": "SZ", "code": "300308", "vipdoc": str(VIPDOC)},
        },
        "offline_find_lc5_bar_file": {
            "arguments": {"market": "SZ", "code": "300308", "vipdoc": str(VIPDOC)},
        },
        "offline_read_daily_bars": {"arguments": {"filepath": str(DAILY_FILE)}},
        "offline_get_last_bar_date": {"arguments": {"filepath": str(DAILY_FILE)}},
    }


SKIPS = {
    "standard_get_financial_file": "可能下载较大的历史财报 ZIP；文件列表接口已测试",
    "standard_get_financial_records": "内部会下载并解析完整财报 ZIP；避免无界下载",
    "standard_get_report_file": "需要指定远端文件且可能返回大二进制",
    "market_download_file": "需要已知远端文件名且可能无界下载",
    "market_download_file_chunk": "需要 get_file_meta 返回的有效远端文件名和偏移",
    "extended_goods_transaction_all": "港股全天逐笔最高约 9 万条，避免无界 live 测试",
    "offline_read_5min_bars": "测试目录没有真实 .5 文件样本",
    "offline_read_lc_min_bars": "测试目录没有真实 .lc1/.lc5 文件样本",
    "offline_read_ex_daily_bars": "测试目录没有扩展市场 .day 文件样本",
    "offline_read_gbbq": "测试目录没有 gbbq 文件样本",
    "offline_read_history_financial": "测试目录没有 gpcw 财务文件样本",
    "offline_read_block_dat": "测试目录没有 block.dat 文件样本",
    "offline_read_customer_blocks": "测试目录没有自定义板块目录样本",
    "offline_get_last_5min_bar_datetime": "测试目录没有 .5 文件样本",
    "offline_get_last_ex_bar_date": "测试目录没有扩展市场 .day 文件样本",
    "offline_get_last_lc_min_bar_datetime": "测试目录没有 .lc 文件样本",
}


def unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and set(payload) == {"result"}:
        return payload["result"]
    return payload


def compact(payload: Any) -> dict[str, Any]:
    value = unwrap(payload)
    if not isinstance(value, dict):
        return {"type": type(value).__name__}
    data = value.get("data")
    summary: dict[str, Any] = {
        "status": value.get("status"),
        "source": value.get("source"),
    }
    if isinstance(data, list):
        summary["data_count"] = len(data)
        summary["sample"] = data[:1]
    elif isinstance(data, dict):
        summary["data_keys"] = sorted(data)[:20]
        if "path" in data:
            summary["path"] = data["path"]
    else:
        summary["data_type"] = type(data).__name__
    if value.get("error"):
        summary["error"] = value["error"]
    return summary


async def call_tool(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any],
    timeout: float,
) -> tuple[str, dict[str, Any]]:
    started = time.perf_counter()
    try:
        output = await asyncio.wait_for(session.call_tool(name, arguments), timeout=timeout)
        elapsed = round(time.perf_counter() - started, 3)
        if output.isError:
            text = " | ".join(getattr(item, "text", "") for item in output.content)
            return "FAIL", {"elapsed_seconds": elapsed, "error": text[:1000]}
        return "PASS", {
            "elapsed_seconds": elapsed,
            "summary": compact(output.structuredContent),
        }
    except asyncio.TimeoutError:
        return "FAIL", {"elapsed_seconds": timeout, "error": f"timeout after {timeout}s"}
    except Exception as exc:
        return "FAIL", {
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }


async def run(timeout: float) -> dict[str, Any]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "EASY_TDX_MCP_STATE_DIR": str(STATE_ROOT),
        "EASY_TDX_MCP_WRITE_ROOT": str(STATE_ROOT),
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "easy_tdx_mcp.server"],
        env=env,
    )
    report: dict[str, Any] = {
        "symbol": "SZ300308",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "results": {},
        "servers": {},
        "resources": {},
    }
    dynamic = dynamic_arguments()
    direct = direct_arguments()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            listed = await session.list_tools()
            resources = await session.list_resources()
            tool_names = sorted(tool.name for tool in listed.tools)
            report["server"] = initialized.serverInfo.name
            report["discovered_tools"] = len(tool_names)
            report["discovered_resources"] = len(resources.resources)

            for resource in resources.resources:
                try:
                    content = await session.read_resource(resource.uri)
                    report["resources"][str(resource.uri)] = {
                        "status": "PASS",
                        "content_blocks": len(content.contents),
                    }
                except Exception as exc:
                    report["resources"][str(resource.uri)] = {
                        "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"
                    }

            # Capture all three server pools explicitly.
            for protocol in ("mac", "standard", "extended"):
                status, detail = await call_tool(
                    session, "server_ping", {"protocol": protocol, "timeout": 1.0}, timeout
                )
                report["servers"][protocol] = {"status": status, **detail}
            ping_status = (
                "PASS"
                if all(item["status"] == "PASS" for item in report["servers"].values())
                else "FAIL"
            )
            report["results"]["server_ping"] = {
                "status": ping_status,
                "protocols": report["servers"],
            }

            ordered = [
                "market_get_stock_kline", "quote", "announcement",
                "offline_sync_daily", "offline_sync_market_daily",
            ] + [name for name in tool_names if name not in {
                "market_get_stock_kline", "quote", "announcement",
                "offline_sync_daily", "offline_sync_market_daily", "server_ping",
            }]

            announcement_record: dict[str, Any] | None = None
            for index, name in enumerate(ordered, 1):
                if name in SKIPS:
                    report["results"][name] = {"status": "SKIP", "reason": SKIPS[name]}
                    print(f"[{index}/{len(ordered)}] SKIP {name}: {SKIPS[name]}", flush=True)
                    continue
                if name == "announcement_download_pdf":
                    if announcement_record is None:
                        report["results"][name] = {
                            "status": "SKIP", "reason": "公告查询未返回可下载记录"
                        }
                        print(f"[{index}/{len(ordered)}] SKIP {name}: no announcement", flush=True)
                        continue
                    arguments = {
                        "announcement": announcement_record,
                        "destination": str(STATE_ROOT / "downloads"),
                    }
                elif name in dynamic:
                    arguments = {"arguments": dynamic[name]}
                elif name in direct:
                    arguments = direct[name]
                else:
                    report["results"][name] = {
                        "status": "SKIP", "reason": "没有安全、有限的 live fixture"
                    }
                    print(f"[{index}/{len(ordered)}] SKIP {name}: no fixture", flush=True)
                    continue

                status, detail = await call_tool(session, name, arguments, timeout)
                report["results"][name] = {"status": status, **detail}
                print(f"[{index}/{len(ordered)}] {status} {name} ({detail.get('elapsed_seconds', 0)}s)", flush=True)

                if name == "announcement" and status == "PASS":
                    # Run a direct lightweight lookup through the returned structured payload.
                    output = await asyncio.wait_for(session.call_tool(name, arguments), timeout=timeout)
                    payload = unwrap(output.structuredContent)
                    if isinstance(payload, dict):
                        records = payload.get("records") or payload.get("data") or []
                        if records:
                            announcement_record = records[0]

    counts = {status: 0 for status in ("PASS", "FAIL", "SKIP")}
    for item in report["results"].values():
        counts[item["status"]] += 1
    report["counts"] = counts
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), "utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Live-test all safe Easy TDX MCP tools for SZ300308")
    parser.add_argument("--timeout", type=float, default=45.0, help="per-tool timeout seconds")
    args = parser.parse_args()
    report = asyncio.run(run(args.timeout))
    print(json.dumps({"counts": report["counts"], "report": str(REPORT_PATH)}, ensure_ascii=False))
    if report["counts"]["FAIL"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
