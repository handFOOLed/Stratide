#Requires -Version 7.0
<#
.SYNOPSIS
Check a locally built installer payload without installing it or publishing it.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$SourceSha,
  [Parameter(Mandatory = $true)][string]$Version
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$setup = Join-Path $root "dist\installer\Stratide-Setup-$Version-x64.exe"
$sums = Join-Path $root 'dist\installer\SHA256SUMS.txt'
$infoPath = Join-Path $root 'dist\app\BUILD_INFO.json'
$launcher = Join-Path $root 'dist\app\stratide-launcher.exe'
$ico = Join-Path $root 'assets\brand\stratide.ico'
$iss = Join-Path $root 'installer\Stratide.iss'
foreach ($path in @($setup, $sums, $infoPath, $launcher, $ico, $iss)) {
  if (-not (Test-Path -LiteralPath $path)) { throw "MISSING $path" }
}

$info = Get-Content -LiteralPath $infoPath -Raw | ConvertFrom-Json
if ($info.version -ne $Version) { throw "VERSION_MISMATCH $($info.version)" }
if ($info.commit -ne $SourceSha) { throw "COMMIT_MISMATCH $($info.commit)" }
if ($info.commit -like '*-dirty') { throw 'WORKTREE_DIRTY' }
if ($info.paper_only -ne $true -or $info.live_broker -ne $false -or $info.unsigned -ne $true) {
  throw 'BUILD_INFO_BOUNDARY'
}
if ($info.architecture -ne 'x64') { throw "ARCH $($info.architecture)" }

$setupHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $setup).Hash.ToUpperInvariant()
$first = (Get-Content -LiteralPath $sums -TotalCount 1).Trim()
if ($first -notmatch ("^" + [regex]::Escape($setupHash) + "\s+Stratide-Setup-" + [regex]::Escape($Version) + "-x64\.exe$")) {
  throw "SHA256SUMS_MISMATCH $first"
}
$size = (Get-Item -LiteralPath $setup).Length
if ($size -lt 8MB) { throw "INSTALLER_TOO_SMALL $size" }

$issText = Get-Content -LiteralPath $iss -Raw
if ($issText -notmatch 'SetupIconFile=\.\.\\assets\\brand\\stratide\.ico') { throw 'SETUP_ICON_FILE' }
if ($issText -notmatch 'UninstallDisplayIcon=\{app\}\\stratide\.ico') { throw 'UNINSTALL_ICON' }
$iconLines = @(Select-String -LiteralPath $iss -Pattern 'IconFilename:' )
if ($iconLines.Count -lt 1) { throw 'NO_SHORTCUT_ICON' }
foreach ($line in $iconLines) {
  if ($line.Line -notmatch 'IconFilename:\s*"\{app\}\\stratide\.ico"') { throw "SHORTCUT_ICON $($line.Line)" }
}
$buildScript = Get-Content -LiteralPath (Join-Path $root 'scripts\build-windows-installer.ps1') -Raw
if ($buildScript -notmatch 'installer\\Stratide\.iss') { throw 'BUILD_DOES_NOT_USE_ISS' }

Add-Type -TypeDefinition @'
using System;
public static class ByteFind {
  public static bool Contains(byte[] hay, byte[] needle) {
    if (needle.Length == 0 || hay.Length < needle.Length) return false;
    int last = hay.Length - needle.Length;
    for (int i = 0; i <= last; i++) {
      int j = 0;
      for (; j < needle.Length; j++) {
        if (hay[i + j] != needle[j]) break;
      }
      if (j == needle.Length) return true;
    }
    return false;
  }
}
'@

function Get-IcoImages([string]$path) {
  $bytes = [System.IO.File]::ReadAllBytes($path)
  if ($bytes.Length -lt 6) { throw 'ICO_TOO_SMALL' }
  $count = [BitConverter]::ToUInt16($bytes, 4)
  if ($count -lt 1) { throw 'ICO_EMPTY' }
  $images = [System.Collections.Generic.List[byte[]]]::new()
  for ($i = 0; $i -lt $count; $i++) {
    $entry = 6 + ($i * 16)
    $size = [BitConverter]::ToUInt32($bytes, $entry + 8)
    $offset = [BitConverter]::ToUInt32($bytes, $entry + 12)
    if ($size -lt 16 -or ($offset + $size) -gt $bytes.Length) { throw "ICO_IMAGE_OUT_OF_RANGE $i" }
    $image = New-Object byte[] $size
    [Array]::Copy($bytes, $offset, $image, 0, $size)
    $images.Add($image)
  }
  return $images
}

$images = Get-IcoImages $ico
$launcherBytes = [System.IO.File]::ReadAllBytes($launcher)
$setupBytes = [System.IO.File]::ReadAllBytes($setup)
$index = 0
foreach ($image in $images) {
  if (-not [ByteFind]::Contains($launcherBytes, $image)) { throw "LAUNCHER_ICON_MISSING image=$index bytes=$($image.Length)" }
  if (-not [ByteFind]::Contains($setupBytes, $image)) { throw "SETUP_ICON_MISSING image=$index bytes=$($image.Length)" }
  $index += 1
}
# Inno compresses the compiled script, so the shortcut filename may not appear
# as raw text. The IconFilename lines above are the wiring ISCC just compiled,
# and the icon images themselves are already required in the setup executable.
$shortcutUtf16 = [System.Text.Encoding]::Unicode.GetBytes('stratide.ico')
$shortcutAscii = [System.Text.Encoding]::ASCII.GetBytes('stratide.ico')
if ([ByteFind]::Contains($setupBytes, $shortcutUtf16) -or [ByteFind]::Contains($setupBytes, $shortcutAscii)) {
  Write-Host 'SETUP_ICON_NAME present in the installer executable'
} else {
  Write-Host 'SETUP_ICON_NAME is compressed in the installer; shortcut targets were checked in installer/Stratide.iss'
}

Write-Host "INSTALLER_SHA256 $setupHash"
Write-Host "INSTALLER_BYTES $size"
Write-Host "COMMIT $($info.commit)"
Write-Host "VERSION $($info.version)"
Write-Host "ICON_IMAGES $index"
Write-Host 'Identity check passed. Installer was not executed and was not published.'
