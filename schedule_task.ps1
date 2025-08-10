# PowerShell script to create a scheduled task for the newspaper downloader

# Configuration
$taskName = "DailyNewspaperDownloader"
$taskDescription = "Downloads the daily newspaper and emails it to the configured recipients"
$scriptPath = Join-Path $PSScriptRoot "run_newspaper.ps1"

# Create the run_newspaper.ps1 script that will be executed by the scheduled task
$runScriptContent = @"
# PowerShell script to run the newspaper downloader
`$ErrorActionPreference = 'Stop'
`$scriptDir = Split-Path -Parent `$MyInvocation.MyCommand.Path
`$pythonScript = Join-Path `$scriptDir "main.py"
python "`$pythonScript" @args
"@

# Write the run script to disk
$runScriptContent | Out-File -FilePath $scriptPath -Encoding utf8

Write-Host "Created run script at: $scriptPath"

# Get the current username for the principal
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

# Create a scheduled task action
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

# Create a scheduled task trigger (runs daily at 6:00 AM)
$trigger = New-ScheduledTaskTrigger -Daily -At 6am

# Create a scheduled task settings
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

# Register the scheduled task (will prompt for password if needed)
Register-ScheduledTask -TaskName $taskName -Description $taskDescription -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -User $currentUser -Force

Write-Host "Scheduled task '$taskName' created successfully."
Write-Host "The task will run daily at 6:00 AM."
Write-Host "You can modify the scheduled task in Task Scheduler if needed." 