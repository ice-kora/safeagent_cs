$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path

$Missing = @()
foreach ($Name in @("SAFEAGENT_LLM_BASE_URL", "SAFEAGENT_LLM_MODEL", "SAFEAGENT_LLM_API_KEY")) {
    if (-not [Environment]::GetEnvironmentVariable($Name, "Process")) {
        $Missing += $Name
    }
}
if ($Missing.Count -gt 0) {
    Write-Host "SKIP: missing real LLM env: $($Missing -join ', ')" -ForegroundColor Yellow
    exit 0
}

$env:SAFEAGENT_PROFILE = "demo"
$env:SAFEAGENT_WORKFLOW_MODE = "workflow"
$env:SAFEAGENT_WORKFLOW_ENGINE = "langgraph"
$env:SAFEAGENT_LLM_MODE = "real_llm"

Push-Location $ProjectRoot
try {
    @'
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
body = {"user_id": "u_1001", "session_id": "sess_llm_smoke", "message": "帮我查一下订单 O10086"}
response = client.post("/api/chat", json=body)
print(response.status_code)
print(response.json())
'@ | python -
} finally {
    Pop-Location
}
