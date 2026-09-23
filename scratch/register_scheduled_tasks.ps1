<#
.SYNOPSIS
  Registers or updates ONE named Swing Trading Task Scheduler entry.

.DESCRIPTION
  Nothing is registered implicitly. You must choose the task and confirm:

    -Task ICICI          SwingTrading-ICICI-Recs        Mon-Fri 20:00, 30 minute limit
    -Task OHLCV          SwingTrading-OHLCV-Bhavcopy    Mon-Fri 19:00, 120 minute limit
    -Task Fundamentals   SwingTrading-Fundamentals      previewable only: this script cannot register it
                         (no -Monthly trigger support here); 60 minute limit
    -Task All            all three; refused while Fundamentals is included
                         (still needs -ConfirmRegistration)

  Selecting one task never touches the others. Task Scheduler is changed only
  when -ConfirmRegistration is given; if the task already exists its definition
  is replaced (only that one task). Without the confirmation switch the script
  refuses and changes nothing.

  Non-mutating modes (no scheduled task is created or changed):
    -WhatIf         shows exactly what would be registered, including whether it
                    would create or replace a task, then exits 0.
    -ValidateOnly   checks paths and builds the definitions, then exits 0.
                    -Task is optional here (defaults to All).

  Every task: runs its committed wrapper through cmd.exe with the path quoted and
  the project folder as working directory, has a bounded execution limit, never
  overlaps itself (MultipleInstances = IgnoreNew), and stores no password or
  credential (it runs as the registering user, interactively). Wrappers return
  the script's exit code, so a failed run is a non-zero task result.

  Definitions live in scheduled_task_definitions.ps1 (pure, testable). Run this
  from the authoritative checkout D:\Swing Trading only; any other folder is
  refused. To remove tasks later, run unregister_scheduled_tasks.ps1.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File 'D:\Swing Trading\scratch\register_scheduled_tasks.ps1' -Task ICICI -WhatIf

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File 'D:\Swing Trading\scratch\register_scheduled_tasks.ps1' -Task ICICI -ConfirmRegistration

.NOTES
  Makes no network calls and runs none of the download scripts.
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'None')]
param(
    [ValidateSet('ICICI', 'OHLCV', 'Fundamentals', 'All')]
    [string]$Task,
    [switch]$ConfirmRegistration,
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
# Remember a preview request, then keep -WhatIf out of the in-memory builders and read-only queries.
$previewOnly = [bool]$WhatIfPreference
$WhatIfPreference = $false
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot 'backend\venv\Scripts\python.exe'

. (Join-Path $PSScriptRoot 'scheduled_task_definitions.ps1')

if ((Split-Path $RepoRoot -Leaf) -ne 'Swing Trading') {
    [Console]::Error.WriteLine("Refusing to run from '$RepoRoot': tasks must be registered from the authoritative checkout 'D:\Swing Trading'.")
    exit 2
}

if (-not $Task) {
    if ($ValidateOnly) {
        $Task = 'All'
    } else {
        [Console]::Error.WriteLine("Specify -Task ICICI, OHLCV, Fundamentals or All. Nothing is registered implicitly.")
        exit 2
    }
}

$selected = @(Select-SwingTasks -RepoRoot $RepoRoot -Task $Task)

foreach ($p in @($VenvPython) + @($selected | ForEach-Object { $_.Wrapper })) {
    if (-not (Test-Path -LiteralPath $p)) {
        throw "Expected file not found: $p -- did you move this file out of scratch\?"
    }
}

Write-Host "Repo root resolved to: $RepoRoot"
Write-Host "Selected task(s): $((@($selected | ForEach-Object { $_.TaskName })) -join ', ')"
foreach ($d in $selected) {
    $s = Get-SwingTaskSummary -Definition $d
    $existing = Get-ScheduledTask -TaskName $d.TaskName -ErrorAction SilentlyContinue
    $state = if ($d.Unsupported) { 'NOT REGISTERABLE BY THIS SCRIPT' } elseif ($existing) { 'EXISTS - would be replaced' } else { 'not registered - would be created' }
    Write-Host ''
    Write-Host ("  {0}  [{1}]" -f $s.TaskName, $state)
    Write-Host ("    Action:     {0} {1}" -f $s.Execute, $s.Arguments)
    Write-Host ("    Working:    {0}" -f $s.WorkingDirectory)
    Write-Host ("    Trigger:    {0}" -f $s.Trigger)
    Write-Host ("    Limit:      {0} minutes" -f $s.LimitMinutes)
    Write-Host ("    Overlap:    {0}; StartWhenAvailable={1}" -f $s.MultipleInstances, $s.StartWhenAvailable)
    Write-Host '    Credentials: none stored (runs as the registering user, interactively)'
    if ($d.Unsupported) { Write-Host ('    Reason:     ' + $d.Unsupported) }
}
Write-Host ''

if ($ValidateOnly -or $previewOnly) {
    Write-Host 'Validation passed. No scheduled tasks were created or changed.'
    exit 0
}

if (-not $ConfirmRegistration) {
    [Console]::Error.WriteLine('Refused: pass -ConfirmRegistration to modify Task Scheduler (or -WhatIf / -ValidateOnly to preview). No scheduled tasks were created or changed.')
    exit 2
}

$blocked = @($selected | Where-Object { $_.Unsupported })
if ($blocked.Count -gt 0) {
    [Console]::Error.WriteLine('Refused: ' + ((@($blocked | ForEach-Object { $_.TaskName })) -join ', ') + ' cannot be registered by this script (see the reason above). Nothing was changed; select -Task ICICI or -Task OHLCV instead.')
    exit 2
}

foreach ($d in $selected) {
    $params = @{
        TaskName    = $d.TaskName
        Action      = $d.Action
        Trigger     = $d.Trigger
        Settings    = $d.Settings
        Description = $d.Description
    }
    if (Get-ScheduledTask -TaskName $d.TaskName -ErrorAction SilentlyContinue) { $params['Force'] = $true }
    Register-ScheduledTask @params | Out-Null
    Write-Host (Get-SwingRegisteredMessage -Definition $d)
}
Write-Host ''
Write-Host 'Done. Logs appear under scratch\logs\ after each run; each script also writes its usual JSON report.'
exit 0
