# Register the weekly local pipeline run with Windows Task Scheduler.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_schedule.ps1
#
# Runs `job-finder run --email` every Monday at 09:00 local time.
#
# WakeToRun is what makes that reliable. On 2026-08-31 the machine was asleep
# at 09:00 and StartWhenAvailable did NOT produce a catch-up run: 24 minutes
# past wake the task still showed NumberOfMissedRuns=1 and a next run a week
# out. StartWhenAvailable stays on for the powered-off case, but do not rely
# on it alone; sleep is the common case and waking for the trigger is the fix.
# Re-running this script replaces the existing task. Remove with:
#   Unregister-ScheduledTask -TaskName 'job-finder weekly' -Confirm:$false
#
# The task launches scripts\run_scheduled.py with pythonw.exe (no console),
# so no terminal window appears during the run. Because there is no console,
# all output goes to data\logs\scheduled-run.log — check it when a run's
# LastTaskResult is nonzero. The task reads user-level environment variables
# (setx) and the repo .env; a variable set with setx applies from the next
# launch. No elevation required.

$repo = Split-Path -Parent $PSScriptRoot
$pyw = Join-Path $repo '.venv\Scripts\pythonw.exe'
$runner = Join-Path $repo 'scripts\run_scheduled.py'
if (-not (Test-Path $pyw)) {
    Write-Error "pythonw.exe not found at $pyw - create the venv and 'pip install -e .' first (SETUP.md section 2)"
    exit 1
}

$action = New-ScheduledTaskAction -Execute $pyw -Argument ('"{0}"' -f $runner) -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName 'job-finder weekly' -Action $action -Trigger $trigger -Settings $settings -Description 'Weekly job-finder pipeline: collect, extract, score, digest, email.' -Force | Out-Null

Write-Host "Registered 'job-finder weekly' (Mondays 09:00, windowless, catch-up at next boot if missed)."
Write-Host "Output goes to data\logs\scheduled-run.log"
Write-Host "It needs ANTHROPIC_API_KEY in the repo's .env, and GMAIL_USER + GMAIL_APP_PASSWORD in .env or set via setx."
