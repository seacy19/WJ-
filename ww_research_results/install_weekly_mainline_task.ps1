param(
    [string]$Python = "python",
    [string]$TaskName = "WJ Strategy Weekly Mainline Snapshot"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runner = Join-Path $PSScriptRoot "weekly_mainline_runner.py"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\run_weekly_mainline_task.ps1`" -Python `"$Python`"" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At 4:10PM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "After Friday close, create a point-in-time bounded A-share weekly market snapshot and manual research queue." -Force | Out-Null
Write-Output "Installed task '$TaskName' for Fridays at 16:10 local time. Set TUSHARE_TOKEN in the task user's environment before running it. The task creates a snapshot and research queue; it does not automatically write a researched mainline conclusion."
