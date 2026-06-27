$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path

Push-Location $ProjectRoot
try {
    if (-not $env:SAFEAGENT_RAG_VECTOR_STORE) { $env:SAFEAGENT_RAG_VECTOR_STORE = "memory" }
    if (-not $env:SAFEAGENT_RAG_EMBEDDING_PROVIDER) { $env:SAFEAGENT_RAG_EMBEDDING_PROVIDER = "mock" }
    python scripts/eval_rag.py
} finally {
    Pop-Location
}
