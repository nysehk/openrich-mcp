# OpenRich News MCP

从 `testweb` 的“实时 A 股 / 24 小时快讯”提取的独立只读 MCP。保留 crabpi 数据源和兼容解析，并补充最近 N 小时过滤、关键词检索、稳定新闻 ID 和 Evidence 元数据。

## Tool

- `search(query="", hours=24, limit=30)`：查询最近 24 小时财经快讯。Harness 使用 `namespace="news"` 绑定后，Tool 名为 `news.search`。

## 本地验证

```powershell
& D:\anaconda3\python.exe -m pytest .\news-mcp\tests -q
```

服务默认走真实 API。测试和 Banking Demo 通过 `OPENRICH_NEWS_FIXTURE` 使用本地 fixture，不依赖网络。

