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
