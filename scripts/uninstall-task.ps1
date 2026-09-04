<#
.SYNOPSIS
    Removes the weekly Letterboxd Sync scheduled task.

.DESCRIPTION
    Unregisters the task created by install-task.ps1. Nothing else is touched:
    the database, the logs and the CSV files stay where they are.

.PARAMETER TaskName
    Name of the scheduled task. Defaults to "LetterboxdSync-Weekly".

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\uninstall-task.ps1
#>

[CmdletBinding()]
param(
    [string]$TaskName = 'LetterboxdSync-Weekly'
)

$ErrorActionPreference = 'Stop'

if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
    Write-Host "No scheduled task named '$TaskName'. Nothing to do."
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Removed scheduled task '$TaskName'."
Write-Host 'The database, logs and CSV files were left untouched.'
