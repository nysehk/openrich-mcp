from __future__ import annotations

from datetime import date
from enum import Enum
import inspect
from typing import Any, Callable

from easy_tdx import ExTdxClient, MacClient, MacExClient, TdxClient
from easy_tdx.mac.enums import (
    Adjust,
    BoardType,
    Category,
    ExMarket,
    FilterType,
    Period,
    SortOrder,
    SortType,
)
from easy_tdx.models.enums import KlineCategory, Market
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .response import result


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

_SKIP = {
    "close",
    "connect",
    "disconnect",
    "ensure_connected",
    "from_best_host",
    "ping_all",
    "reconnect_to",
}


def _enum(value: Any, enum_cls: type[Enum]) -> Any:
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        key = value.strip().upper()
        if key in enum_cls.__members__:
            return enum_cls[key]
        try:
            return enum_cls(int(value))
        except (TypeError, ValueError):
            pass
    return enum_cls(value)


def _convert(prefix: str, method: str, arguments: dict[str, Any]) -> dict[str, Any]:
    args = dict(arguments)
    if "market" in args:
        enum_cls = (
            ExMarket
            if prefix.startswith("extended") or method == "get_goods_list"
            else Market
        )
        args["market"] = _enum(args["market"], enum_cls)
    if "stocks" in args:
        enum_cls = ExMarket if prefix.startswith("extended") else Market
        args["stocks"] = [
            (_enum(item[0], enum_cls), str(item[1]))
            if isinstance(item, (list, tuple))
            else (_enum(item["market"], enum_cls), str(item["code"]))
            for item in args["stocks"]
        ]
    enum_params: dict[str, type[Enum]] = {
        "period": Period,
        "adjust": Adjust,
        "board_type": BoardType,
        "sort_type": SortType,
        "sort_order": SortOrder,
    }
    for name, enum_cls in enum_params.items():
        if name in args:
            args[name] = _enum(args[name], enum_cls)
    if method == "get_stock_quotes_list" and "category" in args:
        args["category"] = _enum(args["category"], Category)
    elif "category" in args:
        args["category"] = _enum(args["category"], KlineCategory)
    if "exclude_flags" in args and args["exclude_flags"] is not None:
        args["exclude_flags"] = [_enum(v, FilterType) for v in args["exclude_flags"]]
    if "query_date" in args and isinstance(args["query_date"], str):
        args["query_date"] = date.fromisoformat(args["query_date"])
    return args


def _description(prefix: str, method_name: str, method: Callable[..., Any]) -> str:
    signature = str(inspect.signature(method)).replace("self, ", "").replace("(self)", "()")
    first_line = (inspect.getdoc(method) or method_name).splitlines()[0]
    market_help = (
        " 扩展市场 market 可用名称如 HK_MAIN_BOARD、US_STOCK、SH_FUTURES。"
        if prefix.startswith("extended")
        else " A股 market 使用 SH、SZ 或 BJ。"
    )
    return (
        f"{first_line} 内置 fork 直接执行，不依赖 easy-tdx 第三方安装包。"
        f" 参数放入 arguments 对象，原方法签名：{method_name}{signature}。"
        f"{market_help}枚举参数优先使用大写名称；返回统一包含来源、时间戳和严格 JSON 数据。"
    )


def register_client_tools(mcp: FastMCP) -> list[str]:
    """Expose every public data method of the three synchronous fork clients."""
    registered: list[str] = []
    clients = [
        ("standard", "tdx_standard", TdxClient),
        ("market", "tdx_mac", MacClient),
        ("extended", "tdx_ex", MacExClient),
        ("extended_standard", "tdx_ex_standard", ExTdxClient),
    ]
    for prefix, source, client_cls in clients:
        for method_name, method in inspect.getmembers(client_cls, inspect.isfunction):
            if method_name.startswith("_") or method_name in _SKIP:
                continue
            tool_name = f"{prefix}_{method_name}"

            def make_invoke(
                selected_prefix: str,
                selected_source: str,
                selected_method: str,
                selected_client: type[Any],
            ) -> Callable[[dict[str, Any]], dict[str, Any]]:
                def invoke(arguments: dict[str, Any]) -> dict[str, Any]:
                    """Call a self-contained fork client method with named arguments."""
                    converted = _convert(selected_prefix, selected_method, arguments)
                    with selected_client.from_best_host() as client:
                        data = getattr(client, selected_method)(**converted)
                    return result(data, source=selected_source, request=arguments)

                return invoke

            invoke = make_invoke(prefix, source, method_name, client_cls)

            invoke.__name__ = tool_name
            invoke.__qualname__ = tool_name
            mcp.tool(
                name=tool_name,
                description=_description(prefix, method_name, method),
                annotations=READ_ONLY,
                structured_output=True,
            )(invoke)
            registered.append(tool_name)
    return registered
