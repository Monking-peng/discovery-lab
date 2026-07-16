[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Uv = Join-Path $ProjectRoot ".tools\bin\uv.exe"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $ProjectRoot ".tools\python"
$env:UV_CACHE_DIR = Join-Path $ProjectRoot ".cache\uv"

Push-Location $ProjectRoot
try {
    & $Uv run ruff check .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Uv run ruff format --check .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Uv run mypy src\discovery_lab
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Uv run pytest
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Uv run python -m discovery_lab.evaluation.source_to_evidence `
        --dataset "evals\golden\source_to_evidence.json" `
        --output ".cache\evals\source-to-evidence.json"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Uv run python -m discovery_lab.evaluation.evidence_to_claim `
        --dataset "evals\golden\evidence_to_claim.json" `
        --output ".cache\evals\evidence-to-claim.json"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Uv run python -m discovery_lab.evaluation.bad_cases `
        --output ".cache\evals\bad-cases.json"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    if (Test-Path (Join-Path $ProjectRoot "apps\web\node_modules")) {
        & pnpm lint:web
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & pnpm typecheck:web
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & pnpm test:web
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & pnpm build:web
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    else {
        Write-Host "Skipping web checks until pnpm install has run." -ForegroundColor Yellow
    }
}
finally {
    Pop-Location
}
