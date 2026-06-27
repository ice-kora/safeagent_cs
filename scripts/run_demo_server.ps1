$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path

Push-Location $ProjectRoot
try {
    if (-not $env:SAFEAGENT_PROFILE) { $env:SAFEAGENT_PROFILE = "demo" }
    if (-not $env:SAFEAGENT_RAG_VECTOR_STORE) { $env:SAFEAGENT_RAG_VECTOR_STORE = "memory" }
    Write-Host "SafeAgent-CS demo server" -ForegroundColor Cyan
    Write-Host "  SAFEAGENT_PROFILE=$env:SAFEAGENT_PROFILE"
    Write-Host "  Console: http://127.0.0.1:8010/console/"
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
} finally {
    Pop-Location
}
