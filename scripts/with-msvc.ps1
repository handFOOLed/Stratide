# Run from the repository root. Uses an existing VS C++ toolchain; installs nothing.
$ErrorActionPreference = 'Stop'
$stratideVswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$stratideVsRoot = & $stratideVswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $stratideVsRoot) {
    $stratideVsRoot = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/2022/BuildTools'
}
$stratideVcvars = Join-Path $stratideVsRoot 'VC/Auxiliary/Build/vcvars64.bat'
$stratideToolEnv = & cmd.exe /d /c "`"$stratideVcvars`" >nul && set"
if ($LASTEXITCODE -ne 0) { throw 'MSVC environment initialization failed' }
foreach ($stratideEnvLine in $stratideToolEnv) {
    if ($stratideEnvLine -match '^([^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}
& cargo @args
exit $LASTEXITCODE
