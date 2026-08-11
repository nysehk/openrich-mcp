[CmdletBinding()]
param(
    [string]$BindHost = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 7070,
    [string]$Python = "python",
    [switch]$Background,
    [switch]$Status,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $projectRoot "src"
$runRoot = Join-Path $projectRoot ".run"
$pidPath = Join-Path $runRoot "cn-stock-mcp-$Port.pid"
$stdoutPath = Join-Path $runRoot "cn-stock-mcp-$Port.stdout.log"
$stderrPath = Join-Path $runRoot "cn-stock-mcp-$Port.stderr.log"

function Test-McpPort {
    param([string]$TargetHost, [int]$TargetPort)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connect = $client.ConnectAsync($TargetHost, $TargetPort)
        return $connect.Wait(1000) -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Get-ManagedProcess {
    if (-not (Test-Path -LiteralPath $pidPath)) {
        return $null
    }
    $managedPid = [int](Get-Content -LiteralPath $pidPath -Raw)
    return Get-Process -Id $managedPid -ErrorAction SilentlyContinue
}

if ($Status) {
    $managed = Get-ManagedProcess
    [pscustomobject]@{
        name = "cn-stock-mcp"
        endpoint = "http://${BindHost}:$Port/sse"
        online = Test-McpPort -TargetHost $BindHost -TargetPort $Port
        managed_pid = if ($managed) { $managed.Id } else { $null }
    } | ConvertTo-Json
    exit 0
}

if ($Stop) {
    $managed = Get-ManagedProcess
    if (-not $managed) {
        Write-Output "No managed cn-stock-mcp process found for port $Port."
        exit 0
    }
    Stop-Process -Id $managed.Id -Force
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    Write-Output "Stopped cn-stock-mcp pid=$($managed.Id) port=$Port."
    exit 0
}

if (Test-McpPort -TargetHost $BindHost -TargetPort $Port) {
    throw "Port $Port is already in use. Run with -Status to inspect the endpoint."
}

$pythonCommand = Get-Command $Python -ErrorAction Stop
$pythonExe = $pythonCommand.Source
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = if ($previousPythonPath) {
    "$sourceRoot$([IO.Path]::PathSeparator)$previousPythonPath"
} else {
    $sourceRoot
}

try {
    & $pythonExe -c "import akshare, mcp, pandas" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Python dependencies are unavailable. Run: python -m pip install -e ."
    }

    if (-not $Background) {
        Write-Output "Starting cn-stock-mcp at http://${BindHost}:$Port/sse"
        Push-Location $projectRoot
        try {
            & $pythonExe -m cn_stock_mcp --http --host $BindHost --port $Port
            exit $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
    }

    New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
    $process = Start-Process -FilePath $pythonExe `
        -ArgumentList "-m", "cn_stock_mcp", "--http", "--host", $BindHost, "--port", $Port `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -WindowStyle Hidden `
        -PassThru

    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 250
        if ($process.HasExited) {
            $details = Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue
            throw "cn-stock-mcp exited during startup. $details"
        }
        if (Test-McpPort -TargetHost $BindHost -TargetPort $Port) {
            $ready = $true
            break
        }
    }
    if (-not $ready) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw "cn-stock-mcp did not listen on port $Port within 5 seconds."
    }

    Set-Content -LiteralPath $pidPath -Value $process.Id -Encoding ascii
    Write-Output "Started cn-stock-mcp pid=$($process.Id) endpoint=http://${BindHost}:$Port/sse"
    Write-Output "Logs: $stdoutPath ; $stderrPath"
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
