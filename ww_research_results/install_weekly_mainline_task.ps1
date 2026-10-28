param(
    [string]$Python = "python",
    [string]$TaskName = "WW Weekly Mainline Snapshot and Research Queue"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\run_weekly_mainline_task.ps1`" -Python `"$Python`"" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 8:00PM
$trigger.StartBoundary = [DateTime]::Now.Date.AddDays(((1 - [int][DateTime]::Now.DayOfWeek + 7) % 7)).AddHours(20).ToString("yyyy-MM-dd'T'HH:mm:ssK")
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Every Monday, create the prior completed week's point-in-time bounded A-share market snapshot and manual research queue." -Force | Out-Null
Write-Output "Installed task '$TaskName' for Mondays at 20:00 local time. Set TUSHARE_TOKEN in the task user's environment before running it. The task creates a snapshot and research queue; it does not automatically write a researched mainline conclusion."
