# OpenRich Easy TDX MCP

自包含的 Python MCP Server。项目基于 MIT 许可的 [`handsomejustin/easy_tdx`](https://github.com/handsomejustin/easy_tdx) 源码改写，内置通达信协议、编解码、行情与研究计算代码；它不是安装 `easy-tdx` 后再转发调用的包装层。

基线为上游提交 `e533b70`（项目元数据 1.20.6）。版权与许可见 `THIRD_PARTY_LICENSE.easy_tdx`、`THIRD_PARTY_NOTICE.easy_tdx`。

## 已覆盖能力

当前 MCP 目录包含 **105 个 tools** 和 **4 个 resources**。工具目录在服务启动时生成，
其中 67 个客户端工具直接映射到项目内置协议客户端的公开方法；其余工具覆盖公告、
研究计算、回测、因子、组合、本地数据、受控写入和诊断能力。

- 标准协议：证券列表、报价、个股/指数 K 线、分时、逐笔、除权除息、财务/F10、板块、服务器文件、市场统计和资金流。
- Mac 协议：复权 K 线、分类报价、板块汇总/排行、竞价、异动、资金流和证券信息。
- 扩展市场：港股、美股、期货的列表、报价、K 线、分时和逐笔。
- 研究计算：34 个技术指标、完整缠论管道、19 个内置策略回测。
- 本地数据：通达信日线、分钟线、扩展日线、股本变迁、历史财务和自定义板块读取。
- 独立数据源：巨潮资讯公告检索。
- 补充能力：三类服务器测速、标准扩展市场发现/信息/区间历史、F10 板块名完整读取、
  新浪财报三表、多级别缠论、截面因子分析、多期组合调仓和有界实时行情采样。
- 受控写入：公告 PDF 下载、单股日线同步、分页全市场日线同步。

完整产品范围与验收口径见 [`docs/PRD.md`](docs/PRD.md)，实施分期见 [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)。

## 安装与启动

```powershell
& D:\anaconda3\python.exe -m pip install -e ".[dev]"
& D:\anaconda3\python.exe -m easy_tdx_mcp.server
```

默认使用 MCP stdio transport，stdout 只输出协议帧。主站选择缓存写入当前目录 `.easy-tdx-state`；可通过 `EASY_TDX_MCP_STATE_DIR` 指定其他目录。

## LLM / Skill 如何选择工具

先读以下资源：

- `resource://easy-tdx/capabilities`：所有客户端工具名与前缀选择说明。
- `resource://easy-tdx/indicators`：34 个指标的输入、输出和参数。
- `resource://easy-tdx/strategies`：19 个内置策略及参数 schema。

工具前缀：

- `market_*`：推荐的 A 股 Mac 协议，例如 `market_get_stock_kline`、`market_get_board_ranking`。
- `standard_*`：标准协议独有能力，例如 `standard_get_xdxr_info`、`standard_get_finance_info`。
- `extended_*`：港股、美股与期货，例如 `extended_goods_kline`。
- `analysis_*`：对调用方已有 OHLCV 数据执行指标或缠论计算。
- `backtest_*`：研究型回测。
- `offline_*`：只读本地通达信文件。
- `extended_standard_*`：标准 7727 扩展协议的市场发现、商品信息和日期区间历史。

补充的高层工具包括：

- `server_ping`
- `company_get_section`
- `sina_get_financial_report`
- `announcement_download_pdf`
- `analysis_chanlun_multi_level`
- `factor_compute_cross_section`、`factor_analyze`
- `portfolio_run_rebalance`
- `realtime_sample_quotes`
- `offline_sync_daily`、`offline_sync_market_daily`

### 文件写入安全

PDF 下载和离线同步不会默认获得任意磁盘写权限。未配置时只能写入
`.easy-tdx-state`；如需同步真实通达信目录，应在启动 MCP 前显式设置：

```powershell
$env:EASY_TDX_MCP_WRITE_ROOT = "C:\new_jyplug"
& D:\anaconda3\python.exe -m easy_tdx_mcp.server
```

全市场同步必须用 `start`、`limit` 分页调用，单次最多处理 500 个 `.day` 文件。
实时采样最多 80 个标的、10 轮，避免永久占用一次 MCP 请求。

自动生成的协议工具使用统一输入：

```json
{
  "arguments": {
    "market": "SH",
    "code": "600519",
    "period": "DAILY",
    "count": 30,
    "adjust": "QFQ"
  }
}
```

每个工具描述都带原 Python 方法签名。市场、周期、复权、板块和排序参数优先使用大写枚举名，不要求模型猜协议整数。

## 返回契约

新工具统一返回 `status`、`source`、`retrieved_at`、`request`、`data`、`meta`、`warnings` 和 `error`。DataFrame、dataclass、枚举、日期、numpy 标量和非有限浮点会转换成严格 JSON；二进制服务器文件以 base64 和字节数返回。

## 测试

```powershell
& D:\anaconda3\python.exe -m pytest -q
& D:\anaconda3\python.exe -m ruff check src tests
```

单元测试不要求连接行情服务器。真实网络 smoke test 应单独执行，避免把通达信主站可用性当成代码正确性。

以深市 `300308` 为主标的遍历 MCP 目录并记录服务器 IP、耗时、通过/失败/跳过状态：

```powershell
& D:\anaconda3\python.exe .\scripts\live_test_300308.py --timeout 35
```

脚本通过真实 MCP stdio 会话执行 `initialize`、资源读取和全部工具发现；A 股接口使用
`SZ/300308`，扩展市场接口使用 `HK/00700`，纯计算工具使用固定 OHLCV 样本。可能下载
无界大文件、全日逐笔或缺少本地通达信样本的接口会明确标为 `SKIP`，不会伪造通过。
JSON 报告写入 `reports/live-test-300308.json`。具体范围、判定方式和复测建议见
[`docs/LIVE_TEST_300308.md`](docs/LIVE_TEST_300308.md)。

## 免责声明

本项目仅供学习和技术研究，不构成任何投资建议。行情许可、频率和使用范围应遵守数据源及当地法规；使用者自行承担投资决策风险。
