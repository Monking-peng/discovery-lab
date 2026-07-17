[CmdletBinding()]
param(
    [string]$Output = ".cache\evals\source-to-evidence.json",
    [string]$EvidenceToClaimOutput = ".cache\evals\evidence-to-claim.json",
    [string]$BadCasesOutput = ".cache\evals\bad-cases.json"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Uv = Join-Path $ProjectRoot ".tools\bin\uv.exe"

Push-Location $ProjectRoot
try {
    & $Uv run python -m discovery_lab.evaluation.source_to_evidence `
        --dataset "evals\golden\source_to_evidence.json" `
        --output $Output
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    & $Uv run python -m discovery_lab.evaluation.evidence_to_claim `
        --dataset "evals\golden\evidence_to_claim.json" `
        --output $EvidenceToClaimOutput
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    & $Uv run python -m discovery_lab.evaluation.bad_cases `
        --output $BadCasesOutput
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
