[CmdletBinding()]
param(
    [string]$Output = ".cache\evals\source-to-evidence.json"
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
}
finally {
    Pop-Location
}
