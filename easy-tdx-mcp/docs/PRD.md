# OpenRich Easy TDX MCP 产品需求文档

## 1. 产品定义

将 MIT 许可的 `handsomejustin/easy_tdx` 源码迁移、重构为一个自包含的 Python MCP Server。第三方仓库仅作为实现与兼容性基线；成品不得把 `easy-tdx` 发行包作为运行时依赖，也不得通过 CLI/REST 转发伪装成本地实现。

目标用户是需要由 LLM、Codex Skill 或其他 MCP Host 获取中国及扩展市场数据、执行技术分析和研究型回测的开发者。所有工具必须具备明确的动词式名称、可枚举参数、边界说明、数据来源、时间戳和结构化错误。

## 2. 目标与非目标

### 目标

- 等价保留 easy_tdx 1.20.6 的协议、解析、行情、分析、回测、因子、组合、离线与公开数据源能力。
- 以内置 `easy_tdx` fork 内核运行，安装成品时不再安装第三方 `easy-tdx` 包。
- 将适合单次请求的能力暴露为 MCP tools；将说明、枚举和能力目录暴露为 MCP resources。
- 对网络、文件写入、长耗时计算分别标注只读性、幂等性和副作用。
- 返回 JSON 兼容结果，统一包含 `status`、`source`、`retrieved_at`、`data`、`warnings`、`error`。
- 支持 stdio，预留 streamable HTTP 运行方式。

### 非目标

- 不提供自动交易、下单、账户登录或收益承诺。
- 不绕过数据源许可、访问控制或频率限制。
- 不把 Web UI 的像素级复刻作为 MCP 首版验收条件；Web/CLI 内核代码保留，但 MCP 以结构化工具为主。
- 不允许无限时长订阅或无上限全市场扫描阻塞一次 MCP 调用。

## 3. 功能矩阵

| 领域 | 必须保留的能力 | MCP 形态 |
|---|---|---|
| 服务发现 | 标准、Mac、扩展三类服务器测速，返回 IP、端口、延迟与可用性 | `server_ping` |
| 标准 A 股协议 | 证券数、证券列表、报价、个股/指数 K 线、分时、逐笔、除权除息、财务、F10、板块、市场统计、资金流、服务器文件 | 独立查询工具；文件下载单独标副作用 |
| Mac A 股协议 | 分类报价、复权 K 线、分时/采样、板块成员/归属/汇总/排行/N 日涨跌、集合竞价、异动、证券信息、资金流 | 行情、板块、监控工具组 |
| 扩展市场 | 市场枚举、证券数/列表、港美股/期货报价、K 线、分时、逐笔、港股全日逐笔 | `tdx_ex_*` 工具组 |
| 公告与财报 | 巨潮公告检索/PDF URL/受控下载；新浪利润表、资产负债表、现金流量表 | `announcement`、`announcement_download_pdf`、`sina_get_financial_report` |
| 技术指标 | 34 个指标：MACD、RSI、BOLL、BIAS、PSY、TRIX、DPO、MTM、ROC、EXPMA、BBI、DFMA、KDJ、DMI、ATR、WR、CCI、CR、KTN、XSII、OBV、VR、EMV、MASS、MFI、BRAR、ASI、ZHUOYAO、BIAS_SIGNAL、TAQ、SAR、VWAP、AROON、FK | 指标目录资源 + K 线计算工具 + 内联 OHLCV 计算工具 |
| 缠论 | K 线合并、分型、笔、中枢、线段、买卖点、背驰、多级别联立 | `analysis_chanlun` |
| 回测 | 策略基类、19 个内置策略、撮合、滑点、订单、绩效、归因、网格优化、多策略、组合回测、DSL | 策略目录资源 + 回测/优化/归因工具 |
| 因子 | 内置动量、反转、质量、技术、估值、波动率、成交量、缠论因子；预处理、IC/分层分析 | 因子目录资源 + `factor_compute_cross_section`、`factor_analyze` |
| 组合 | 等权、因子加权、风险平价、均值方差，风险模型与再平衡 | `portfolio_run_rebalance` 及自动映射的组合工具 |
| 选股 | 策略信号扫描、强度排名、回测排名 | 有界 universe/数量/并发参数的扫描工具 |
| 实时 | EventBus、RealtimeStrategy、RealtimeDataFeed 轮询 | 有界采样工具；不在 stdio 请求内创建永久后台任务 |
| 离线 | 自动发现通达信目录，读取日线/分钟/扩展日线/股本变迁/历史财务/自定义板块 | `offline_read_*` 只读工具 |
| 离线写入 | 日线和分钟线编码、增量追加、市场同步 | 独立 `offline_sync_*`，明确文件写入副作用 |

## 4. MCP 工具设计原则

1. 名称采用 `领域_动作_对象`，例如 `market_get_kline`，避免 `run`、`query` 等无语义名称。
2. 市场、周期、复权、板块类型、排序方式使用枚举，不要求 LLM 猜整数协议值。
3. 股票输入统一为 `market` + `code`；批量输入统一为 `[{"market":"SH","code":"600519"}]`。
4. 时间使用 ISO 8601；仅协议必须时接受 `YYYYMMDD`，描述中给出示例。
5. 大结果必须支持 `offset/count` 或 `limit`；响应回传请求量、实际量和是否截断。
6. 网络失败、无数据、部分数据、参数错误不得混为一类；错误包含稳定 `code` 和可执行 `message`。
7. 每个工具描述回答：何时使用、数据来源、关键参数、上限、返回核心字段、是否写文件。
8. 行情和研究结果都携带免责声明，不把计算信号描述成投资建议。

## 5. 统一响应契约

```json
{
  "status": "ok | partial | unavailable | error",
  "source": "tdx_mac | tdx_standard | tdx_ex | cninfo | sina | local | computed",
  "retrieved_at": "2026-08-18T00:00:00Z",
  "request": {},
  "data": [],
  "meta": {"returned_count": 0, "truncated": false},
  "warnings": [],
  "error": null
}
```

数据帧必须把 `NaN`、`NaT`、numpy 标量、日期和枚举转换为严格 JSON 值。网络异常需隐藏内部堆栈，但保留异常类型到诊断日志。

## 6. 架构约束

- `src/easy_tdx/`：从上游迁移的自包含 fork 内核，保留原 MIT 许可证与 NOTICE。
- `src/easy_tdx_mcp/`：MCP 专用输入模型、服务编排、序列化、错误映射、工具与资源。
- MCP 层不得依赖 Click CLI 或 FastAPI 路由完成业务调用，必须直接调用项目内 Python 内核。
- stdout 仅用于 MCP stdio 帧；日志写 stderr。
- 本地状态默认位于项目可配置目录，不污染用户主目录。
- 读工具默认 `readOnlyHint=true`；文件下载/同步等工具为 false，并把目标路径限制在显式允许目录。

## 7. 安全与合规

- 保留上游版权、MIT License、NOTICE 和改写说明。
- 公告 PDF、服务器文件及离线同步不得隐式下载；必须调用明确的写入工具。
- 校验目标路径，拒绝根目录、用户目录和路径穿越。
- 限制批量报价、逐笔、K 线、扫描、优化网格和实时采样上限。
- 所有输出注明仅供学习与技术研究，不构成投资建议。

## 8. 验收标准

- `pyproject.toml` 不含 `easy-tdx` 依赖；干净环境仅安装本项目即可导入内核和启动 MCP。
- 能通过 MCP initialize、tools/list、resources/list，并调用至少：K 线、报价、指标、板块、扩展市场、缠论、回测、离线读取。
- 自动化测试覆盖参数校验、统一序列化、网络异常、只读/写入注解、代表性工具和上游能力清单完整性。
- 上游公共客户端方法、34 指标、19 策略及主要 CLI 功能均能映射到 MCP 工具、资源或明确的等价调用入口。
- README 给出安装、配置、工具选择指南、Skill 集成示例、错误语义、数据源和免责声明。

## 9. 当前交付基线

- MCP 目录：105 个 tools、4 个 resources。
- 自动映射客户端工具：67 个，覆盖标准 A 股、Mac A 股、扩展市场及标准扩展协议。
- 协议验证：必须通过真实 stdio `initialize`、`tools/list`、`resources/list` 和资源读取。
- Live 验证：`scripts/live_test_300308.py` 遍历完整工具目录；外部节点不可达、无本地样本和
  主动跳过的大下载必须分别记录，不能以模拟数据冒充在线通过。
