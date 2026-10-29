#requires -Version 7.0
<# Start from the repository root. No report is selected implicitly. #>
[CmdletBinding()]
param(
    [string]$ReportDir,
    [string]$EvaluationFile,
    [string]$AgentDir = 'state/agent',
    [string]$AgentConfig,
    [switch]$FakeAgent,
    [ValidateRange(1, 65535)][int]$Port = 8710,
    [switch]$NoBuild,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$stratideRoot = Split-Path -Parent $PSScriptRoot
$stratideArguments = [System.Collections.Generic.List[string]]::new()
$stratideArguments.Add('--port')
$stratideArguments.Add($Port.ToString())
$stratideArguments.Add('--assets-dir')
$stratideArguments.Add((Join-Path $stratideRoot 'apps/dashboard/dist'))
$stratideAgentPath = if ([System.IO.Path]::IsPathRooted($AgentDir)) { $AgentDir } else { Join-Path $stratideRoot $AgentDir }
$stratideArguments.Add('--agent-dir')
$stratideArguments.Add($stratideAgentPath)
if ($AgentConfig) { $stratideArguments.Add('--agent-config'); $stratideArguments.Add((Resolve-Path -LiteralPath $AgentConfig).Path) }
if ($ReportDir) {
    $stratideArguments.Add('--report-dir')
    $stratideArguments.Add((Resolve-Path -LiteralPath $ReportDir).Path)
}
if ($EvaluationFile) {
    $stratideArguments.Add('--evaluation-file')
    $stratideArguments.Add((Resolve-Path -LiteralPath $EvaluationFile).Path)
}
Push-Location $stratideRoot
try {
    if (-not $NoBuild) {
        & npm.cmd --prefix apps/dashboard ci --ignore-scripts --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败' }
        & npm.cmd --prefix apps/dashboard run build
        if ($LASTEXITCODE -ne 0) { throw '前端构建失败' }
        # Run in a child PowerShell: with-msvc.ps1 intentionally uses exit.
        & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'with-msvc.ps1') build --locked -p stratided
        if ($LASTEXITCODE -ne 0) { throw 'Rust 服务构建失败' }
    }
    if ($FakeAgent -and -not (Test-Path -LiteralPath (Join-Path $stratideAgentPath 'settings.json'))) {
        & (Join-Path $stratideRoot 'target/debug/stratided.exe') --agent-init-fake $stratideAgentPath
        if ($LASTEXITCODE -ne 0) { throw 'fake Agent 初始化失败' }
    }
    New-Item -ItemType Directory -Force -Path $stratideAgentPath | Out-Null
    if ($IsWindows) {
        # Keep task context, trusted settings and Owner token in this user's ACL.
        $stratideOwnerSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        & icacls.exe $stratideAgentPath /inheritance:r /grant:r "*$($stratideOwnerSid):(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' /Q | Out-Null
        if ($LASTEXITCODE -ne 0) { throw '无法保护本地 Agent 目录' }
    }
    $stratideInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $stratideInfo.FileName = Join-Path $stratideRoot 'target/debug/stratided.exe'
    $stratideInfo.WorkingDirectory = $stratideRoot
    $stratideInfo.UseShellExecute = $false
    $stratideInfo.CreateNoWindow = $true
    foreach ($stratideArgument in $stratideArguments) { $stratideInfo.ArgumentList.Add($stratideArgument) }
    $stratideProcess = [System.Diagnostics.Process]::Start($stratideInfo)
    try {
        $stratideUrl = "http://127.0.0.1:$Port"
        $stratideReady = $false
        for ($stratideAttempt = 0; $stratideAttempt -lt 50; $stratideAttempt++) {
            if ($stratideProcess.HasExited) { throw '服务启动失败，请检查端口和前端构建' }
            try {
                $stratideHealth = Invoke-RestMethod -Uri "$stratideUrl/api/health" -TimeoutSec 1
                if ($stratideHealth.data.service -eq 'online') { $stratideReady = $true; break }
            } catch { Start-Sleep -Milliseconds 100 }
        }
        if (-not $stratideReady -or $stratideProcess.HasExited) { throw '等待本地服务超时' }
        Write-Host "Dashboard 已启动：$stratideUrl （Ctrl+C 停止）"
        Write-Host "Agent Owner 令牌保存在本机 Agent 目录的 owner-token 文件；在 Agent 管理页解锁。"
        if (-not $NoBrowser) { Start-Process $stratideUrl } # Requested interactive browser.
        while (-not $stratideProcess.HasExited) { Start-Sleep -Milliseconds 250 }
        if ($stratideProcess.ExitCode -ne 0) { throw 'Dashboard 服务已异常退出' }
    } finally {
        # Only the exact child created by this invocation is stopped.
        if (-not $stratideProcess.HasExited) { $stratideProcess.Kill(); $stratideProcess.WaitForExit() }
        $stratideProcess.Dispose()
    }
} finally { Pop-Location }
