from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .advanced_service import (
    AnalysisService,
    CompanyService,
    ExternalDataService,
    OfflineSyncService,
    ProtocolName,
    RealtimeService,
    ServerService,
)
from .response import result


READ_ONLY_NETWORK = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
COMPUTE_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
WRITES_FILES = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
)


def register_advanced_tools(mcp: FastMCP, state_root: Path) -> list[str]:
    server_service = ServerService()
    company_service = CompanyService()
    external_service = ExternalDataService()
    analysis_service = AnalysisService()
    realtime_service = RealtimeService()
    offline_service = OfflineSyncService()

    @mcp.tool(
        name="server_ping",
        description=(
            "测试通达信服务器延迟并按速度排序。protocol=mac 用于推荐 A 股协议，"
            "standard 用于传统 A 股协议，extended 用于港股/美股/期货 7727 协议。"
        ),
        annotations=READ_ONLY_NETWORK,
        structured_output=True,
    )
    def server_ping(protocol: ProtocolName = "mac", timeout: float = 3.0) -> dict[str, Any]:
        return result(
            server_service.ping(protocol, timeout),
            source=f"tdx_{protocol}",
            request={"protocol": protocol, "timeout": timeout},
        )

    @mcp.tool(
        name="company_get_section",
        description=(
            "按中文 F10 板块名读取完整正文，例如公司概况、公司大事。工具先查询目录，"
            "再按 30720 字节安全分块读取完整内容；无需模型处理 filename/offset/length。"
        ),
        annotations=READ_ONLY_NETWORK,
        structured_output=True,
    )
    def company_get_section(market: str, code: str, section: str) -> dict[str, Any]:
        return result(
            company_service.get_section(market, code, section),
            source="tdx_standard",
            request={"market": market, "code": code, "section": section},
        )

    @mcp.tool(
        name="sina_get_financial_report",
        description=(
            "从新浪财经获取多期财报三表。report_type 使用 lrb（利润表）、fzb"
            "（资产负债表）或 llb（现金流量表）；数值和同比均返回可计算数字。"
        ),
        annotations=READ_ONLY_NETWORK,
        structured_output=True,
    )
    def sina_get_financial_report(
        code: str, report_type: str = "lrb", num: int = 8
    ) -> dict[str, Any]:
        return result(
            external_service.sina_report(code, report_type, num),
            source="sina",
            request={"code": code, "report_type": report_type, "num": num},
        )

    @mcp.tool(
        name="announcement_download_pdf",
        description=(
            "下载 announcement 工具返回的单条公告 PDF。announcement 至少包含 pdf_url、"
            "announcement_id、announcement_time；写入目录必须位于 EASY_TDX_MCP_WRITE_ROOT。"
        ),
        annotations=WRITES_FILES,
        structured_output=True,
    )
    def announcement_download_pdf(
        announcement: dict[str, Any],
        destination: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        dest = destination or str(state_root / "downloads")
        path = external_service.download_announcement(
            announcement, dest, state_root, filename=filename
        )
        return result(
            {"path": path},
            source="cninfo",
            request={"destination": dest, "filename": filename},
        )

    @mcp.tool(
        name="analysis_chanlun_multi_level",
        description=(
            "对高级别和低级别两组 OHLCV K 线执行多级别缠论联立分析。返回两个级别的"
            "笔/中枢/买卖点/背驰，以及高级别最后一笔在低级别中的趋势、盘整和背驰条件。"
        ),
        annotations=COMPUTE_ONLY,
        structured_output=True,
    )
    def analysis_chanlun_multi_level(
        code: str,
        high_frequency: str,
        high_records: list[dict[str, Any]],
        low_frequency: str,
        low_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return result(
            analysis_service.multi_level_chanlun(
                code, high_frequency, high_records, low_frequency, low_records
            ),
            source="computed",
            request={
                "code": code,
                "high_frequency": high_frequency,
                "low_frequency": low_frequency,
            },
        )

    @mcp.tool(
        name="factor_compute_cross_section",
        description=(
            "对多标的历史 OHLCV 数据计算一个或多个截面因子，并同时计算指定周期的"
            "未来收益。data 是 code 到 records 的映射，用于后续 IC 和分层分析。"
        ),
        annotations=COMPUTE_ONLY,
        structured_output=True,
    )
    def factor_compute_cross_section(
        data: dict[str, list[dict[str, Any]]],
        factors: list[str],
        date: int | None = None,
        forward_period: int = 5,
    ) -> dict[str, Any]:
        return result(
            analysis_service.factor_cross_section(data, factors, date, forward_period),
            source="computed",
            request={"factors": factors, "date": date, "forward_period": forward_period},
        )

    @mcp.tool(
        name="factor_analyze",
        description=(
            "分析截面因子有效性，返回 IC/ICIR、正 IC 比例、分层收益、Top-Bottom、"
            "换手率、IC 衰减和自相关。factor_data 与 return_data 可直接使用截面计算结果。"
        ),
        annotations=COMPUTE_ONLY,
        structured_output=True,
    )
    def factor_analyze(
        factor_data: list[dict[str, Any]],
        return_data: list[dict[str, Any]],
        factor_col: str,
        return_col: str = "forward_5d",
        n_quantiles: int = 5,
        method: str = "pearson",
        max_lag: int = 10,
    ) -> dict[str, Any]:
        return result(
            analysis_service.factor_report(
                factor_data,
                return_data,
                factor_col,
                return_col,
                n_quantiles,
                method,
                max_lag,
            ),
            source="computed",
            request={
                "factor_col": factor_col,
                "return_col": return_col,
                "n_quantiles": n_quantiles,
                "method": method,
            },
        )

    @mcp.tool(
        name="portfolio_run_rebalance",
        description=(
            "对多标的历史 OHLCV 数据运行周/月/季度多期调仓。支持 equal、"
            "factor_weighted、risk_parity、mean_variance 优化器，返回调仓日、交易、"
            "权益曲线、持仓状态和组合绩效。"
        ),
        annotations=COMPUTE_ONLY,
        structured_output=True,
    )
    def portfolio_run_rebalance(
        data: dict[str, list[dict[str, Any]]],
        optimizer: str = "factor_weighted",
        factor_name: str = "momentum_20d",
        n_stocks: int = 50,
        rebalance_freq: str = "M",
        cash: float = 1_000_000,
        commission: float = 0.0003,
        slippage: float = 0.001,
        start_date: int | None = None,
        end_date: int | None = None,
    ) -> dict[str, Any]:
        output = analysis_service.rebalance(
            data, optimizer, factor_name, n_stocks, rebalance_freq, cash,
            commission, slippage, start_date, end_date
        )
        return result(
            output,
            source="computed",
            request={
                "optimizer": optimizer,
                "factor_name": factor_name,
                "n_stocks": n_stocks,
                "rebalance_freq": rebalance_freq,
            },
        )

    @mcp.tool(
        name="realtime_sample_quotes",
        description=(
            "通过 RealtimeDataFeed 有界轮询五档快照并返回 MarketEvent 列表。"
            "最多 80 个标的、10 轮、每轮间隔 0.1-5 秒；不会创建永久后台订阅。"
        ),
        annotations=READ_ONLY_NETWORK,
        structured_output=True,
    )
    def realtime_sample_quotes(
        symbols: list[dict[str, str]],
        iterations: int = 1,
        interval: float = 0.1,
        dedup: bool = True,
    ) -> dict[str, Any]:
        return result(
            realtime_service.sample(symbols, iterations, interval, dedup),
            source="tdx_mac_polling",
            request={
                "symbols": symbols,
                "iterations": iterations,
                "interval": interval,
                "dedup": dedup,
            },
        )

    @mcp.tool(
        name="offline_sync_daily",
        description=(
            "从 TDX 服务端增量同步单只股票或指数日线到本地 .day 文件。该工具会写文件；"
            "vipdoc 必须位于 EASY_TDX_MCP_WRITE_ROOT，建议关闭通达信后调用。"
        ),
        annotations=WRITES_FILES,
        structured_output=True,
    )
    def offline_sync_daily(market: str, code: str, vipdoc: str) -> dict[str, Any]:
        return result(
            offline_service.sync_daily(market, code, vipdoc, state_root),
            source="tdx_standard_to_local",
            request={"market": market, "code": code, "vipdoc": vipdoc},
        )

    @mcp.tool(
        name="offline_sync_market_daily",
        description=(
            "分页同步 vipdoc 内已有的沪深 .day 文件。start/limit 用于分批执行，"
            "单次最多 500 个文件并返回 next_start；会写文件且目录必须在允许写入根目录内。"
        ),
        annotations=WRITES_FILES,
        structured_output=True,
    )
    def offline_sync_market_daily(
        vipdoc: str, start: int = 0, limit: int = 100
    ) -> dict[str, Any]:
        return result(
            offline_service.sync_market(vipdoc, start, limit, state_root),
            source="tdx_standard_to_local",
            request={"vipdoc": vipdoc, "start": start, "limit": limit},
        )

    return [
        "server_ping", "company_get_section", "sina_get_financial_report",
        "announcement_download_pdf", "analysis_chanlun_multi_level",
        "factor_compute_cross_section", "factor_analyze", "portfolio_run_rebalance",
        "realtime_sample_quotes", "offline_sync_daily", "offline_sync_market_daily",
    ]
