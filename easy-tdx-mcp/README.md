# OpenRich easy_tdx MCP

独立、只读的行情与公告 MCP Server。底层使用 [`easy_tdx`](https://github.com/handsomejustin/easy_tdx)，当前提供：

- `kline`：K 线，支持市场、周期、数量和复权参数。
- `quote`：一个或多个 A 股标的的实时快照。
- `announcement`：通过巨潮资讯网检索上市公司公告，返回详情页和 PDF 直链；不在 MCP 进程内下载文件。

`announcement` 优先使用上游 `easy_tdx.cninfo.CninfoClient`。若当前 PyPI 版本尚未
包含该模块，则使用 MCP 内与上游 MIT 实现兼容的只读 HTTP 客户端；两条路径都直接访问
巨潮资讯网，不会回退到模拟公告。当前不开放 PDF 下载副作用，返回的 `pdf_url` 可交给
后续受控 Artifact 下载流程。

## 启动

```powershell
& D:\anaconda3\python.exe -m pip install -e .
& D:\anaconda3\python.exe -m easy_tdx_mcp.server
```

服务使用 MCP stdio transport，stdout 只用于协议消息。`easy_tdx` 的主站选择缓存默认写入本仓库 `.easy-tdx-state`，也可通过 `EASY_TDX_MCP_STATE_DIR` 修改。

## Harness 联调

在 `openrich` 根目录运行：

```powershell
& D:\anaconda3\python.exe .\examples\verify_easy_tdx_mcp.py
```

脚本会通过 MCP 完成 initialize、tool discovery，并真实调用 K 线与实时报价。该项目只用于学习和技术研究；行情许可、频率和使用范围遵循 `easy_tdx` 与数据源的条款。
