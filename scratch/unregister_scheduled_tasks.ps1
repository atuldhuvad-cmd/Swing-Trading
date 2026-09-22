<#
.SYNOPSIS
  Removes the three Task Scheduler entries created by
  register_scheduled_tasks.ps1. Safe to run even if some/none exist.
#>

$Names = @('SwingTrading-OHLCV-Bhavcopy', 'SwingTrading-ICICI-Recs', 'SwingTrading-Fundamentals')

foreach ($name in $Names) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "Removed: $name"
    } else {
        Write-Host "Not found (already removed?): $name"
    }
}
