$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path

if (-not $env:SAFEAGENT_RAG_MILVUS_URI) {
    Write-Host "SKIP: SAFEAGENT_RAG_MILVUS_URI is not set." -ForegroundColor Yellow
    Write-Host "Example: docker run -p 19530:19530 milvusdb/milvus:latest"
    exit 0
}

$env:SAFEAGENT_RAG_VECTOR_STORE = "milvus"
Push-Location $ProjectRoot
try {
    @'
from app.rag.rag_service import RAGService
result = RAGService().query("订单未发货可以修改地址吗")
print("vector_store=", result.get("vector_store"))
print("fallback=", result.get("vector_store_fallback"))
print("evidence_count=", len(result.get("evidence", [])))
'@ | python -
} finally {
    Pop-Location
}
