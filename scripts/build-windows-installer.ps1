#Requires -Version 7.0
<#
.SYNOPSIS
Build the Windows payload and the Inno Setup installer for Stratide.

.DESCRIPTION
Does not touch user data, credentials or WSL2. Produces
dist\installer\Stratide-Setup-<version>-x64.exe and SHA256SUMS.txt.

Build dependencies (pinned by the companion fetch script):
  * Inno Setup 6.7.4 compiler (ISCC.exe)
  * CPython 3.12.10 embeddable AMD64 archive
  * tzdata 2026.6 wheel (zoneinfo data for Windows)
See docs/WINDOWS_INSTALL.md for a clean-machine build walkthrough.
#>
[CmdletBinding()]
param(
  [string]$Version = '0.3.2',
  [switch]$SkipBuild,
  [string]$Iscc,
  [string]$PythonEmbedZip,
  [string]$TzdataWheel
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
$distRoot = Join-Path $root 'dist'
$payload = Join-Path $distRoot 'app'
$installerOut = Join-Path $distRoot 'installer'

function Find-Tool([string]$explicit, [string]$envName, [string[]]$candidates, [string]$description) {
  $path = $null
  if ($explicit) {
    $path = $explicit
  } elseif ($envName) {
    $path = [Environment]::GetEnvironmentVariable($envName)
  }
  if (-not $path) {
    $path = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
  }
  if (-not $path -or -not (Test-Path -LiteralPath $path)) {
    throw "MISSING_BUILD_DEPENDENCY: $description. See docs/WINDOWS_INSTALL.md. Tried: $($candidates -join '; ')"
  }
  return (Resolve-Path -LiteralPath $path).Path
}

$programFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
$localPrograms = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
$isccPath = Find-Tool $Iscc 'ISCC_EXE' @(
  (Join-Path $root '..\.tools\InnoSetup\ISCC.exe'),
  $localPrograms,
  (Join-Path $programFilesX86 'Inno Setup 6\ISCC.exe')
) 'Inno Setup 6 ISCC.exe'
$pythonZip = Find-Tool $PythonEmbedZip 'PYTHON_EMBED_ZIP' @(
  (Join-Path $root '..\.tools\python-embed.zip')
) 'python-3.12.10-embed-amd64.zip'
$tzdataFile = Find-Tool $TzdataWheel 'TZDATA_WHEEL' @(
  (Join-Path $root '..\.tools\tzdata.whl')
) 'tzdata wheel'

if ((Split-Path -Leaf $pythonZip) -eq 'python-embed.zip') {
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $pythonZip).Hash
  if ($hash -ne '4ACBED6DD1C744B0376E3B1CF57CE906F9DC9E95E68824584C8099A63025A3C3') {
    throw "PYTHON_EMBED_HASH_MISMATCH: $hash"
  }
}
if ((Split-Path -Leaf $tzdataFile) -eq 'tzdata.whl') {
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $tzdataFile).Hash
  if ($hash -ne '0A10EEC6E13EF16B627FABED9A5F2BA61A62B1C67F327305F4E7E412A70B4AEC') {
    throw "TZDATA_HASH_MISMATCH: $hash"
  }
}

if (-not $SkipBuild) {
  Write-Host 'Building Rust release binaries...'
  & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'with-msvc.ps1') build --release --locked -p stratided -p stratide-cli -p stratide-launcher -p stratide-research --bins
  if ($LASTEXITCODE -ne 0) { throw 'RUST_RELEASE_BUILD_FAILED' }
  Write-Host 'Building Dashboard...'
  & cmd.exe /d /c "npm.cmd --prefix apps/dashboard ci --ignore-scripts --no-audit --no-fund && npm.cmd --prefix apps/dashboard run build"
  if ($LASTEXITCODE -ne 0) { throw 'DASHBOARD_BUILD_FAILED' }
}

Write-Host 'Assembling payload...'
if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Recurse -Force }
if (Test-Path -LiteralPath $installerOut) { Remove-Item -LiteralPath $installerOut -Recurse -Force }
foreach ($directory in @($payload, (Join-Path $payload 'bin'), (Join-Path $payload 'dashboard'), (Join-Path $payload 'scripts'), (Join-Path $payload 'research'), (Join-Path $payload 'runtime\python'), (Join-Path $payload 'docs'), $installerOut)) {
  New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

$release = Join-Path $root 'target\release'
foreach ($name in @('stratided.exe', 'stratide-cli.exe', 'stratide-launcher.exe')) {
  $source = Join-Path $release $name
  if (-not (Test-Path -LiteralPath $source)) { throw "MISSING_RELEASE_BINARY: $name" }
  Copy-Item -LiteralPath $source -Destination $payload
}
foreach ($name in @('stratide-cli.exe', 'market-research-agent.exe', 'risk-portfolio-agent.exe', 'timesfm-risk-agent.exe')) {
  $source = Join-Path $release $name
  if (-not (Test-Path -LiteralPath $source)) { throw "MISSING_RELEASE_BINARY: $name" }
  Copy-Item -LiteralPath $source -Destination (Join-Path $payload 'bin')
}
Copy-Item -Path (Join-Path $root 'apps\dashboard\dist\*') -Destination (Join-Path $payload 'dashboard') -Recurse -Force

foreach ($file in Get-ChildItem -LiteralPath (Join-Path $root 'scripts') -File -Filter '*.py') {
  Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $payload 'scripts')
}
Get-ChildItem -LiteralPath (Join-Path $root 'research') -Recurse -File | Where-Object {
  $_.FullName -notmatch '__pycache__' -and $_.FullName -notmatch '\\research\\agent\\'
} | ForEach-Object {
  $relative = $_.FullName.Substring((Join-Path $root 'research').Length).TrimStart('\')
  $target = Join-Path (Join-Path $payload 'research') $relative
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
  Copy-Item -LiteralPath $_.FullName -Destination $target
}
foreach ($doc in @('WINDOWS_INSTALL.md', 'M3_PR04.md')) {
  $source = Join-Path $root "docs\$doc"
  if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $payload 'docs') }
}

& tar.exe -xf $pythonZip -C (Join-Path $payload 'runtime\python')
if ($LASTEXITCODE -ne 0) { throw 'PYTHON_EMBED_EXTRACT_FAILED' }
$pth = Join-Path $payload 'runtime\python\python312._pth'
@('python312.zip', '.', 'Lib\site-packages', 'import site') | Set-Content -LiteralPath $pth -Encoding Ascii
New-Item -ItemType Directory -Force -Path (Join-Path $payload 'runtime\python\Lib\site-packages') | Out-Null
& tar.exe -xf $tzdataFile -C (Join-Path $payload 'runtime\python\Lib\site-packages')
if ($LASTEXITCODE -ne 0) { throw 'TZDATA_EXTRACT_FAILED' }

Set-Content -LiteralPath (Join-Path $payload 'VERSION') -Value $Version -Encoding Ascii
$notices = Join-Path $PSScriptRoot '..\installer\THIRD_PARTY_NOTICES.md'
if (Test-Path -LiteralPath $notices) { Copy-Item -LiteralPath $notices -Destination (Join-Path $payload 'THIRD_PARTY_NOTICES.md') }

$pythonVersion = (& (Join-Path $payload 'runtime\python\python.exe') -c "import sys;print(sys.version.split()[0])").Trim()
if ($LASTEXITCODE -ne 0) { throw 'BUNDLED_PYTHON_SMOKE_FAILED' }
$commit = (git -C $root rev-parse HEAD).Trim()
$dirty = if ((git -C $root status --porcelain)) { '-dirty' } else { '' }
$innoInfo = (Get-Item -LiteralPath $isccPath).VersionInfo
$innoVersion = [string]$innoInfo.ProductVersion
if ([string]::IsNullOrWhiteSpace($innoVersion) -or $innoVersion.Trim() -eq '0.0.0.0') {
  $innoVersion = [string]$innoInfo.FileVersion
}
$innoVersion = $innoVersion.Trim()
$buildInfo = [ordered]@{
  product = 'Stratide'
  version = $Version
  commit = "$commit$dirty"
  built_at = (Get-Date).ToUniversalTime().ToString('o')
  python = $pythonVersion
  architecture = 'x64'
  inno_setup = $innoVersion
  paper_only = $true
  live_broker = $false
  unsigned = $true
}
$buildInfo | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $payload 'BUILD_INFO.json') -Encoding UTF8

$iss = Join-Path $PSScriptRoot '..\installer\Stratide.iss'
Write-Host "Compiling installer with $isccPath ..."
& $isccPath "/DAppVersion=$Version" "/DSourceDir=$payload" "/DOutputDir=$installerOut" $iss
if ($LASTEXITCODE -ne 0) { throw "INNO_COMPILE_FAILED exit=$LASTEXITCODE" }

$setup = Join-Path $installerOut ("Stratide-Setup-$Version-x64.exe")
if (-not (Test-Path -LiteralPath $setup)) { throw 'INSTALLER_NOT_PRODUCED' }
$setupHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $setup).Hash
$serverHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $payload 'stratided.exe')).Hash
$launcherHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $payload 'stratide-launcher.exe')).Hash
$pythonHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $payload 'runtime\python\python.exe')).Hash
$lines = @(
  "$setupHash  $(Split-Path -Leaf $setup)",
  "$serverHash  stratided.exe",
  "$launcherHash  stratide-launcher.exe",
  "$pythonHash  runtime/python/python.exe"
)
$lines | Set-Content -LiteralPath (Join-Path $installerOut 'SHA256SUMS.txt') -Encoding Ascii
Copy-Item -LiteralPath (Join-Path $installerOut 'SHA256SUMS.txt') -Destination (Join-Path $payload 'SHA256SUMS.txt')
Write-Host ''
Write-Host "Installer: $setup"
Write-Host "SHA256:    $setupHash"
Write-Host "Version:   $Version"
Write-Host 'Paper-only. No broker, model download or credential is included.'
