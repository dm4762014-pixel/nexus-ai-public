param([int]$Port = 8000, [switch]$TrustedLocalProxy)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Choose an unprivileged TCP port between 1024 and 65535.' }
if (Test-Path -LiteralPath '.env') {
    foreach ($line in Get-Content -LiteralPath '.env') {
        if ($line -match '^\s*(NEXUS_[A-Z_]+)\s*=\s*(.*?)\s*$') {
            $settingName = $Matches[1]
            $settingValue = $Matches[2].Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($settingName, $settingValue, 'Process')
        }
    }
}
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe') -or -not (Test-Path -LiteralPath 'frontend\dist\index.html')) {
    throw 'Run .\setup.ps1 first. Python environment and compiled frontend are required.'
}
$occupiedPort = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($occupiedPort) { throw "Port $Port is in use. Reuse your existing NEXUS window or choose -Port 8005. No process was stopped." }
Write-Host "NEXUS AI: http://127.0.0.1:$Port (Ctrl+C stops the server). Ollama must be running locally."
$serverArguments = @('-m','uvicorn','main:app','--host','127.0.0.1','--port',"$Port",'--workers','1','--limit-concurrency','32','--timeout-keep-alive','5')
if ($TrustedLocalProxy) { $serverArguments += @('--proxy-headers','--forwarded-allow-ips','127.0.0.1') }
else { $serverArguments += '--no-proxy-headers' }
& '.\.venv\Scripts\python.exe' @serverArguments
exit $LASTEXITCODE
