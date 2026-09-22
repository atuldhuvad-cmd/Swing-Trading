<#
.SYNOPSIS
  Registers Windows Task Scheduler entries so the on-demand auto-download
  scripts run on their own, without you triggering them by hand or from
  the app's Data Sync screen every time.

.DESCRIPTION
  Run this ONCE yourself, in a normal (non-admin) PowerShell window, from
  anywhere -- it locates the repo root relative to its own location. It is
  safe to re-run: existing tasks with the same name are replaced, nothing
  is duplicated.

  What gets registered, and why:

    SwingTrading-OHLCV-Bhavcopy
      Mon-Fri 19:00 (after NSE market close + typical Bhavcopy publish time)
      Backs up, then IMPORTS into, the production database -- same as
      running scratch\auto_download_ohlcv.py by hand.

    SwingTrading-ICICI-Recs
      Mon-Fri 20:00 -- matches this project's README note that daily is
      the most feasible check frequency for ICICI Direct.
      Download/report only. Never writes to the database.

    SwingTrading-Fundamentals
      15th of Feb, May, Aug, Nov, 09:00 -- you asked for a quarterly
      cadence. Results are typically announced 4-8 weeks after quarter-end,
      so these four fixed dates land roughly mid-results-season for each
      quarter. The script's own 120-day lookback window is a safety
      margin in case a filing is late; adjust the -MonthsOfYear /
      -DaysOfMonth below if your tracked stocks report on a different
      pattern.
      Download/report only. Never writes to the database.

  Each task runs while you are logged in (no stored password, no elevated
  "run whether logged on or not" -- kept simple for personal use) and
  appends to a log file under scratch\logs\, in addition to the timestamped
  JSON report each script already writes on every run.

  To remove these tasks later, run unregister_scheduled_tasks.ps1.

.NOTES
  This script only registers Task Scheduler entries. It does not run any
  of the download scripts itself, and it makes no network calls.
#>

param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot 'backend\venv\Scripts\python.exe'

$OhlcvBat        = Join-Path $PSScriptRoot 'run_ohlcv.bat'
$FundamentalsBat = Join-Path $PSScriptRoot 'run_fundamentals.bat'
$IcicBat         = Join-Path $PSScriptRoot 'run_broker_recs_icici.bat'

foreach ($p in @($VenvPython, $OhlcvBat, $FundamentalsBat, $IcicBat)) {
    if (-not (Test-Path $p)) {
        throw "Expected wrapper script not found: $p -- did you move this file out of scratch\?"
    }
}

Write-Host "Repo root resolved to: $RepoRoot"

if ($ValidateOnly) {
    Write-Host 'Validation passed: project Python and all three wrappers exist.'
    Write-Host 'No scheduled tasks were created or changed.'
    exit 0
}

$CmdExe = Join-Path $env:WINDIR 'System32\cmd.exe'
function New-BatchAction([string]$BatchPath) {
    # Task Scheduler actions need a real executable; cmd.exe reliably launches
    # a .bat even when the repository path contains spaces.
    $quoted = '"' + $BatchPath + '"'
    New-ScheduledTaskAction -Execute $CmdExe -Argument "/d /c $quoted" -WorkingDirectory $RepoRoot
}

$taskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable

# --- SwingTrading-OHLCV-Bhavcopy: Mon-Fri 19:00 -------------------------
$ohlcvAction  = New-BatchAction $OhlcvBat
$ohlcvTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 7:00PM
Register-ScheduledTask -TaskName 'SwingTrading-OHLCV-Bhavcopy' `
    -Action $ohlcvAction -Trigger $ohlcvTrigger -Settings $taskSettings -Force `
    -Description 'Swing Trading: per-symbol OHLCV + daily Bhavcopy download and import (writes to the production DB). See scratch\auto_download_ohlcv.py.' | Out-Null
Write-Host 'Registered: SwingTrading-OHLCV-Bhavcopy (Mon-Fri 19:00)'

# --- SwingTrading-ICICI-Recs: Mon-Fri 20:00 -----------------------------
$icicAction  = New-BatchAction $IcicBat
$icicTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 8:00PM
Register-ScheduledTask -TaskName 'SwingTrading-ICICI-Recs' `
    -Action $icicAction -Trigger $icicTrigger -Settings $taskSettings -Force `
    -Description 'Swing Trading: ICICI Direct broker recommendation discovery (download/report only, no DB writes). See scratch\auto_download_broker_recs_icici.py.' | Out-Null
Write-Host 'Registered: SwingTrading-ICICI-Recs (Mon-Fri 20:00)'

# --- SwingTrading-Fundamentals: 15th of Feb/May/Aug/Nov, 09:00 ---------
$fundAction  = New-BatchAction $FundamentalsBat
$fundTrigger = New-ScheduledTaskTrigger -Monthly -DaysOfMonth 15 `
    -MonthsOfYear February,May,August,November -At 9:00AM
Register-ScheduledTask -TaskName 'SwingTrading-Fundamentals' `
    -Action $fundAction -Trigger $fundTrigger -Settings $taskSettings -Force `
    -Description 'Swing Trading: quarterly fundamentals filing discovery (download/report only, no DB writes). See scratch\auto_download_fundamentals.py.' | Out-Null
Write-Host 'Registered: SwingTrading-Fundamentals (15th of Feb/May/Aug/Nov, 09:00)'

Write-Host ''
Write-Host 'Done. View/edit these anytime in Task Scheduler under Task Scheduler Library (no subfolder).'
Write-Host 'Logs will appear under scratch\logs\ after each run; each script also writes its usual JSON report.'
