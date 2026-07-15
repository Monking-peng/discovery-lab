[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ToolsBin = Join-Path $ProjectRoot ".tools\bin"
$UvExe = Join-Path $ToolsBin "uv.exe"
$UvVersion = "0.11.28"
$PythonVersion = "3.12.13"

New-Item -ItemType Directory -Force -Path $ToolsBin | Out-Null

if (-not (Test-Path $UvExe)) {
    Write-Host "Installing project-local uv $UvVersion..." -ForegroundColor Cyan
    $env:UV_UNMANAGED_INSTALL = $ToolsBin
    $env:UV_NO_MODIFY_PATH = "1"
    Invoke-RestMethod "https://astral.sh/uv/$UvVersion/install.ps1" | Invoke-Expression
}
else {
    Write-Host "Project-local uv already exists." -ForegroundColor Green
}

& $UvExe --version

$env:UV_PYTHON_INSTALL_DIR = Join-Path $ProjectRoot ".tools\python"
$env:UV_CACHE_DIR = Join-Path $ProjectRoot ".cache\uv"
Write-Host "Ensuring project-managed Python $PythonVersion..." -ForegroundColor Cyan
& $UvExe python install $PythonVersion

if (Test-Path (Join-Path $ProjectRoot "pyproject.toml")) {
    Write-Host "Syncing locked Python dependencies..." -ForegroundColor Cyan
    Push-Location $ProjectRoot
    try {
        & $UvExe sync --dev
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $ProjectRoot ".env"))) {
    Write-Host "Create .env from .env.example before starting services." -ForegroundColor Yellow
}

& (Join-Path $PSScriptRoot "doctor.ps1")
