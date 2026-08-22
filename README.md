# OpenRich MCP

OpenRich 的独立 MCP 服务 monorepo。每个子目录保持独立依赖、测试和发布周期，
OpenRich Harness 只通过 MCP 协议调用，不直接依赖其内部实现。

```text
openrich-mcp/
├── easy-tdx-mcp/   # K 线、报价、巨潮公告
├── news-mcp/       # 24 小时财经快讯
└── cn-stock-mcp/   # A 股行情、财报、行业、宏观与新闻（42 个工具）
```

本仓库与 OpenRich Harness 分开发布；各 MCP 服务共享本仓库历史，但可独立测试和部署。

`easy-tdx-mcp` 的 OpenRich Quant/stdio 部署使用独立虚拟环境，完整配置见
[`easy-tdx-mcp/docs/SERVICE_CONFIGURATION.md`](easy-tdx-mcp/docs/SERVICE_CONFIGURATION.md)。

## Windows 独立部署基线

推荐将本仓库部署在 Harness 工作区之外：

```text
MCP 源码/运行目录: D:\services\openrich-mcp
Harness 工作区:    D:\claude\openrich
cn-stock endpoint: http://127.0.0.1:7070/sse
```

首次安装与启动：

```powershell
git clone git@github.com:nysehk/openrich-mcp.git D:\services\openrich-mcp
cd D:\services\openrich-mcp\cn-stock-mcp
& D:\anaconda3\python.exe -m pip install -e .
.\scripts\start-cn-stock-mcp.ps1 -Background -Python 'D:\anaconda3\python.exe'
.\scripts\start-cn-stock-mcp.ps1 -Status
```

更新服务：

```powershell
cd D:\services\openrich-mcp
git pull --ff-only
cd .\cn-stock-mcp
.\scripts\start-cn-stock-mcp.ps1 -Stop
.\scripts\start-cn-stock-mcp.ps1 -Background -Python 'D:\anaconda3\python.exe'
```

PID 和 stdout/stderr 位于 `cn-stock-mcp/.run/`。完整参数、Docker 和 Harness 配置见
[`cn-stock-mcp/README.md`](cn-stock-mcp/README.md)。Harness 只连接 endpoint，不应从其工作区
临时启动第二个 MCP 进程。
