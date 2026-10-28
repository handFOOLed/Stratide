# Foreground helper only. No service, scheduled task, token persistence or backfill.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Journal,
    [Parameter(Mandatory = $true)][string]$Reports,
    [string]$Cli = (Join-Path $PSScriptRoot '../target/debug/stratide-cli.exe'),
    [switch]$Watch,
    [ValidateRange(1, 31)][int]$MaxDays = 5
)
$ErrorActionPreference = 'Stop'
$stratideCliPath = (Resolve-Path -LiteralPath $Cli).Path
$stratideJournalPath = (Resolve-Path -LiteralPath $Journal).Path
$stratideReportsPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Reports)
$stratideLastDay = $null
$stratideDays = 0
do {
    $stratideLocal = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8))
    $stratideDay = $stratideLocal.ToString('yyyyMMdd')
    if (-not $Watch -or ($stratideLocal.Hour -ge 16 -and $stratideDay -ne $stratideLastDay)) {
        & $stratideCliPath forward-eod-step $stratideJournalPath $stratideReportsPath
        if ($LASTEXITCODE -ne 0) {
            throw 'EOD step failed; diagnostics retained. Inspect status/report, then explicitly retry with forward-collect-once.'
        }
        $stratideLastDay = $stratideDay
        $stratideDays += 1
    }
    if (-not $Watch -or $stratideDays -ge $MaxDays) { break }
    # Checking the wall clock is local only; at most one CLI step per date here.
    Start-Sleep -Seconds 60
} while ($true)
