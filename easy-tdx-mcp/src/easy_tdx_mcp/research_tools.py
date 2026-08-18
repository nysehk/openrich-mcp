from __future__ import annotations

from typing import Any

import pandas as pd
from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.strategies import get_registry
from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.factor import FactorEngine
from easy_tdx.factor.builtin import list_factors
from easy_tdx.indicator import compute_indicators, list_indicators
from easy_tdx.portfolio.optimizer import get_optimizer
from easy_tdx.portfolio.risk import RiskModel
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .response import result


COMPUTE_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def _frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(records)
    if frame.empty:
        raise ValueError("records 至少需要一条 OHLCV 数据")
    if "datetime" in frame:
        frame["datetime"] = pd.to_datetime(frame["datetime"])
    elif "date" in frame:
        frame["date"] = pd.to_datetime(frame["date"])
    return frame


def register_research_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="analysis_compute_indicators",
        description=(
            "对调用方提供的 OHLCV records 计算一个或多个内置技术指标。"
            "适合已有 K 线时避免再次联网；indicators 例如 MACD、KDJ、RSI、BOLL。"
            "params 按指标名覆盖参数；tail 控制只返回末尾 N 行。"
        ),
        annotations=COMPUTE_ONLY,
        structured_output=True,
    )
    def analysis_compute_indicators(
        records: list[dict[str, Any]],
        indicators: list[str],
        params: dict[str, dict[str, int | float]] | None = None,
        keep_ohlcv: bool = True,
        tail: int | None = None,
    ) -> dict[str, Any]:
        data = compute_indicators(
            _frame(records), indicators, params=params, keep_ohlcv=keep_ohlcv, tail=tail
        )
        return result(data, source="computed", request={"indicators": indicators, "params": params})

    @mcp.tool(
        name="analysis_chanlun",
        description=(
            "对 OHLCV records 执行完整缠论管道：K线合并、分型、笔、中枢、线段、"
            "买卖点和背驰。frequency 使用 DAILY、30MIN 等；结果是研究结构，不构成交易建议。"
        ),
        annotations=COMPUTE_ONLY,
        structured_output=True,
    )
    def analysis_chanlun(
        records: list[dict[str, Any]], code: str = "", frequency: str = "DAILY"
    ) -> dict[str, Any]:
        analysed = ChanlunAnalyser(code=code, frequency=frequency).process_klines(_frame(records))
        return result(analysed, source="computed", request={"code": code, "frequency": frequency})

    @mcp.tool(
        name="backtest_run_builtin_strategy",
        description=(
            "在调用方提供的历史 OHLCV records 上运行一个内置策略，返回 19 项绩效、"
            "权益曲线、成交与持仓。先读取 resource://easy-tdx/strategies 获取策略名和参数。"
            "cash、费率和滑点均为研究假设，不能代表未来收益。"
        ),
        annotations=COMPUTE_ONLY,
        structured_output=True,
    )
    def backtest_run_builtin_strategy(
        records: list[dict[str, Any]],
        strategy: str,
        strategy_params: dict[str, Any] | None = None,
        cash: float = 100000.0,
        commission: float = 0.0003,
        min_commission: float = 5.0,
        stamp_tax: float = 0.001,
        slippage: float = 0.0,
        execution: str = "next_open",
        warmup_bars: int = 0,
    ) -> dict[str, Any]:
        entry = get_registry().get(strategy)
        strategy_instance = entry.build(strategy_params)
        engine = BacktestEngine(
            strategy_instance,
            cash=cash,
            commission=commission,
            min_commission=min_commission,
            stamp_tax=stamp_tax,
            slippage=slippage,
            execution=execution,
            warmup_bars=warmup_bars,
        )
        data = engine.run(_frame(records))
        return result(
            data,
            source="computed",
            request={"strategy": strategy, "strategy_params": strategy_params, "cash": cash},
        )

    @mcp.tool(
        name="factor_compute",
        description=(
            "对单个标的 OHLCV records 计算一个或多个内置因子。"
            "factors 使用 resource://easy-tdx/factors 中的名称；返回逐日因子值。"
        ),
        annotations=COMPUTE_ONLY,
        structured_output=True,
    )
    def factor_compute(
        records: list[dict[str, Any]], factors: list[str]
    ) -> dict[str, Any]:
        data = FactorEngine().compute_single(_frame(records), factors)
        return result(data, source="computed", request={"factors": factors})

    @mcp.tool(
        name="portfolio_optimize_weights",
        description=(
            "根据包含 code、score（风险平价可另含 volatility）的因子评分记录生成组合权重。"
            "optimizer 支持 equal、factor_weighted、risk_parity、mean_variance；n_stocks 限制入选数量。"
        ),
        annotations=COMPUTE_ONLY,
        structured_output=True,
    )
    def portfolio_optimize_weights(
        factor_scores: list[dict[str, Any]],
        optimizer: str = "equal",
        n_stocks: int = 50,
    ) -> dict[str, Any]:
        data = get_optimizer(optimizer).optimize(pd.DataFrame(factor_scores), n_stocks=n_stocks)
        return result(
            data, source="computed", request={"optimizer": optimizer, "n_stocks": n_stocks}
        )

    @mcp.tool(
        name="portfolio_estimate_risk",
        description=(
            "从收益率矩阵 records 估计协方差并计算给定 weights 的组合风险。"
            "每列为一个 code，method 支持 sample、ewma 或 shrinkage。"
        ),
        annotations=COMPUTE_ONLY,
        structured_output=True,
    )
    def portfolio_estimate_risk(
        return_records: list[dict[str, Any]],
        weights: dict[str, float],
        method: str = "shrinkage",
        window: int = 60,
        shrinkage_intensity: float = 0.5,
    ) -> dict[str, Any]:
        model = RiskModel()
        covariance = model.estimate_covariance(
            pd.DataFrame(return_records),
            method=method,
            window=window,
            shrinkage_intensity=shrinkage_intensity,
        )
        return result(
            {"covariance": covariance, "risk": model.portfolio_risk(weights, covariance)},
            source="computed",
            request={"weights": weights, "method": method, "window": window},
        )

    @mcp.resource(
        "resource://easy-tdx/indicators",
        name="easy_tdx_indicator_catalog",
        description="34 个内置技术指标的输入列、输出列、默认参数和中文说明。",
        mime_type="application/json",
    )
    def indicator_catalog() -> list[dict[str, object]]:
        return list_indicators()

    @mcp.resource(
        "resource://easy-tdx/strategies",
        name="easy_tdx_strategy_catalog",
        description="内置回测策略、用途、参数 schema 与推荐参数网格。",
        mime_type="application/json",
    )
    def strategy_catalog() -> list[dict[str, Any]]:
        return [entry.to_schema() for entry in get_registry().all()]

    @mcp.resource(
        "resource://easy-tdx/factors",
        name="easy_tdx_factor_catalog",
        description="内置动量、质量、技术、估值、波动、成交量和缠论因子目录。",
        mime_type="application/json",
    )
    def factor_catalog() -> list[dict[str, Any]]:
        return list_factors()
