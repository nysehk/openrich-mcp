# easy-tdx-mcp 服务配置说明

本文给出 Windows 本地部署基线，并说明 OpenRich Quant 如何连接本服务。`easy-tdx-mcp`
使用 MCP stdio transport：OpenRich Quant 启动并持有一个长生命周期子进程，不监听 HTTP
端口，也不能通过手工启动的另一个 stdio 进程共享连接。

## 1. 目录约定

```text
源码仓库: D:\claude\openrich-mcp\easy-tdx-mcp
虚拟环境: D:\claude\env\easy-tdx-mcp
手工调试状态: D:\claude\env\easy-tdx-mcp\state
OpenRich:  D:\claude\openrich
```

虚拟环境必须放在 `D:\claude\env`，不要放进源码仓库，也不要提交 `.venv`、状态缓存或
行情下载文件。

## 2. 创建环境与安装

使用本机 Python 3.13 创建独立环境：

```powershell
New-Item -ItemType Directory -Path D:\claude\env -Force
python -m venv D:\claude\env\easy-tdx-mcp
& D:\claude\env\easy-tdx-mcp\Scripts\python.exe -m pip install --upgrade pip
& D:\claude\env\easy-tdx-mcp\Scripts\python.exe -m pip install `
  D:\claude\openrich-mcp\easy-tdx-mcp
```

创建前先运行 `python -V` 确认为 Python 3.13.9，并用 `Get-Command python` 记录实际路径。
这里使用普通安装而不是 editable install，避免运行环境和源码目录互相污染。

验证安装：

```powershell
& D:\claude\env\easy-tdx-mcp\Scripts\python.exe -c `
  "import easy_tdx_mcp; print('easy-tdx-mcp import ok')"
```

## 3. 单独启动 stdio 服务

仅在 MCP Host 调试或协议验证时手工启动：

```powershell
$env:EASY_TDX_MCP_STATE_DIR = 'D:\claude\env\easy-tdx-mcp\state'
& D:\claude\env\easy-tdx-mcp\Scripts\python.exe -m easy_tdx_mcp.server
```

启动后等待 stdin 中的 MCP JSON-RPC 帧是正常现象。stdout 专用于协议帧，日志写 stderr。
按 `Ctrl+C` 停止。日常使用 OpenRich Quant 时不要预先手工启动；Quant 会自行创建并复用
子进程。

## 4. OpenRich Quant 配置

在 `D:\claude\openrich\.env` 中配置：

```dotenv
OPENRICH_MCP_SOURCE_ROOT=D:\claude\openrich-mcp
EASY_TDX_MCP_PYTHON=D:\claude\env\easy-tdx-mcp\Scripts\python.exe
EASY_TDX_MCP_TIMEOUT_SECONDS=60
QUANT_ENABLE_MCP_WRITES=0
```

- `OPENRICH_MCP_SOURCE_ROOT` 用于定位独立 MCP 仓库和诊断来源，不复制 MCP 源码到 OpenRich。
- `EASY_TDX_MCP_PYTHON` 是 Quant 启动 stdio 服务时使用的解释器。
- `EASY_TDX_MCP_TIMEOUT_SECONDS` 是单次 discovery/call 超时。
- `QUANT_ENABLE_MCP_WRITES=0` 保持默认只读策略。只有明确需要公告下载或离线行情同步时才
  设为 `1`，并同时配置受限写入根目录。

如需启用三个有副作用工具，额外配置：

```dotenv
QUANT_ENABLE_MCP_WRITES=1
EASY_TDX_MCP_WRITE_ROOT=D:\market-data\easy-tdx
```

`EASY_TDX_MCP_WRITE_ROOT` 必须是明确的业务目录，不得指向磁盘根目录、用户目录或源码仓库。

启动 Quant Demo：

```powershell
cd D:\claude\openrich
python .\apps\quant_demo\server.py
```

Quant 启动的 MCP 状态目录由 OpenRich 管理，位于
`data/runtime/quant-web-demo/easy-tdx-mcp-state`；它与手工协议调试目录相互隔离。默认地址为
`http://127.0.0.1:9092/`。验证服务状态：

```powershell
Invoke-RestMethod http://127.0.0.1:9092/quant/mcp/status |
  ConvertTo-Json -Depth 6
```

正常状态应为 `online`，工具总数为 106；默认策略允许 103 个只读工具并禁用 3 个写入工具。

## 5. 更新部署

拉取源码后重新安装，随后重启 Quant，让它创建新 stdio 子进程：

```powershell
cd D:\claude\openrich-mcp
git pull --ff-only
& D:\claude\env\easy-tdx-mcp\Scripts\python.exe -m pip install --upgrade `
  D:\claude\openrich-mcp\easy-tdx-mcp
```

如果修改了依赖或怀疑安装残留，可增加 `--force-reinstall`。更新前后均可用状态接口核对工具
数量与启动错误。

## 6. 常见问题

- **状态为 offline**：先核对 `EASY_TDX_MCP_PYTHON` 是否存在，并用该解释器执行导入验证。
- **启动后没有端口**：这是 stdio 服务的正常行为，不应为它临时配置 HTTP 端口。
- **行情超时**：先增大 `EASY_TDX_MCP_TIMEOUT_SECONDS`，再检查通达信节点可达性；节点故障
  不等同于 MCP 协议或代码失败。
- **中文名称乱码**：优先检查数据源字节编码和解码边界；股票代码与数值字段正常不代表
  名称字段已正确解码。
- **写入被拒绝**：确认同时启用 `QUANT_ENABLE_MCP_WRITES` 并配置合法的
  `EASY_TDX_MCP_WRITE_ROOT`。
