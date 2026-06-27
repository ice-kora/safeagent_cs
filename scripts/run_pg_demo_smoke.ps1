$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path

Write-Host "=== SafeAgent-CS v0.8 PG Demo Smoke ===" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"
Write-Host ""

# Step 1: Load .env.local
$EnvLocalPath = Join-Path $ProjectRoot ".env.local"
if (-not (Test-Path $EnvLocalPath)) {
    Write-Host "[ERROR] .env.local not found: $EnvLocalPath" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Create it from the demo template:" -ForegroundColor Yellow
    Write-Host "    copy .env.demo.example .env.local" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "[1/6] Loading .env.local ..." -ForegroundColor Green

$EnvVars = @{}
foreach ($Line in Get-Content $EnvLocalPath -Encoding UTF8) {
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
    $EnvVars[$Key] = $Value
    [Environment]::SetEnvironmentVariable($Key, $Value, "Process")
}

Write-Host "  Loaded $($EnvVars.Count) variable(s)."

# Simple redaction: split URL on @ and mask password
function Redact-Url {
    param($Url)
    if (-not $Url) { return "<not set>" }
    try {
        $Uri = [uri]$Url
        $Masked = ""
        if ($Uri.UserInfo) {
            $Name = $Uri.UserInfo.Split(':')[0]
            $Masked = "$Name" + ":***@"
        }
        $rest = $Uri.Host + ":" + $Uri.Port + $Uri.AbsolutePath
        return $Uri.Scheme + "://" + $Masked + $rest
    } catch {
        return $Url
    }
}

Write-Host ""
Write-Host "  SAFEAGENT_PROFILE              = $($EnvVars['SAFEAGENT_PROFILE'])"
Write-Host "  DATABASE_URL                   = $(Redact-Url $EnvVars['DATABASE_URL'])"
Write-Host "  SAFEAGENT_RUNTIME_DATABASE_URL = $(Redact-Url $EnvVars['SAFEAGENT_RUNTIME_DATABASE_URL'])"

# Step 2: Check prerequisites
Write-Host ""
Write-Host "[2/6] Checking prerequisites ..." -ForegroundColor Green

$Profile = $EnvVars['SAFEAGENT_PROFILE']
if ($Profile -ne "demo") {
    Write-Host "[ERROR] SAFEAGENT_PROFILE must be 'demo', got: '$Profile'" -ForegroundColor Red
    exit 1
}
Write-Host "  SAFEAGENT_PROFILE = demo  OK"

$DbUrl = $EnvVars['DATABASE_URL']
if (-not $DbUrl) {
    Write-Host "[ERROR] DATABASE_URL is not set in .env.local" -ForegroundColor Red
    exit 1
}
Write-Host "  DATABASE_URL  OK"

$RuntimeUrl = $EnvVars['SAFEAGENT_RUNTIME_DATABASE_URL']
if (-not $RuntimeUrl) {
    Write-Host "[ERROR] SAFEAGENT_RUNTIME_DATABASE_URL is not set in .env.local" -ForegroundColor Red
    exit 1
}
Write-Host "  SAFEAGENT_RUNTIME_DATABASE_URL  OK"

# Step 3: Check Docker PG container
Write-Host ""
Write-Host "[3/6] Checking Docker PostgreSQL container ..." -ForegroundColor Green

$ContainerName = "safeagent-pg"
$ContainerStatus = docker ps -a --filter "name=$ContainerName" --format "{{.Status}}" 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Cannot connect to Docker. Is Docker Desktop running?" -ForegroundColor Red
    exit 1
}

if (-not $ContainerStatus) {
    Write-Host "[INFO] Container '$ContainerName' does not exist." -ForegroundColor Yellow
    Write-Host ""
    $DockerHelp = @'
  Create it with:
    docker run --name safeagent-pg \
      -e POSTGRES_USER=safeagent \
      -e POSTGRES_PASSWORD=safeagent_pwd \
      -e POSTGRES_DB=safeagent_cs \
      -p 5432:5432 \
      -d postgres:16

  See .env.demo.example for details.
'@
    Write-Host $DockerHelp -ForegroundColor Yellow
    exit 1
}

if ($ContainerStatus -like "Up*") {
    Write-Host "  Container '$ContainerName' is Up - reusing." -ForegroundColor Green
} elseif ($ContainerStatus -like "Exited*") {
    Write-Host "[INFO] Container '$ContainerName' is Exited. Starting ..." -ForegroundColor Yellow
    docker start $ContainerName 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to start container." -ForegroundColor Red
        exit 1
    }
    Start-Sleep -Seconds 3
    Write-Host "  Container started." -ForegroundColor Green
} else {
    Write-Host "[INFO] Container status: $ContainerStatus" -ForegroundColor Yellow
    Write-Host "  Attempting docker start ..." -ForegroundColor Yellow
    docker start $ContainerName 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to start container." -ForegroundColor Red
        exit 1
    }
    Start-Sleep -Seconds 3
    Write-Host "  Container started." -ForegroundColor Green
}

# Step 4: Run seed_postgres.py
Write-Host ""
Write-Host "[4/6] Running seed_postgres.py ..." -ForegroundColor Green

Push-Location $ProjectRoot
try {
    python seed_postgres.py 2>&1 | ForEach-Object {
        Write-Host "  $_"
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARN] seed_postgres.py exit code $LASTEXITCODE (may be harmless if data exists)" -ForegroundColor Yellow
    }
} finally {
    Pop-Location
}

# Step 5: Run PG demo smoke test
Write-Host ""
Write-Host "[5/6] Running v0.8 PG demo smoke test ..." -ForegroundColor Green

Push-Location $ProjectRoot
try {
    python -m pytest -q -p no:cacheprovider --basetemp C:\tmp\pytest-v08-pg-final tests/test_v08_pg_demo_smoke.py -rs 2>&1 | ForEach-Object {
        Write-Host "  $_"
    }
    $Global:PytestExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

# Step 6: Result
Write-Host ""
Write-Host "[6/6] Result" -ForegroundColor Green

if ($Global:PytestExitCode -eq 0) {
    Write-Host "  PG demo smoke: PASSED" -ForegroundColor Green
} else {
    Write-Host "  PG demo smoke: FAILED (exit code $Global:PytestExitCode)" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
exit $Global:PytestExitCode
