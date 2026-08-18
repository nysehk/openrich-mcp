from __future__ import annotations

import inspect
from typing import Any, Callable

import easy_tdx.offline as offline
from easy_tdx.models.enums import Market
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .response import result


READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)

_READ_FUNCTIONS = [
    "detect_tdx_home",
    "resolve_vipdoc",
    "find_daily_bar_file",
    "find_5min_bar_file",
    "find_lc1_bar_file",
    "find_lc5_bar_file",
    "read_daily_bars",
    "read_5min_bars",
    "read_lc_min_bars",
    "read_ex_daily_bars",
    "read_gbbq",
    "read_history_financial",
    "read_block_dat",
    "read_customer_blocks",
    "get_last_bar_date",
    "get_last_ex_bar_date",
    "get_last_5min_bar_datetime",
    "get_last_lc_min_bar_datetime",
]


def register_offline_tools(mcp: FastMCP) -> list[str]:
    names: list[str] = []
    for function_name in _READ_FUNCTIONS:
        function = getattr(offline, function_name)
        tool_name = f"offline_{function_name}"

        def factory(selected: Callable[..., Any]) -> Callable[[dict[str, Any]], dict[str, Any]]:
            def invoke(arguments: dict[str, Any]) -> dict[str, Any]:
                converted = dict(arguments)
                if "market" in converted and isinstance(converted["market"], str):
                    converted["market"] = Market[converted["market"].upper()]
                return result(selected(**converted), source="local", request=arguments)

            return invoke

        invoke = factory(function)
        invoke.__name__ = tool_name
        invoke.__qualname__ = tool_name
        signature = str(inspect.signature(function))
        description = (inspect.getdoc(function) or function_name).splitlines()[0]
        mcp.tool(
            name=tool_name,
            description=(
                f"{description} 只读取本地通达信文件，不联网、不修改文件。"
                f"参数放在 arguments 对象中，原函数签名：{function_name}{signature}。"
            ),
            annotations=READ_ONLY,
            structured_output=True,
        )(invoke)
        names.append(tool_name)
    return names
