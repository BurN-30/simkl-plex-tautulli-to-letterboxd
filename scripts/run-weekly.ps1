<#
.SYNOPSIS
    Weekly job: sync the source, then write an incremental Letterboxd CSV.

.DESCRIPTION
    Called by the scheduled task registered by install-task.ps1, but safe to
    run by hand. It never talks to Letterboxd: it only refreshes the local
    database and writes CSV files into output\pending.

.PARAMETER Python
    Python executable to use. Defaults to the project venv when present.
#>

[CmdletBinding()]
param(
    [string]$Python
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot 'logs'
$LogFile = Join-Path $LogDir 'weekly-task.log'

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

function Write-Log {
    param([string]$Message)
    $Line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path $LogFile -Value $Line -Encoding utf8
    Write-Host $Line
}

if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot 'venv\Scripts\python.exe'
    if (Test-Path $VenvPython) {
        $Python = $VenvPython
    }
    else {
        $Python = 'python'
    }
}

Set-Location $ProjectRoot

# Keep CSV titles and reviews readable in the log on a legacy console codepage.
$env:PYTHONIOENCODING = 'utf-8'

$ExitCode = 0
Write-Log '--- weekly run start ---'

Write-Log 'step 1/2: sync'
& $Python -m src.cli sync 2>&1 | ForEach-Object { Write-Log "  $_" }
if ($LASTEXITCODE -ne 0) {
    Write-Log "sync failed with exit code $LASTEXITCODE, skipping export"
    Write-Log '--- weekly run end ---'
    exit $LASTEXITCODE
}

Write-Log 'step 2/2: export --incremental'
& $Python -m src.cli export --incremental 2>&1 | ForEach-Object { Write-Log "  $_" }
if ($LASTEXITCODE -ne 0) {
    Write-Log "export failed with exit code $LASTEXITCODE"
    $ExitCode = $LASTEXITCODE
}

$Pending = Get-ChildItem -Path (Join-Path $ProjectRoot 'output\pending') -Filter '*.csv' -ErrorAction SilentlyContinue
if ($Pending) {
    Write-Log "$($Pending.Count) CSV file(s) waiting in output\pending, import them at https://letterboxd.com/import"
}
else {
    Write-Log 'nothing new to import'
}

Write-Log '--- weekly run end ---'
exit $ExitCode
