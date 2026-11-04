#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateSet('start','stop','status')][string]$Action = 'status',
    [ValidateRange(1,65535)][int]$Port = 8710,
    [string]$AgentDir,
    [string]$AgentConfig,
    [string]$DesktopConfig,
    [string]$PaperLedger,
    [string]$ReportDir,
    [string]$EvaluationFile,
    [string]$WslWorkspace,
    [string]$WslDistribution = 'Ubuntu-24.04',
    [switch]$NoBuild,
    [switch]$FakeAgent,
    [switch]$OpenBrowser
)
$ErrorActionPreference = 'Stop'
$stratideRoot = Split-Path -Parent $PSScriptRoot
$stratideRecordDir = Join-Path $stratideRoot "state/windows-local/$Port"
$stratideRecordPath = Join-Path $stratideRecordDir 'process.json'
$stratideUrl = "http://127.0.0.1:$Port"
function Get-StratideHealth {
    Invoke-RestMethod -Uri "$stratideUrl/api/health" -TimeoutSec 2 -NoProxy
}
if ($Action -eq 'status') {
    $stratideHealth = Get-StratideHealth
    [pscustomobject]@{ Url=$stratideUrl; Service=$stratideHealth.data.service; PaperOnly=$stratideHealth.data.paper_only; ProcessId=$stratideHealth.data.process_id } | ConvertTo-Json
    exit 0
}
if ($Action -eq 'stop') {
    if (-not (Test-Path -LiteralPath $stratideRecordPath)) { throw '没有本脚本启动的实例记录；不会按端口猜测并结束其他进程。' }
    $stratideRecord = Get-Content -LiteralPath $stratideRecordPath -Raw | ConvertFrom-Json
    $stratideHealth = Get-StratideHealth
    if ($stratideHealth.data.instance_id -ne $stratideRecord.InstanceId) { throw '本地实例已变化，保留进程和记录供核对。' }
    if ($stratideRecord.Wsl) {
        & wsl.exe --distribution $stratideRecord.Distribution --exec kill -TERM $stratideHealth.data.process_id
        if ($LASTEXITCODE -ne 0) { throw 'WSL Dashboard 停止失败。' }
    } else {
        $stratideProcess = Get-Process -Id $stratideRecord.ProcessId
        if ($stratideProcess.StartTime.ToUniversalTime().Ticks -ne ([datetime]$stratideRecord.StartTime).ToUniversalTime().Ticks) { throw '进程标识已变化，禁止停止。' }
        Stop-Process -InputObject $stratideProcess
    }
    Remove-Item -LiteralPath $stratideRecordPath
    Write-Host '已停止本次 Dashboard。独立 CPU Worker 使用原 timesfm-cpu.py stop；已发云调用不能撤回，不会自动重发。'
    exit 0
}
if (Test-Path -LiteralPath $stratideRecordPath) { throw '已有实例记录；先运行 status/stop，异常退出后核对 PID 与日志，再保留并移走旧记录。' }
New-Item -ItemType Directory -Path $stratideRecordDir -Force | Out-Null
$stratideArguments = [System.Collections.Generic.List[string]]::new()
if ($WslWorkspace) {
    if (-not $WslWorkspace.StartsWith('/')) { throw 'WslWorkspace 必须是已有 ext4 工作树的绝对路径。' }
    if (-not $NoBuild) {
        & wsl.exe --distribution $WslDistribution --cd $WslWorkspace --exec cargo build --workspace --locked --offline
        if ($LASTEXITCODE -ne 0) { throw 'WSL 构建失败。' }
    }
    $stratideFile = 'wsl.exe'
    foreach ($stratideArg in @('--distribution',$WslDistribution,'--cd',$WslWorkspace,'--exec',"$WslWorkspace/target/debug/stratided")) { $stratideArguments.Add($stratideArg) }
    $stratideAssets = "$WslWorkspace/apps/dashboard/dist"
} else {
    if (-not $NoBuild) {
        & npm.cmd --prefix (Join-Path $stratideRoot 'apps/dashboard') ci --ignore-scripts --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败。' }
        & npm.cmd --prefix (Join-Path $stratideRoot 'apps/dashboard') run build
        if ($LASTEXITCODE -ne 0) { throw '前端构建失败。' }
        & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'with-msvc.ps1') build --workspace --locked --offline
        if ($LASTEXITCODE -ne 0) { throw 'Rust 构建失败。' }
    }
    $stratideFile = Join-Path $stratideRoot 'target/debug/stratided.exe'
    $stratideAssets = Join-Path $stratideRoot 'apps/dashboard/dist'
    if ($FakeAgent) {
        if (-not $AgentDir) { throw 'FakeAgent 必须显式指定新的 AgentDir。' }
        if (-not (Test-Path -LiteralPath $AgentDir)) {
            & $stratideFile --agent-init-fake $AgentDir
            if ($LASTEXITCODE -ne 0) { throw '合成 Agent 初始化失败。' }
        }
    }
}
foreach ($stratideArg in @('--port',$Port.ToString(),'--assets-dir',$stratideAssets)) { $stratideArguments.Add($stratideArg) }
foreach ($stratidePair in @(@('--agent-dir',$AgentDir),@('--agent-config',$AgentConfig),@('--desktop-config',$DesktopConfig),@('--paper-ledger',$PaperLedger),@('--report-dir',$ReportDir),@('--evaluation-file',$EvaluationFile))) {
    if ($stratidePair[1]) { $stratideArguments.Add($stratidePair[0]); $stratideArguments.Add($stratidePair[1]) }
}
$stratideInfo = [System.Diagnostics.ProcessStartInfo]::new()
$stratideInfo.FileName = $stratideFile
$stratideInfo.WorkingDirectory = $stratideRoot
$stratideInfo.UseShellExecute = $true
$stratideInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$stratideInfo.CreateNoWindow = $true
foreach ($stratideArg in $stratideArguments) { $stratideInfo.ArgumentList.Add($stratideArg) }
$stratideProcess = [System.Diagnostics.Process]::Start($stratideInfo)
try {
    $stratideHealth = $null
    for ($stratideAttempt=0; $stratideAttempt -lt 100; $stratideAttempt++) {
        if ($stratideProcess.HasExited) { throw '服务启动失败；检查配置与端口，未改写已有数据。' }
        try { $stratideHealth = Get-StratideHealth; break }
        catch [System.Net.Http.HttpRequestException] { Start-Sleep -Milliseconds 100 }
        catch [System.Threading.Tasks.TaskCanceledException] { Start-Sleep -Milliseconds 100 }
    }
    if ($null -eq $stratideHealth) { throw '本地健康检查超时。' }
    $stratideRecord = @{ ProcessId=$stratideProcess.Id; StartTime=$stratideProcess.StartTime.ToUniversalTime().ToString('o'); InstanceId=$stratideHealth.data.instance_id; Wsl=[bool]$WslWorkspace; Distribution=$WslDistribution }
    $stratideStream = [System.IO.File]::Open($stratideRecordPath,[System.IO.FileMode]::CreateNew)
    try { $stratideBytes=[System.Text.Encoding]::UTF8.GetBytes(($stratideRecord|ConvertTo-Json)); $stratideStream.Write($stratideBytes); $stratideStream.Flush($true) } finally { $stratideStream.Dispose() }
} catch {
    if (-not $stratideProcess.HasExited) { $stratideProcess.Kill(); $stratideProcess.WaitForExit() }
    throw
}
Write-Host "Dashboard 已启动：$stratideUrl；使用 local-windows.ps1 stop -Port $Port 停止。"
if ($OpenBrowser) { Start-Process $stratideUrl }
