[CmdletBinding()]
param(
    [ValidateSet("up", "down", "status", "logs")]
    [string]$Action = "up"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $ProjectRoot "infra\compose.yaml"
$EnvFile = Join-Path $ProjectRoot ".env"
$KeepAlivePidFile = Join-Path $ProjectRoot ".cache\wsl-docker-keepalive.pid"
$WindowsDocker = Get-Command docker -ErrorAction SilentlyContinue

function Start-WslDockerKeepAlive {
    if ($WindowsDocker) {
        return
    }

    if (Test-Path $KeepAlivePidFile) {
        $ExistingPid = [int](Get-Content -Raw $KeepAlivePidFile)
        $ExistingProcess = Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue
        if ($ExistingProcess -and $ExistingProcess.ProcessName -eq "wsl") {
            return
        }
        Remove-Item -LiteralPath $KeepAlivePidFile -Force -ErrorAction SilentlyContinue
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $KeepAlivePidFile) | Out-Null
    $Process = Start-Process `
        -FilePath "wsl.exe" `
        -ArgumentList @("-d", "Ubuntu", "--", "sleep", "infinity") `
        -WindowStyle Hidden `
        -PassThru
    [System.IO.File]::WriteAllText($KeepAlivePidFile, [string]$Process.Id)
    Start-Sleep -Milliseconds 750
}

function Stop-WslDockerKeepAlive {
    if (-not (Test-Path $KeepAlivePidFile)) {
        return
    }
    $KeepAlivePid = [int](Get-Content -Raw $KeepAlivePidFile)
    Stop-Process -Id $KeepAlivePid -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $KeepAlivePidFile -Force -ErrorAction SilentlyContinue
}

function Convert-ToWslPath {
    param([string]$WindowsPath)

    if ($WindowsPath -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $WindowsPath"
    }

    $Drive = $Matches[1].ToLowerInvariant()
    $Rest = $Matches[2] -replace '\\', '/'
    return "/mnt/$Drive/$Rest"
}

function Invoke-Compose {
    param([string[]]$Arguments)

    if ($WindowsDocker) {
        & docker compose @Arguments
        return
    }

    $Wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if ($Wsl) {
        & wsl.exe -d Ubuntu -- docker compose @Arguments
        return
    }

    throw "Docker is unavailable. Install Docker Desktop or Docker Engine in WSL Ubuntu."
}

$ComposeFileForDocker = if ($WindowsDocker) { $ComposeFile } else { Convert-ToWslPath $ComposeFile }
$EnvFileForDocker = if ($WindowsDocker) { $EnvFile } else { Convert-ToWslPath $EnvFile }
$EnvArgs = if (Test-Path $EnvFile) { @("--env-file", $EnvFileForDocker) } else { @() }
$CommonArgs = @($EnvArgs + @("-f", $ComposeFileForDocker))

switch ($Action) {
    "up" {
        Start-WslDockerKeepAlive
        Invoke-Compose ($CommonArgs + @("up", "-d", "--wait"))
    }
    "down" {
        Start-WslDockerKeepAlive
        try {
            Invoke-Compose ($CommonArgs + @("down"))
        }
        finally {
            Stop-WslDockerKeepAlive
        }
    }
    "status" {
        Start-WslDockerKeepAlive
        Invoke-Compose ($CommonArgs + @("ps"))
    }
    "logs" {
        Start-WslDockerKeepAlive
        Invoke-Compose ($CommonArgs + @("logs", "--tail", "200"))
    }
}
