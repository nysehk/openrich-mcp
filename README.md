# OpenRich MCP

**OpenRich MCP** 是一套面向 AI Agent 的金融数据 MCP（Model Context Protocol）服务套件。每个子服务独立依赖、独立测试、独立部署，可被任何支持 MCP 协议的客户端（Claude、Cursor、自研 Agent 等）直接调用，为 LLM 提供真实、可溯源的行情与资讯能力。

```text
openrich-mcp/
├── easy-tdx-mcp/   # 通达信全协议行情与研究：106 个工具、4 个资源
├── cn-stock-mcp/   # A 股行情、财报、行业、宏观与新闻：42 个工具（HTTP/SSE）
└── news-mcp/       # 24 小时财经快讯检索
```

## 服务一览

| 服务 | 定位 | 数据能力 | Transport |
| --- | --- | --- | --- |
| **easy-tdx-mcp** | 通达信行情与研究主力服务 | A 股 / 港股 / 美股 / 期货报价与 K 线、板块、资金流、财务 F10、巨潮公告、34 个技术指标、缠论、策略回测、因子与组合分析、本地通达信文件读取 | stdio |
| **cn-stock-mcp** | A 股金融数据聚合 | 基于 AKShare 的行情、财报、行业、宏观与新闻 | HTTP/SSE（默认 `http://127.0.0.1:7070/sse`） |
| **news-mcp** | 财经快讯 | 最近 N 小时快讯过滤、关键词检索、稳定新闻 ID 与 Evidence 元数据 | stdio |

## easy-tdx-mcp 亮点

- **内置通达信协议实现**：基于 MIT 许可的 [easy_tdx](https://github.com/handsomejustin/easy_tdx) 源码改写，自包含协议、编解码与行情计算，非转发包装层
- **统一工具目录**：67 个客户端工具直接映射协议方法，另覆盖公告、研究计算、回测、因子、组合、离线数据与受控写入
- **批量 K 线**：`batch_kline` 单次最多 500 只标的，服务端并发抓取、自动主机择优与故障切换，11 只百日线约 0.3 秒
- **LLM 友好**：参数使用大写枚举（市场、周期、复权），每个工具带原方法签名与输入 Schema，附 `capabilities` / `indicators` / `strategies` 三个发现资源
- **严格返回契约**：统一 `status` / `source` / `retrieved_at` / `warnings` / `error` 字段，DataFrame、枚举、日期、numpy 标量自动转为严格 JSON

## 快速开始

环境要求：Python 3.12+。

### easy-tdx-mcp（stdio）

```bash
git clone git@github.com:nysehk/openrich-mcp.git
cd openrich-mcp/easy-tdx-mcp
python -m pip install -e .

# 启动 MCP stdio 服务（stdout 只输出协议帧）
python -m easy_tdx_mcp.server
```

- 主站选择缓存默认写入当前目录 `.easy-tdx-state`，可用 `EASY_TDX_MCP_STATE_DIR` 指定其他目录
- 涉及文件写入的工具（公告 PDF 下载、离线日线同步）默认只能写入状态目录；如需写入真实通达信目录，启动前设置 `EASY_TDX_MCP_WRITE_ROOT`

### cn-stock-mcp（HTTP/SSE）

```bash
cd openrich-mcp/cn-stock-mcp
python -m pip install -e .
./scripts/start-cn-stock-mcp.ps1 -Background -Python (Get-Command python).Source
./scripts/start-cn-stock-mcp.ps1 -Status
```

PID 与日志位于 `cn-stock-mcp/.run/`；Docker 与完整参数见 [`cn-stock-mcp/README.md`](cn-stock-mcp/README.md)。

### news-mcp（stdio）

```bash
cd openrich-mcp/news-mcp
python -m pip install -e .
openrich-news-mcp
```

## 在 MCP 客户端中接入

以通用 MCP 客户端配置为例（Claude Desktop、Cursor 等同构）：

```json
{
  "mcpServers": {
    "easy-tdx": {
      "command": "python",
      "args": ["-m", "easy_tdx_mcp.server"],
      "env": { "EASY_TDX_MCP_STATE_DIR": "D:/data/easy-tdx-state" }
    }
  }
}
```

工具按前缀路由，便于 Agent 按意图检索：

| 前缀 | 覆盖 |
| --- | --- |
| `market_*` | A 股 Mac 协议：报价、复权 K 线、板块排行、竞价、异动、资金流 |
| `standard_*` | A 股标准协议：证券列表、除权除息、财务 F10、逐笔、市场统计 |
| `extended_*` / `extended_standard_*` | 港股、美股、期货：列表、报价、K 线、分时、逐笔、市场发现 |
| `analysis_*` | 技术指标（34 个）与缠论计算 |
| `backtest_*` / `factor_*` / `portfolio_*` | 策略回测、截面因子、组合调仓 |
| `offline_*` | 本地通达信日线、分钟线、股本、历史财务与自定义板块读取 |
| `batch_kline` | 多标的并发批量 K 线（最多 500 只/次） |

## 更新

```bash
git pull --ff-only
python -m pip install -e .   # 对应服务目录内
```

## 免责声明

本项目仅供学习和技术研究，不构成任何投资建议。行情许可、频率和使用范围应遵守数据源及当地法规；使用者自行承担投资决策风险。
