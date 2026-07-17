[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8010,

    [ValidateRange(1, 65535)]
    [int]$WebPort = 3010,

    [switch]$NoOpen,

    [switch]$SkipSeed
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DevScript = Join-Path $PSScriptRoot "dev.ps1"
$SeedScript = Join-Path $PSScriptRoot "seed-helphub.ps1"
$ApiUrl = "http://127.0.0.1:$ApiPort"
$ProductUrl = "http://127.0.0.1:$WebPort"

if (-not (Test-Path -LiteralPath $DevScript -PathType Leaf)) {
    throw "DiscoveryLab launcher could not find scripts\dev.ps1."
}

Push-Location $ProjectRoot
try {
    & $DevScript start -ApiPort $ApiPort -WebPort $WebPort
    if ($LASTEXITCODE -ne 0) {
        throw "DiscoveryLab startup returned exit code $LASTEXITCODE."
    }
    if (-not $SkipSeed) {
        if (-not (Test-Path -LiteralPath $SeedScript -PathType Leaf)) {
            throw "DiscoveryLab launcher could not find scripts\seed-helphub.ps1."
        }
        Write-Host "Preparing the repeatable HelpHub portfolio demo..." -ForegroundColor Cyan
        & $SeedScript -ApiUrl $ApiUrl -WebUrl $ProductUrl
        if ($LASTEXITCODE -ne 0) {
            throw "HelpHub demo preparation returned exit code $LASTEXITCODE."
        }
    }
}
finally {
    Pop-Location
}

if ($NoOpen) {
    Write-Host "DiscoveryLab is ready at $ProductUrl" -ForegroundColor Green
    return
}

Write-Host "Opening DiscoveryLab..." -ForegroundColor Green
Start-Process -FilePath $ProductUrl
