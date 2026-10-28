param([string]$Python = "python")

$ErrorActionPreference = "Continue"
$runner = Join-Path $PSScriptRoot "weekly_mainline_runner.py"
$log = Join-Path $PSScriptRoot "weekly_mainline_task.log"
Push-Location (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
try {
    & $Python $runner *>> $log
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
