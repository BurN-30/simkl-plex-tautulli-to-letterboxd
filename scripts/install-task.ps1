<#
.SYNOPSIS
    Registers the weekly Letterboxd Sync scheduled task.

.DESCRIPTION
    Creates a Windows scheduled task that runs, every Sunday at 09:00 local
    time, the run-weekly.ps1 wrapper: `sync` followed by `export --incremental`.
    The resulting CSV files land in output\pending and wait for a manual import
    at letterboxd.com/import. Nothing is ever uploaded automatically.

    The task runs under the current user. It is registered with an interactive
    logon type so it can reach the network and write into the project folder.

.PARAMETER TaskName
    Name of the scheduled task. Defaults to "LetterboxdSync-Weekly".

.PARAMETER At
    Time of day to run, as HH:mm. Defaults to 09:00.

.PARAMETER DayOfWeek
    Day of week to run. Defaults to Sunday.

.PARAMETER Python
    Python executable to use. Defaults to the project venv when present,
    otherwise the python on PATH.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1 -At 21:30 -DayOfWeek Monday
#>

[CmdletBinding()]
param(
    [string]$TaskName = 'LetterboxdSync-Weekly',
    [string]$At = '09:00',
    [ValidateSet('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')]
    [string]$DayOfWeek = 'Sunday',
    [string]$Python
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $PSScriptRoot 'run-weekly.ps1'
$LogDir = Join-Path $ProjectRoot 'logs'

if (-not (Test-Path $Runner)) {
    throw "Runner script not found: $Runner"
}

if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot 'venv\Scripts\python.exe'
    if (Test-Path $VenvPython) {
        $Python = $VenvPython
    }
    else {
        $Command = Get-Command python -ErrorAction SilentlyContinue
        if (-not $Command) {
            throw 'No python found. Create the venv first, or pass -Python.'
        }
        $Python = $Command.Source
        Write-Warning "No venv at $VenvPython, falling back to $Python"
    }
}

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

try {
    $ParsedTime = [datetime]::ParseExact($At, 'HH:mm', $null)
}
catch {
    throw "Invalid -At value '$At', expected HH:mm (24 hour)."
}

$Arguments = @(
    '-NoProfile'
    '-ExecutionPolicy', 'Bypass'
    '-File', ('"{0}"' -f $Runner)
    '-Python', ('"{0}"' -f $Python)
) -join ' '

$Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $Arguments -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $ParsedTime
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Task '$TaskName' already exists, replacing it."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description 'Weekly Simkl sync and incremental Letterboxd CSV export. Import stays manual.' | Out-Null

Write-Host ''
Write-Host "Registered '$TaskName'"
Write-Host "  runs      : $DayOfWeek at $At (local time)"
Write-Host "  python    : $Python"
Write-Host "  project   : $ProjectRoot"
Write-Host "  log       : $(Join-Path $LogDir 'weekly-task.log')"
Write-Host ''
Write-Host 'Run it once now with:'
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host 'Then import output\pending\*.csv at https://letterboxd.com/import'
Write-Host 'and confirm with: python -m src.cli confirm <file>'
