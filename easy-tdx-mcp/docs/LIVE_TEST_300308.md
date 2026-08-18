# 300308 MCP 全量 Live 测试

## 目的

验证成品 MCP 而不是直接调用 Python 服务层：测试器启动 `easy_tdx_mcp.server` 的 stdio
进程，完成 MCP 初始化、工具/资源发现、资源读取，再按目录逐项调用工具并生成机器可读报告。

## 执行

```powershell
& D:\anaconda3\python.exe .\scripts\live_test_300308.py --timeout 35
```

默认输出：

- 报告：`reports/live-test-300308.json`
- 受控状态与写入目录：`.easy-tdx-state/live-test-300308`
- A 股在线样本：深市 `300308`
- 扩展市场在线样本：港股 `00700`
- 研究计算样本：脚本内固定 OHLCV，保证结果可复现

## 覆盖与判定

1. `initialize`、`tools/list`、`resources/list` 必须成功。
2. 4 个 MCP resources 必须能读取。
3. `server_ping` 分别测试 `mac`、`standard`、`extended`，记录每个候选 IP、端口和延迟。
4. 每个可安全、有界执行的工具都真实调用，MCP 返回成功记为 `PASS`。
5. 协议错误、参数错误、MCP 错误或超时记为 `FAIL`，报告保留错误摘要和耗时。
6. 会产生无界下载、请求港股全日逐笔，或依赖本机既有通达信文件且没有测试夹具的工具记为
   `SKIP`；跳过原因必须写入报告。

外部服务器不可达不等于 MCP 注册或序列化失败。复盘时应按工具组聚合：若同一协议组连续
超时而其他工具正常，先检查报告中的服务器测速结果和节点切换日志，再判断是否需要改代码。

## 报告字段

- `tool_count`、`resource_count`：服务发现数量。
- `counts`：PASS、FAIL、SKIP 总数。
- `servers`：三类服务器的 MCP 测速结果。
- `resources`：资源读取结果。
- `results`：按工具名记录状态、耗时、摘要或错误。
- `started_at`、`finished_at`：测试时间范围。

任何修复都应先运行单元测试和 Ruff，再至少复测失败工具；协议服务器状态变化较大时，重新跑
完整脚本并保留新的 JSON 报告。
