from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import re
from typing import Any, Callable, Literal

import pandas as pd

from easy_tdx import KlineCategory, MacClient, Market, TdxClient
from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.multi_level import MultiLevelAnalyser
from easy_tdx.cninfo import CninfoClient
from easy_tdx.ex.client import ExTdxClient
from easy_tdx.factor import FactorAnalyzer, FactorEngine
from easy_tdx.models.bar import SecurityBar
from easy_tdx.offline import append_daily_bars, find_daily_bar_file, get_last_bar_date
from easy_tdx.offline.daily_bar import _SECURITY_COEFFICIENTS, _detect_security_type
from easy_tdx.offline.paths import resolve_vipdoc
from easy_tdx.portfolio import RebalanceEngine
from easy_tdx.portfolio.optimizer import get_optimizer
from easy_tdx.realtime import EventBus, RealtimeDataFeed
from easy_tdx.sina import SinaClient
from easy_tdx.transport.sync import ping_all, ping_mac_all


ProtocolName = Literal["standard", "mac", "extended"]


def frames_by_symbol(data: dict[str, list[dict[str, Any]]]) -> dict[str, pd.DataFrame]:
    if not data:
        raise ValueError("data 至少需要一个标的")
    frames: dict[str, pd.DataFrame] = {}
    for symbol, records in data.items():
        if not records:
            raise ValueError(f"{symbol} 的 records 不能为空")
        frame = pd.DataFrame(records)
        if "datetime" not in frame and "date" in frame:
            frame = frame.rename(columns={"date": "datetime"})
        if "datetime" not in frame:
            raise ValueError(f"{symbol} 缺少 datetime/date 列")
        frame["datetime"] = pd.to_datetime(frame["datetime"])
        frames[symbol] = frame.sort_values("datetime").reset_index(drop=True)
    return frames


def resolve_write_path(path: str | os.PathLike[str], default_root: Path) -> Path:
    root = Path(os.environ.get("EASY_TDX_MCP_WRITE_ROOT", default_root)).resolve()
    target = Path(path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"写入路径必须位于 {root}；如需其他目录，请先设置 EASY_TDX_MCP_WRITE_ROOT"
        ) from exc
    return target


class ServerService:
    def ping(self, protocol: ProtocolName, timeout: float = 3.0) -> list[dict[str, Any]]:
        if not 0.1 <= timeout <= 10:
            raise ValueError("timeout 必须在 0.1 到 10 秒之间")
        if protocol == "standard":
            rows = ping_all(timeout=timeout)
        elif protocol == "mac":
            rows = ping_mac_all(timeout=timeout)
        else:
            rows = ExTdxClient.ping_all(timeout=timeout)
        return [
            {"host": host, "latency_ms": round(latency * 1000, 3), "rank": index + 1}
            for index, (host, latency) in enumerate(rows)
        ]


class CompanyService:
    def __init__(self, client_factory: Callable[[], Any] | None = None) -> None:
        self.client_factory = client_factory

    def _client_factories(self) -> list[Callable[[], Any]]:
        if self.client_factory is not None:
            return [self.client_factory]
        ranked = ping_all(timeout=1.5)
        return [lambda host=host: TdxClient(host, timeout=5.0) for host, _ in ranked[:8]]

    def get_section(self, market: str, code: str, section: str) -> dict[str, Any]:
        if market.upper() not in Market.__members__:
            raise ValueError("market 必须是 SH、SZ 或 BJ")
        if not re.fullmatch(r"\d{6}", code):
            raise ValueError("code 必须是 6 位数字")
        if not section or "." in section:
            raise ValueError("section 必须是 F10 板块名称，而不是文件名")
        market_enum = Market[market.upper()]
        available_names: set[str] = set()
        last_error: Exception | None = None
        for factory in self._client_factories():
            try:
                with factory() as client:
                    catalog = client.get_company_info_category(market_enum, code)
                    if not catalog.empty:
                        available_names.update(str(name) for name in catalog["name"].tolist())
                    matched = (
                        catalog.loc[catalog["name"] == section]
                        if not catalog.empty
                        else catalog
                    )
                    if matched.empty:
                        continue
                    row = matched.iloc[0]
                    filename = str(row["filename"])
                    start = int(row["start"])
                    length = int(row["length"])
                    parts: list[str] = []
                    for offset in range(start, start + length, 30720):
                        size = min(30720, start + length - offset)
                        chunk = client.get_company_info_content(
                            market_enum, code, filename, offset, size
                        )
                        if not chunk:
                            break
                        parts.append(chunk)
                    return {
                        "market": market.upper(),
                        "code": code,
                        "section": section,
                        "filename": filename,
                        "byte_length": length,
                        "content": "".join(parts),
                    }
            except Exception as exc:
                last_error = exc
                continue
        suffix = f"；最后错误: {type(last_error).__name__}" if last_error else ""
        raise ValueError(
            f"未找到板块 {section!r}；已尝试多个服务器；"
            f"可用板块: {sorted(available_names)}{suffix}"
        )


class ExternalDataService:
    def __init__(
        self,
        cninfo_factory: Callable[..., Any] = CninfoClient,
        sina_factory: Callable[..., Any] = SinaClient,
    ) -> None:
        self.cninfo_factory = cninfo_factory
        self.sina_factory = sina_factory

    def sina_report(self, code: str, report_type: str, num: int) -> pd.DataFrame:
        if not re.fullmatch(r"\d{6}", code):
            raise ValueError("code 必须是 6 位数字")
        if not 1 <= num <= 40:
            raise ValueError("num 必须在 1 到 40 之间")
        return self.sina_factory().get_financial_report(code, report_type, num=num)

    def download_announcement(
        self,
        announcement: dict[str, Any],
        destination: str,
        default_root: Path,
        filename: str | None = None,
    ) -> str:
        target_dir = resolve_write_path(destination, default_root)
        target_dir.mkdir(parents=True, exist_ok=True)
        if filename is not None and (Path(filename).name != filename or not filename):
            raise ValueError("filename 只能是文件名，不能包含目录")
        return self.cninfo_factory().download_pdf(
            pd.Series(announcement), target_dir, filename=filename
        )


class AnalysisService:
    def multi_level_chanlun(
        self,
        code: str,
        high_frequency: str,
        high_records: list[dict[str, Any]],
        low_frequency: str,
        low_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        frames = frames_by_symbol({"high": high_records, "low": low_records})
        analyser = MultiLevelAnalyser()
        analyser.add_level("high", ChanlunAnalyser(code, high_frequency))
        analyser.add_level("low", ChanlunAnalyser(code, low_frequency))
        high_result = analyser.process("high", frames["high"])
        low_result = analyser.process("low", frames["low"])
        structure = (
            analyser.query_low_level_qs("high", "low", high_result.bis[-1])
            if high_result.bis
            else None
        )
        return {
            "high": high_result.to_dict(),
            "low": low_result.to_dict(),
            "last_high_bi_low_level_structure": structure,
        }

    def factor_cross_section(
        self,
        data: dict[str, list[dict[str, Any]]],
        factors: list[str],
        date: int | None,
        forward_period: int,
    ) -> dict[str, Any]:
        if not factors:
            raise ValueError("factors 不能为空")
        if not 1 <= forward_period <= 252:
            raise ValueError("forward_period 必须在 1 到 252 之间")
        frames = frames_by_symbol(data)
        engine = FactorEngine()
        factor_data = (
            engine.compute_cross_section(frames, factors)
            if date is None
            else engine.compute_cross_section(frames, factors, date=date)
        )
        returns = engine.compute_forward_returns(frames, period=forward_period)
        return {"factor_data": factor_data, "forward_returns": returns}

    def factor_report(
        self,
        factor_data: list[dict[str, Any]],
        return_data: list[dict[str, Any]],
        factor_col: str,
        return_col: str,
        n_quantiles: int,
        method: str,
        max_lag: int,
    ) -> dict[str, Any]:
        if not 2 <= n_quantiles <= 20:
            raise ValueError("n_quantiles 必须在 2 到 20 之间")
        if method not in {"pearson", "spearman"}:
            raise ValueError("method 必须是 pearson 或 spearman")
        analyzer = FactorAnalyzer(
            pd.DataFrame(factor_data),
            pd.DataFrame(return_data),
            factor_col=factor_col,
            return_col=return_col,
            n_quantiles=n_quantiles,
        )
        ic = analyzer.compute_ic(method=method)
        quantiles = analyzer.compute_quantile_returns()
        quantile_means = quantiles.mean()
        quantile_returns = {
            str(name): float(value) for name, value in quantile_means.items()
        }
        ic_mean = float(ic.mean()) if len(ic) else 0.0
        ic_std = float(ic.std()) if len(ic) > 1 else 0.0
        decay_values: list[float] = []
        for lag in range(1, max_lag + 1):
            autocorr = ic.autocorr(lag=lag) if lag < len(ic) else 0.0
            decay_values.append(float(autocorr) if pd.notna(autocorr) else 0.0)
        decay = pd.DataFrame(
            {"lag": list(range(1, max_lag + 1)), "autocorr": decay_values}
        )
        return {
            "report": {
                "name": factor_col,
                "ic_mean": ic_mean,
                "ic_std": ic_std,
                "ir": ic_mean / ic_std if ic_std > 0 else 0.0,
                "ic_positive_rate": float((ic > 0).mean()) if len(ic) else 0.0,
                "quantile_returns": quantile_returns,
                "top_minus_bottom": (
                    quantile_returns.get(f"q{n_quantiles}", 0.0)
                    - quantile_returns.get("q1", 0.0)
                ),
                "turnover_rate": analyzer.compute_turnover(),
                "autocorr": float(ic.autocorr(lag=1)) if len(ic) > 1 else 0.0,
            },
            "ic": ic,
            "quantile_returns": quantiles,
            "decay": decay,
            "turnover": analyzer.compute_turnover(),
        }

    def rebalance(
        self,
        data: dict[str, list[dict[str, Any]]],
        optimizer: str,
        factor_name: str,
        n_stocks: int,
        rebalance_freq: str,
        cash: float,
        commission: float,
        slippage: float,
        start_date: int | None,
        end_date: int | None,
    ) -> Any:
        if rebalance_freq not in {"W", "M", "Q"}:
            raise ValueError("rebalance_freq 必须是 W、M 或 Q")
        if not 1 <= n_stocks <= 500:
            raise ValueError("n_stocks 必须在 1 到 500 之间")
        engine = RebalanceEngine(
            get_optimizer(optimizer),
            factor_name=factor_name,
            n_stocks=n_stocks,
            rebalance_freq=rebalance_freq,
            commission=commission,
            slippage=slippage,
            cash=cash,
        )
        return engine.run(frames_by_symbol(data), start_date=start_date, end_date=end_date)


class RealtimeService:
    def __init__(self, client_factory: Callable[[], Any] = MacClient.from_best_host) -> None:
        self.client_factory = client_factory

    def sample(
        self,
        symbols: list[dict[str, str]],
        iterations: int,
        interval: float,
        dedup: bool,
    ) -> list[Any]:
        if not 1 <= iterations <= 10:
            raise ValueError("iterations 必须在 1 到 10 之间")
        if not 0.1 <= interval <= 5:
            raise ValueError("interval 必须在 0.1 到 5 秒之间")
        parsed: list[tuple[int, str]] = []
        for item in symbols:
            market = item.get("market", "").upper()
            code = item.get("code", "")
            if market not in Market.__members__ or not re.fullmatch(r"\d{6}", code):
                raise ValueError(f"无效标的: {item}")
            parsed.append((int(Market[market]), code))
        events: list[Any] = []
        bus = EventBus()
        bus.subscribe_all(events.append)
        feed = RealtimeDataFeed(
            bus, parsed, interval=interval, dedup=dedup, sessions=()
        )
        with self.client_factory() as client:
            feed.run_sync(client, max_iterations=iterations)
        return events


class OfflineSyncService:
    def __init__(self, client_factory: Callable[[], Any] = TdxClient.from_best_host) -> None:
        self.client_factory = client_factory

    @staticmethod
    def _is_index(market: Market, code: str) -> bool:
        return code[:2] in ({"00", "88", "99"} if market is Market.SH else {"39"})

    @staticmethod
    def _to_bars(frame: pd.DataFrame) -> list[SecurityBar]:
        bars: list[SecurityBar] = []
        for row in frame.itertuples():
            dt = getattr(row, "date", None) or getattr(row, "datetime")
            dt = pd.Timestamp(dt)
            bars.append(
                SecurityBar(
                    open=float(row.open), close=float(row.close), high=float(row.high),
                    low=float(row.low), vol=float(row.vol), amount=float(row.amount),
                    year=dt.year, month=dt.month, day=dt.day, hour=0, minute=0,
                )
            )
        return bars

    def _sync_file(self, client: Any, filepath: Path) -> dict[str, Any]:
        name = filepath.name.lower()
        market = Market.SH if name.startswith("sh") else Market.SZ
        code = name[2:8]
        is_index = self._is_index(market, code)
        fetch = client.get_index_bars if is_index else client.get_security_bars
        need_full = get_last_bar_date(filepath) is None
        frames: list[pd.DataFrame] = []
        for page in range(50 if need_full else 1):
            frame = fetch(market, code, KlineCategory.DAY, page * 800, 800)
            if frame.empty:
                break
            frames.append(frame)
            if len(frame) < 800:
                break
        bars = self._to_bars(pd.concat(frames, ignore_index=True)) if frames else []
        sec_type = _detect_security_type(filepath.name)
        price_coeff, vol_coeff = _SECURITY_COEFFICIENTS.get(sec_type, (0.01, 0.01))
        written = append_daily_bars(filepath, bars, price_coeff, vol_coeff) if bars else 0
        return {"file": str(filepath), "market": market.name, "code": code, "written": written}

    def sync_daily(
        self, market: str, code: str, vipdoc: str, default_root: Path
    ) -> dict[str, Any]:
        if market.upper() not in {"SH", "SZ"}:
            raise ValueError("market 必须是 SH 或 SZ")
        if not re.fullmatch(r"\d{6}", code):
            raise ValueError("code 必须是 6 位数字")
        market_enum = Market[market.upper()]
        vipdoc_path = resolve_write_path(vipdoc, default_root)
        vipdoc_path.mkdir(parents=True, exist_ok=True)
        filepath = find_daily_bar_file(market_enum, code, vipdoc_path)
        resolve_write_path(filepath, default_root)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        if not filepath.exists():
            filepath.touch()
        with self.client_factory() as client:
            return self._sync_file(client, filepath)

    def sync_market(
        self, vipdoc: str, start: int, limit: int, default_root: Path
    ) -> dict[str, Any]:
        if start < 0 or not 1 <= limit <= 500:
            raise ValueError("start 必须 >=0，limit 必须在 1 到 500 之间")
        vipdoc_path = resolve_write_path(resolve_vipdoc(vipdoc), default_root)
        files = sorted(
            path
            for exchange in ("sh", "sz")
            for path in (vipdoc_path / exchange / "lday").glob("*.day")
        )
        selected = files[start : start + limit]
        results: list[dict[str, Any]] = []
        with self.client_factory() as client:
            for filepath in selected:
                try:
                    results.append({"status": "ok", **self._sync_file(client, filepath)})
                except Exception as exc:
                    results.append(
                        {"status": "error", "file": str(filepath), "error": type(exc).__name__}
                    )
        return {
            "total_files": len(files),
            "start": start,
            "processed": len(selected),
            "next_start": start + len(selected) if start + len(selected) < len(files) else None,
            "results": results,
            "completed_at": datetime.now(UTC).isoformat(),
        }
