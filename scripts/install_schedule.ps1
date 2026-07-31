# Register the weekly local pipeline run with Windows Task Scheduler.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_schedule.ps1
#
# Runs `job-finder run --email` every Monday at 09:00 local time. If the
# machine is off at that moment, StartWhenAvailable runs it at next boot, so
# a powered-down Monday costs lead time, not the digest. Re-running this
# script replaces the existing task. Remove with:
#   Unregister-ScheduledTask -TaskName 'job-finder weekly' -Confirm:$false

$repo = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $repo '.venv\Scripts\job-finder.exe'
if (-not (Test-Path $exe)) {
    Write-Error "job-finder.exe not found at $exe - create the venv and 'pip install -e .' first (SETUP.md section 2)"
    exit 1
}

$action = New-ScheduledTaskAction -Execute $exe -Argument 'run --email' -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName 'job-finder weekly' -Action $action -Trigger $trigger -Settings $settings -Description 'Weekly job-finder pipeline: collect, extract, score, digest, email.' -Force | Out-Null

Write-Host "Registered 'job-finder weekly' (Mondays 09:00, runs at next boot if missed)."
Write-Host "It needs ANTHROPIC_API_KEY, GMAIL_USER, GMAIL_APP_PASSWORD in the repo's .env"
