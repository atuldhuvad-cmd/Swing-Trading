<#
.SYNOPSIS
  Pure definitions of the Swing Trading Task Scheduler entries.

.DESCRIPTION
  Dot-source this file to get the definitions. Nothing here registers, changes,
  disables or deletes a scheduled task: every function only builds in-memory
  objects, so the definitions can be tested without touching the live scheduler.
  register_scheduled_tasks.ps1 is the only place that mutates Task Scheduler.

  Each task is built on its own, so selecting one task never depends on how any
  other task is defined.

  Every task has:
    * an action that runs its committed wrapper through cmd.exe with the path
      quoted and the project folder as the working directory;
    * a bounded execution limit (ICICI: 30 minutes);
    * MultipleInstances = IgnoreNew, so a run never overlaps another run;
    * no principal, password or credential: the task runs as the registering
      user, interactively.
#>

Set-StrictMode -Version Latest

function Get-SwingTaskKeys {
    return @('ICICI', 'OHLCV', 'Fundamentals')
}

function New-SwingDefinition {
    param($RepoRoot, $Key, $Name, $WrapperName, $Trigger, $TriggerText, [int]$LimitMinutes, $Description, $Unsupported = $null)
    $cmd = Join-Path $env:WINDIR 'System32\cmd.exe'
    $wrapper = Join-Path (Join-Path $RepoRoot 'scratch') $WrapperName
    [pscustomobject]@{
        Key         = $Key
        TaskName    = $Name
        Wrapper     = $wrapper
        Action      = New-ScheduledTaskAction -Execute $cmd -Argument ('/d /c "' + $wrapper + '"') -WorkingDirectory $RepoRoot
        Trigger     = $Trigger
        TriggerText = $TriggerText
        Settings    = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
                          -ExecutionTimeLimit (New-TimeSpan -Minutes $LimitMinutes)
        Description = $Description
        # Non-null means this script refuses to register the task (reason given).
        Unsupported = $Unsupported
    }
}

function Get-SwingTaskDefinition {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Key
    )
    # Building definitions is in-memory only, so a caller's -WhatIf must not leak into it.
    $WhatIfPreference = $false
    $weekdays = @('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')
    switch ($Key) {
        'ICICI' {
            return New-SwingDefinition $RepoRoot 'ICICI' 'SwingTrading-ICICI-Recs' 'run_broker_recs_icici.bat' `
                (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At 8:00PM) 'Mon-Fri 20:00' 30 `
                'Swing Trading: ICICI Direct broker recommendation download + auto-import for tracked stocks (backs up the database first). See scratch\auto_download_broker_recs_icici.py.'
        }
        'OHLCV' {
            return New-SwingDefinition $RepoRoot 'OHLCV' 'SwingTrading-OHLCV-Bhavcopy' 'run_ohlcv.bat' `
                (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At 7:00PM) 'Mon-Fri 19:00' 120 `
                'Swing Trading: per-symbol OHLCV + daily Bhavcopy download and import (writes to the production DB). See scratch\auto_download_ohlcv.py.'
        }
        'Fundamentals' {
            return New-SwingDefinition $RepoRoot 'Fundamentals' 'SwingTrading-Fundamentals' 'run_fundamentals.bat' `
                $null '15th of Feb/May/Aug/Nov 09:00' 60 `
                'Swing Trading: quarterly fundamentals filing discovery (download/report only, no DB writes). See scratch\auto_download_fundamentals.py.' `
                'Monthly triggers cannot be built with the ScheduledTasks module installed here (New-ScheduledTaskTrigger has no -Monthly, and a monthly CIM trigger cannot be verified without registering a task). Register this task by hand in Task Scheduler.'
        }
        default {
            throw ("Unknown task selection '{0}'. Valid choices: {1}, All." -f $Key, ((Get-SwingTaskKeys) -join ', '))
        }
    }
}

function Select-SwingTasks {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Task
    )
    $keys = if ($Task -eq 'All') { Get-SwingTaskKeys } else { @($Task) }
    return @($keys | ForEach-Object { Get-SwingTaskDefinition -RepoRoot $RepoRoot -Key $_ })
}

function Get-SwingTaskSummary {
    param([Parameter(Mandatory = $true)]$Definition)
    $trigger = $Definition.Trigger
    $summary = [ordered]@{
        Key                = $Definition.Key
        TaskName           = $Definition.TaskName
        Wrapper            = $Definition.Wrapper
        Execute            = $Definition.Action.Execute
        Arguments          = $Definition.Action.Arguments
        WorkingDirectory   = $Definition.Action.WorkingDirectory
        Trigger            = $Definition.TriggerText
        StartTime          = if ($trigger) { ([datetime]$trigger.StartBoundary).ToString('HH:mm', [System.Globalization.CultureInfo]::InvariantCulture) } else { $null }
        DaysOfWeek         = if ($trigger -and $trigger.PSObject.Properties['DaysOfWeek']) { [int]$trigger.DaysOfWeek } else { $null }
        LimitMinutes       = [int][System.Xml.XmlConvert]::ToTimeSpan([string]$Definition.Settings.ExecutionTimeLimit).TotalMinutes
        MultipleInstances  = [string]$Definition.Settings.MultipleInstances
        StartWhenAvailable = [bool]$Definition.Settings.StartWhenAvailable
        HasPrincipal       = [bool]$Definition.PSObject.Properties['Principal']
        Description        = $Definition.Description
        Unsupported        = $Definition.Unsupported
    }
    return [pscustomobject]$summary
}
