#Requires -Version 7.0
<#
.SYNOPSIS
Local Windows product E2E: single instance, health, stop, port conflict, crash recovery.
.DESCRIPTION
Runs the already-built payload in dist\app against an isolated home under state\.
It makes no Tushare, DeepSeek or market request and creates no Paper order.
Use -InstallTest to also compile and run the sandbox-compatible installer variant
(same [Files]/[Code] as the real installer, icons/registry omitted).
#>
[CmdletBinding()]
param(
  [string]$AppDir,
  [string]$RootHome = '',
  [int]$Port = 8799,
  [switch]$InstallTest,
  [string]$Iscc = ''
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
if (-not $AppDir) { $AppDir = Join-Path $root 'dist\app' }
if (-not $RootHome) { $RootHome = Join-Path $root ('state\issue85-test\e2e-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$launcher = Join-Path $AppDir 'stratide-launcher.exe'
$failures = 0
function Check([string]$name, [bool]$ok, [string]$detail = '') {
  if ($ok) { Write-Host "PASS $name $detail" } else { Write-Host "FAIL $name $detail"; $script:failures += 1 }
}
function Run-Launcher([string[]]$arguments, [int]$timeout = 90000) {
  $process = Start-Process -FilePath $launcher -ArgumentList $arguments -PassThru
  $null = $process.WaitForExit($timeout)
  $process.Refresh()
  return $process
}
function Stop-Product {
  Get-Process | Where-Object { $_.ProcessName -like 'stratide*' } | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Milliseconds 300
}
function Read-Health {
  try { return Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3 } catch { return $null }
}
Stop-Product
if (Test-Path $RootHome) { Remove-Item -Recurse -Force $RootHome }
New-Item -ItemType Directory -Force -Path $RootHome | Out-Null
$env:STRATIDE_HOME = $RootHome
$data = Join-Path $RootHome 'data'

$configure = Run-Launcher @('--configure','--port',$Port.ToString(),'--data-dir',$data,'--quiet') 30000
Check 'configure' ($configure.ExitCode -eq 0) "exit=$($configure.ExitCode) home=$RootHome"
Check 'config-bom-free' (([IO.File]::ReadAllBytes((Join-Path $RootHome 'runtime.json')))[0] -eq 123)

$start = Run-Launcher @('--no-browser','--quiet')
Check 'first-launch' ($start.ExitCode -eq 0) "exit=$($start.ExitCode)"
$health = Read-Health
Check 'health' ($null -ne $health -and $health.data.service -eq 'online') ''
$firstPid = $health.data.process_id
$second = Run-Launcher @('--no-browser','--quiet') 30000
$health2 = Read-Health
Check 'second-launch-same-instance' ($second.ExitCode -eq 0 -and $health2.data.instance_id -eq $health.data.instance_id) ''
Check 'single-dashboard' ((@(Get-Process stratided -ErrorAction SilentlyContinue)).Count -eq 1) ''

$status = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/runtime/status" -TimeoutSec 20
Check 'runtime-status' ($status.data.managed -eq $true -and $status.data.product_version -ne '') "version=$($status.data.product_version) python=$($status.data.dependencies.python.state)"
Check 'runtime-token-removed' (-not (Test-Path (Join-Path $RootHome 'runtime\runtime-token'))) ''
try {
  $noOrigin = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/runtime/setup-complete" -Method Post -Headers @{'Content-Type'='application/json'} -Body '{}' -TimeoutSec 10
  Check 'runtime-write-requires-origin' $false "status=$($noOrigin.StatusCode)"
} catch {
  Check 'runtime-write-requires-origin' ($_.Exception.Response.StatusCode.value__ -eq 403) "status=$($_.Exception.Response.StatusCode.value__)"
}

$writeHeaders = @{'Origin'="http://127.0.0.1:$Port"; 'Content-Type'='application/json'}
$wslBody = '{"distribution":"Stratide-NoSuchDistro","workspace":"/tmp/stratide-none","python":".venv/bin/python","model":"models/timesfm-2.5"}'
$wslFirst = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/runtime/wsl" -Method Post -Headers $writeHeaders -Body $wslBody -TimeoutSec 20
Check 'wsl-config-saved' ($wslFirst.data.state -eq 'CONFIGURED' -and $wslFirst.data.watch_restart -eq $true -and $wslFirst.data.wsl.distribution -eq 'Stratide-NoSuchDistro') "restart=$($wslFirst.data.watch_restart)"
$wslSecond = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/runtime/wsl" -Method Post -Headers $writeHeaders -Body $wslBody -TimeoutSec 20
Check 'wsl-unchanged-no-restart' ($wslSecond.data.watch_restart -eq $false) "restart=$($wslSecond.data.watch_restart)"
$wslStored = (Get-Content (Join-Path $RootHome 'runtime.json') -Raw | ConvertFrom-Json).wsl
Check 'wsl-config-persisted' ($wslStored.distribution -eq 'Stratide-NoSuchDistro' -and $wslStored.workspace -eq '/tmp/stratide-none') ''
$probe = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/runtime/wsl-probe" -Method Post -Headers $writeHeaders -Body '{}' -TimeoutSec 120
Check 'wsl-probe-blocks-unknown-distro' ($probe.data.state -eq 'BLOCKED') "state=$($probe.data.state) reason=$($probe.data.reason)"

$stop = Run-Launcher @('--stop','--quiet') 60000
Check 'stop' ($stop.ExitCode -eq 0 -and $null -eq (Read-Health)) "exit=$($stop.ExitCode)"
Check 'no-leftovers-after-stop' ((@(Get-Process | Where-Object { $_.ProcessName -like 'stratide*' })).Count -eq 0) ''

$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
$listener.Start()
$conflict = Run-Launcher @('--no-browser','--quiet') 15000
$listener.Stop()
Check 'port-conflict-refused' ($conflict.ExitCode -eq 2) "exit=$($conflict.ExitCode)"
Check 'no-service-on-foreign-port' ($null -eq (Read-Health)) ''

$restart = Run-Launcher @('--no-browser','--quiet')
$health = Read-Health
Check 'restart-after-stop' ($restart.ExitCode -eq 0 -and $null -ne $health) ''
$supervisor = (Get-Content (Join-Path $RootHome 'runtime\supervisor.json') -Raw | ConvertFrom-Json)
Stop-Process -Id ([int]$health.data.process_id) -Force
Start-Sleep -Seconds 13
$recovered = Read-Health
Check 'dashboard-auto-restart' ($null -ne $recovered -and $recovered.data.process_id -ne $health.data.process_id) ''
Check 'one-dashboard-after-restart' ((@(Get-Process stratided -ErrorAction SilentlyContinue)).Count -eq 1) ''
$supervisor = (Get-Content (Join-Path $RootHome 'runtime\supervisor.json') -Raw | ConvertFrom-Json)
Stop-Process -Id ([int]$supervisor.supervisor_pid) -Force
Start-Sleep -Seconds 3
Check 'job-kills-children' ((@(Get-Process | Where-Object { $_.ProcessName -like 'stratide*' })).Count -eq 0) ''
Check 'health-down-after-supervisor-kill' ($null -eq (Read-Health)) ''

$again = Run-Launcher @('--no-browser','--quiet')
Check 'restart-after-supervisor-crash' ($again.ExitCode -eq 0 -and $null -ne (Read-Health)) ''
Set-Content -LiteralPath (Join-Path $data 'preserve.txt') -Value 'survives-upgrade' -Encoding UTF8
$stop = Run-Launcher @('--stop','--quiet') 60000
$before = Get-Content (Join-Path $RootHome 'runtime.json') -Raw
Set-Content -LiteralPath (Join-Path $AppDir 'VERSION') -Value '0.3.1-test' -Encoding Ascii
$after = Run-Launcher @('--no-browser','--quiet')
$health = Read-Health
Check 'upgrade-simulation-restart' ($after.ExitCode -eq 0 -and $null -ne $health) ''
Check 'config-preserved' ($before -eq (Get-Content (Join-Path $RootHome 'runtime.json') -Raw)) ''
Check 'data-preserved' ((Get-Content (Join-Path $data 'preserve.txt') -Raw).Trim() -eq 'survives-upgrade') ''
Set-Content -LiteralPath (Join-Path $AppDir 'VERSION') -Value '0.3.0' -Encoding Ascii
$null = Run-Launcher @('--stop','--quiet') 60000

if ($InstallTest) {
  if (-not $Iscc) {
    $candidates = @((Join-Path $root '..\.tools\InnoSetup\ISCC.exe'), (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'))
    $Iscc = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  }
  if (-not $Iscc) { throw 'ISCC_NOT_FOUND' }
  Remove-Item Env:STRATIDE_HOME -ErrorAction SilentlyContinue
  $setupDir = Join-Path $root 'state\issue85-test\installer-test'
  if (Test-Path $setupDir) { Remove-Item -Recurse -Force $setupDir }
  New-Item -ItemType Directory -Force -Path $setupDir | Out-Null
  & $Iscc '/DTestMode=1' '/DAppVersion=0.3.0' ("/DSourceDir=$AppDir") ("/DOutputDir=$setupDir") (Join-Path $root 'installer\Stratide.iss')
  if ($LASTEXITCODE -ne 0) { throw 'TEST_INSTALLER_COMPILE_FAILED' }
  $setup = Join-Path $setupDir 'Stratide-Setup-0.3.0-x64.exe'
  $installDir = Join-Path $RootHome 'installed\app'
  $installHome = Join-Path $RootHome 'installed\home'
  $installData = Join-Path $RootHome 'installed\data'
  $process = Start-Process -FilePath $setup -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',"/DIR=$installDir","/HOME=$installHome","/DATA=$installData" -PassThru
  $exited = $process.WaitForExit(120000)
  Check 'installer-test-install' ($exited -and $process.ExitCode -eq 0) "exit=$($process.ExitCode)"
  Check 'installer-test-config' (Test-Path (Join-Path $installHome 'runtime.json')) ''
  Check 'installer-test-files' ((@(Get-ChildItem $installDir -Recurse -File)).Count -gt 100) ''
}
Write-Host ''
if ($failures -eq 0) { Write-Host 'RESULT PASS'; exit 0 }
Write-Host "RESULT FAIL ($failures)"; exit 1