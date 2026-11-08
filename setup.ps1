param([switch]$Browser, [switch]$Development)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
function Assert-ExitCode([string]$Operation) { if ($LASTEXITCODE -ne 0) { throw "$Operation failed with exit code $LASTEXITCODE" } }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    Assert-ExitCode 'Virtual environment creation'
}
$runtimePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$requirementsFile = if ($Development) { 'requirements-dev.txt' } else { 'requirements.txt' }
& $runtimePython -m pip install -r $requirementsFile
Assert-ExitCode 'Python dependency installation'
if ($Browser) {
    & $runtimePython -m pip install -r requirements-browser.txt
    Assert-ExitCode 'Playwright installation'
    & $runtimePython -m playwright install chromium
    Assert-ExitCode 'Chromium installation'
}
Push-Location -LiteralPath (Join-Path $PSScriptRoot 'frontend')
try {
    npm.cmd ci
    Assert-ExitCode 'Frontend dependencies'
    npm.cmd run build
    Assert-ExitCode 'Frontend build'
} finally { Pop-Location }
Write-Host 'NEXUS is ready. Run .\start.ps1 and create your local owner account in the browser.'
