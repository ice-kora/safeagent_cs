$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path

Push-Location $ProjectRoot
try {
    python scripts/ingest_knowledge_to_milvus.py --source docs/knowledge @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
