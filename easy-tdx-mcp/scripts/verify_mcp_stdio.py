from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def verify() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "easy_tdx_mcp.server"],
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
    names = {tool.name for tool in tools.tools}
    required = {
        "server_ping",
        "extended_standard_get_markets",
        "company_get_section",
        "sina_get_financial_report",
        "analysis_chanlun_multi_level",
        "factor_compute_cross_section",
        "factor_analyze",
        "portfolio_run_rebalance",
        "realtime_sample_quotes",
        "announcement_download_pdf",
        "offline_sync_daily",
        "offline_sync_market_daily",
    }
    missing = required - names
    if missing:
        raise SystemExit(f"missing MCP tools: {sorted(missing)}")
    if len(tools.tools) != 105:
        raise SystemExit(f"unexpected tool count: {len(tools.tools)}")
    if len(resources.resources) != 4:
        raise SystemExit(f"unexpected resource count: {len(resources.resources)}")
    print(
        {
            "server": initialized.serverInfo.name,
            "tools": len(tools.tools),
            "resources": len(resources.resources),
            "required_tools": len(required),
        }
    )


if __name__ == "__main__":
    asyncio.run(verify())
