$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path

function Load-EnvFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        Write-Host "[WARN] env file not found: $Path" -ForegroundColor Yellow
        return
    }
    foreach ($Line in Get-Content $Path -Encoding UTF8) {
        $Trimmed = $Line.Trim()
        if (-not $Trimmed -or $Trimmed.StartsWith("#")) { continue }
        if ($Trimmed.StartsWith("export ")) {
            $Trimmed = $Trimmed.Substring(7).Trim()
        }
        $EqIdx = $Trimmed.IndexOf("=")
        if ($EqIdx -le 0) { continue }
        $Key = $Trimmed.Substring(0, $EqIdx).Trim()
        $Value = $Trimmed.Substring($EqIdx + 1).Trim()
        if ($Value.Length -ge 2) {
            $First = $Value[0]
            $Last = $Value[$Value.Length - 1]
            if (($First -eq '"' -and $Last -eq '"') -or ($First -eq "'" -and $Last -eq "'")) {
                $Value = $Value.Substring(1, $Value.Length - 2)
            }
        }
        [Environment]::SetEnvironmentVariable($Key, $Value, "Process")
    }
}

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Block,
        [string]$Hint
    )
    Write-Host ""
    Write-Host "[$Name]" -ForegroundColor Green
    try {
        $global:LASTEXITCODE = 0
        & $Block
        if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
            throw "exit code $LASTEXITCODE"
        }
    } catch {
        Write-Host "[ERROR] $Name failed: $_" -ForegroundColor Red
        if ($Hint) {
            Write-Host "[HINT] $Hint" -ForegroundColor Yellow
        }
        exit 1
    }
}

Write-Host "=== SafeAgent-CS Real RAG + Milvus Smoke ===" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"

Load-EnvFile (Join-Path $ProjectRoot ".env.local")

if (-not $env:SAFEAGENT_PROFILE) { $env:SAFEAGENT_PROFILE = "demo" }
$env:SAFEAGENT_RAG_VECTOR_STORE = "milvus"
$env:SAFEAGENT_RAG_EMBEDDING_PROVIDER = "bge_m3"
if (-not $env:SAFEAGENT_RAG_EMBEDDING_MODEL) { $env:SAFEAGENT_RAG_EMBEDDING_MODEL = "BAAI/bge-m3" }
if (-not $env:SAFEAGENT_RAG_EMBEDDING_DEVICE) { $env:SAFEAGENT_RAG_EMBEDDING_DEVICE = "cpu" }
if (-not $env:SAFEAGENT_RAG_MODEL_CACHE_DIR) { $env:SAFEAGENT_RAG_MODEL_CACHE_DIR = ".cache/huggingface" }
if (-not $env:SAFEAGENT_RAG_COLLECTION) { $env:SAFEAGENT_RAG_COLLECTION = "safeagent_knowledge" }
if (-not $env:SAFEAGENT_RAG_TOP_K) { $env:SAFEAGENT_RAG_TOP_K = "5" }
$env:SAFEAGENT_RAG_FAIL_FAST = "true"

if (-not $env:SAFEAGENT_RAG_MILVUS_URI) {
    Write-Host "[ERROR] SAFEAGENT_RAG_MILVUS_URI is required." -ForegroundColor Red
    Write-Host "[HINT] Start Milvus and set SAFEAGENT_RAG_MILVUS_URI=http://localhost:19530" -ForegroundColor Yellow
    exit 1
}

Push-Location $ProjectRoot
try {
    Invoke-Step "1/7 Check Milvus URI" {
        Write-Host "  SAFEAGENT_RAG_MILVUS_URI=$env:SAFEAGENT_RAG_MILVUS_URI"
        Write-Host "  SAFEAGENT_RAG_COLLECTION=$env:SAFEAGENT_RAG_COLLECTION"
    } ""

    Invoke-Step "2/7 Check Milvus connection" {
        @'
import os
from pymilvus import MilvusClient
client = MilvusClient(uri=os.environ["SAFEAGENT_RAG_MILVUS_URI"])
print("collections=", client.list_collections())
'@ | python -
    } "Verify Docker Milvus is running and port 19530 is published."

    Invoke-Step "3/7 Check bge-m3 model load" {
        @'
import os
from app.rag.embeddings.bge_m3_embedder import BgeM3Embedder
embedder = BgeM3Embedder(
    model_name=os.environ.get("SAFEAGENT_RAG_EMBEDDING_MODEL", "BAAI/bge-m3"),
    device=os.environ.get("SAFEAGENT_RAG_EMBEDDING_DEVICE", "cpu"),
    cache_dir=os.environ.get("SAFEAGENT_RAG_MODEL_CACHE_DIR"),
)
vector = embedder.embed(["SafeAgent-CS real RAG smoke"])[0]
print("embedding_model=", embedder.model_name)
print("vector_dim=", len(vector))
'@ | python -
    } "Install FlagEmbedding and ensure the model can be downloaded or is already cached."

    Invoke-Step "4/7 Seed knowledge docs" {
        python scripts/seed_demo_knowledge.py --reset
    } "Check write permission under docs/knowledge."

    Invoke-Step "5/7 Rebuild collection and ingest" {
        python scripts/ingest_knowledge_to_milvus.py --reset --source docs/knowledge --collection $env:SAFEAGENT_RAG_COLLECTION --top-k $env:SAFEAGENT_RAG_TOP_K
    } "If dimension mismatch appears, rerun with --reset or drop the collection manually."

    Invoke-Step "6/7 Query policy through RAGService" {
        @'
import json
from app.rag.rag_service import RAGService
result = RAGService().query("退款规则是什么？退款审核通过后多久到账？")
print(json.dumps({
    "vector_store": result.get("vector_store"),
    "embedding_model": result.get("embedding_model"),
    "retrieval_mode": result.get("retrieval_mode"),
    "evidence_count": len(result.get("evidence", [])),
    "top_doc": result.get("evidence", [{}])[0].get("doc_id") if result.get("evidence") else None,
    "top_score": result.get("evidence", [{}])[0].get("score") if result.get("evidence") else None,
}, ensure_ascii=False, indent=2))
'@ | python -
    } "Check that ingest completed and the collection contains policy chunks."

    Invoke-Step "7/7 Run RAG eval" {
        python scripts/eval_rag.py --vector-store milvus --embedding bge_m3 --top-k $env:SAFEAGENT_RAG_TOP_K
    } "Inspect per-case score_detail and knowledge coverage."
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "=== Real RAG smoke completed ===" -ForegroundColor Cyan
