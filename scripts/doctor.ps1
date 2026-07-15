[CmdletBinding()]
param(
    [switch]$Strict
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LocalUv = Join-Path $ProjectRoot ".tools\bin\uv.exe"
$HasBlockingIssue = $false
$env:UV_PYTHON_INSTALL_DIR = Join-Path $ProjectRoot ".tools\python"
$env:UV_CACHE_DIR = Join-Path $ProjectRoot ".cache\uv"

function Test-WslDocker {
    $Wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if (-not $Wsl) {
        return $false
    }

    try {
        & wsl.exe -d Ubuntu -- docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Write-Check {
    param(
        [string]$Name,
        [bool]$Ok,
        [string]$Detail,
        [bool]$Required = $true
    )

    $Label = if ($Ok) { "OK" } elseif ($Required) { "MISSING" } else { "OPTIONAL" }
    $Color = if ($Ok) { "Green" } elseif ($Required) { "Red" } else { "Yellow" }
    Write-Host ("[{0,-8}] {1,-18} {2}" -f $Label, $Name, $Detail) -ForegroundColor $Color

    if (-not $Ok -and $Required) {
        $script:HasBlockingIssue = $true
    }
}

function Get-FirstLine {
    param([scriptblock]$Command)

    try {
        return ((& $Command 2>&1 | Select-Object -First 1) -join " ").Trim()
    }
    catch {
        return $null
    }
}

$Git = Get-Command git -ErrorAction SilentlyContinue
Write-Check "Git" ($null -ne $Git) $(if ($Git) { Get-FirstLine { git --version } } else { "Install Git 2.40+." })

$Node = Get-Command node -ErrorAction SilentlyContinue
Write-Check "Node.js" ($null -ne $Node) $(if ($Node) { Get-FirstLine { node --version } } else { "Install the Node 24 LTS line." })

$Pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
Write-Check "pnpm" ($null -ne $Pnpm) $(if ($Pnpm) { Get-FirstLine { pnpm --version } } else { "Install pnpm 11 or enable Corepack." })

$UvPath = if (Test-Path $LocalUv) { $LocalUv } else { (Get-Command uv -ErrorAction SilentlyContinue).Source }
Write-Check "uv" ($null -ne $UvPath) $(if ($UvPath) { Get-FirstLine { & $UvPath --version } } else { "Run scripts/bootstrap.ps1." })

if ($UvPath) {
    $PythonPath = Get-FirstLine { & $UvPath python find 3.12 }
    Write-Check "Python 3.12" ($null -ne $PythonPath) $(if ($PythonPath) { $PythonPath } else { "Run scripts/bootstrap.ps1." })
}
else {
    Write-Check "Python 3.12" $false "Install uv first; it manages the project Python."
}

$Docker = Get-Command docker -ErrorAction SilentlyContinue
$WslDocker = if ($Docker) { $false } else { Test-WslDocker }
$DockerAvailable = ($null -ne $Docker) -or $WslDocker
$DockerDetail = if ($Docker) {
    Get-FirstLine { docker --version }
}
elseif ($WslDocker) {
    (Get-FirstLine { wsl.exe -d Ubuntu -- docker --version }) + " (WSL Ubuntu)"
}
else {
    "Install Docker Desktop, or Docker Engine inside WSL 2."
}
Write-Check "Docker CLI" $DockerAvailable $DockerDetail

if ($Docker) {
    $ComposeVersion = Get-FirstLine { docker compose version }
    Write-Check "Docker Compose" ($null -ne $ComposeVersion) $(if ($ComposeVersion) { $ComposeVersion } else { "Docker Desktop should include Compose." })

    $DockerReady = $null -ne (Get-FirstLine { docker info --format '{{.ServerVersion}}' })
    Write-Check "Docker engine" $DockerReady $(if ($DockerReady) { "running" } else { "Start Docker Desktop." })
}
elseif ($WslDocker) {
    $ComposeVersion = Get-FirstLine { wsl.exe -d Ubuntu -- docker compose version }
    Write-Check "Docker Compose" ($null -ne $ComposeVersion) ($ComposeVersion + " (WSL Ubuntu)")
    $DockerServer = Get-FirstLine { wsl.exe -d Ubuntu -- docker info --format '{{.ServerVersion}}' }
    Write-Check "Docker engine" ($null -ne $DockerServer) ("running in WSL Ubuntu, server " + $DockerServer)
}
else {
    Write-Check "Docker Compose" $false "Install it with Docker Desktop or the WSL Docker Compose plugin."
    Write-Check "Docker engine" $false "No usable Windows or WSL Ubuntu engine was found."
}

if ($Strict -and $HasBlockingIssue) {
    exit 1
}

if ($HasBlockingIssue) {
    Write-Host "`nEnvironment is partially ready. See docs/development-environment.md." -ForegroundColor Yellow
}
else {
    Write-Host "`nEnvironment is ready." -ForegroundColor Green
}
