[CmdletBinding()]
param(
    [ValidateSet("start", "stop", "restart", "status", "logs")]
    [string]$Action = "start",

    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8000,

    [ValidateRange(1, 65535)]
    [int]$WebPort = 3000,

    [ValidateRange(1, 500)]
    [int]$Tail = 80,

    [switch]$SkipInfra,
    [switch]$StopInfra
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CacheRoot = Join-Path $ProjectRoot ".cache\dev"
$EnvFile = Join-Path $ProjectRoot ".env"
$EnvExample = Join-Path $ProjectRoot ".env.example"
$Uv = Join-Path $ProjectRoot ".tools\bin\uv.exe"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$NextCli = Join-Path $ProjectRoot "apps\web\node_modules\next\dist\bin\next"
$NodeCommand = Get-Command node -ErrorAction SilentlyContinue

function Get-PidFile {
    param([string]$Name)
    return Join-Path $CacheRoot "$Name.pid"
}

function Get-MetadataFile {
    param([string]$Name)
    return Join-Path $CacheRoot "$Name.process.json"
}

function Get-OutputLog {
    param([string]$Name)
    return Join-Path $CacheRoot "$Name.out.log"
}

function Get-ErrorLog {
    param([string]$Name)
    return Join-Path $CacheRoot "$Name.err.log"
}

function Remove-ManagedState {
    param([string]$Name)

    Remove-Item -LiteralPath (Get-PidFile $Name) -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Get-MetadataFile $Name) -Force -ErrorAction SilentlyContinue
}

function Read-ManagedMetadata {
    param([string]$Name)

    $MetadataFile = Get-MetadataFile $Name
    if (-not (Test-Path $MetadataFile)) {
        return $null
    }

    try {
        return Get-Content -Raw -Encoding UTF8 $MetadataFile | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Get-ManagedProcess {
    param([string]$Name)

    $PidFile = Get-PidFile $Name
    $Metadata = Read-ManagedMetadata $Name
    if (-not (Test-Path $PidFile) -or $null -eq $Metadata) {
        return $null
    }

    try {
        $ManagedPid = [int](Get-Content -Raw $PidFile)
        if ($ManagedPid -ne [int]$Metadata.pid) {
            return $null
        }
        $Process = Get-Process -Id $ManagedPid -ErrorAction Stop
        $ExpectedStart = [DateTime]::Parse(
            [string]$Metadata.started_at_utc,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::RoundtripKind
        )
        $ActualStart = $Process.StartTime.ToUniversalTime()
        if ([Math]::Abs(($ActualStart - $ExpectedStart).TotalSeconds) -gt 1) {
            return $null
        }

        $ActualPath = $Process.Path
        if ($ActualPath) {
            $ExpectedPath = [IO.Path]::GetFullPath([string]$Metadata.executable)
            if (-not $ActualPath.Equals($ExpectedPath, [StringComparison]::OrdinalIgnoreCase)) {
                return $null
            }
        }
        return $Process
    }
    catch {
        return $null
    }
}

function Test-TcpPort {
    param([int]$Port)

    $Client = [Net.Sockets.TcpClient]::new()
    try {
        $Connect = $Client.ConnectAsync("127.0.0.1", $Port)
        if (-not $Connect.Wait(300)) {
            return $false
        }
        return $Client.Connected
    }
    catch {
        return $false
    }
    finally {
        $Client.Dispose()
    }
}

function Wait-HttpEndpoint {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds = 30
    )

    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $Response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2
            if ($Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500) {
                return
            }
        }
        catch {
            # The service is still starting. Its error log is shown if the deadline expires.
        }
        Start-Sleep -Milliseconds 400
    } while ((Get-Date) -lt $Deadline)

    throw "Timed out waiting for $Uri"
}

function Start-ManagedProcess {
    param(
        [string]$Name,
        [string]$Executable,
        [string[]]$Arguments,
        [int]$Port,
        [string]$Url,
        [string]$WorkingDirectory = $ProjectRoot
    )

    $Existing = Get-ManagedProcess $Name
    if ($null -ne $Existing) {
        $ExistingMetadata = Read-ManagedMetadata $Name
        if ([int]$ExistingMetadata.port -ne $Port) {
            throw "$Name is already managed on port $($ExistingMetadata.port). Stop it before changing ports."
        }
        Write-Host "$Name is already running (PID $($Existing.Id))." -ForegroundColor Green
        return $false
    }

    Remove-ManagedState $Name
    if (Test-TcpPort $Port) {
        throw "Port $Port is already in use by a process not managed by DiscoveryLab. Nothing was stopped."
    }

    $OutputLog = Get-OutputLog $Name
    $ErrorLog = Get-ErrorLog $Name
    [IO.File]::WriteAllText($OutputLog, "", [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($ErrorLog, "", [Text.UTF8Encoding]::new($false))

    $Process = Start-Process `
        -FilePath $Executable `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutputLog `
        -RedirectStandardError $ErrorLog `
        -PassThru

    Start-Sleep -Milliseconds 250
    if ($Process.HasExited) {
        $Details = Get-Content -Raw -ErrorAction SilentlyContinue $ErrorLog
        throw "$Name exited during startup. $Details"
    }

    $StartedAt = $Process.StartTime.ToUniversalTime().ToString("O")
    [IO.File]::WriteAllText((Get-PidFile $Name), [string]$Process.Id)
    @{
        name = $Name
        pid = $Process.Id
        started_at_utc = $StartedAt
        executable = [IO.Path]::GetFullPath($Executable)
        arguments = $Arguments
        working_directory = $WorkingDirectory
        port = $Port
        url = $Url
    } | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Get-MetadataFile $Name)

    Write-Host "Started $Name (PID $($Process.Id))." -ForegroundColor Green
    return $true
}

function Stop-ManagedProcess {
    param([string]$Name)

    $Process = Get-ManagedProcess $Name
    if ($null -eq $Process) {
        if ((Test-Path (Get-PidFile $Name)) -or (Test-Path (Get-MetadataFile $Name))) {
            Write-Host "Removed stale $Name process metadata; no process was stopped." -ForegroundColor Yellow
        }
        else {
            Write-Host "$Name is not running."
        }
        Remove-ManagedState $Name
        return
    }

    $ManagedPid = $Process.Id
    Stop-Process -Id $ManagedPid -ErrorAction Stop
    try {
        [void]$Process.WaitForExit(5000)
    }
    catch {
        # Stop-Process already targeted the validated managed PID.
    }
    Remove-ManagedState $Name
    Write-Host "Stopped $Name (PID $ManagedPid)." -ForegroundColor Green
}

function Show-Status {
    $Rows = foreach ($Name in @("api", "web")) {
        $Process = Get-ManagedProcess $Name
        $Metadata = Read-ManagedMetadata $Name
        [PSCustomObject]@{
            Service = $Name
            State = if ($null -ne $Process) { "running" } else { "stopped" }
            PID = if ($null -ne $Process) { $Process.Id } else { "-" }
            URL = if ($null -ne $Metadata) { [string]$Metadata.url } else { "-" }
        }
    }
    $Rows | Format-Table -AutoSize
    Write-Host "Logs: $CacheRoot"
}

function Show-Logs {
    foreach ($Name in @("api", "web")) {
        Write-Host "`n[$Name stdout]" -ForegroundColor Cyan
        $OutputLog = Get-OutputLog $Name
        if (Test-Path $OutputLog) {
            Get-Content -Tail $Tail $OutputLog
        }
        Write-Host "[$Name stderr]" -ForegroundColor Cyan
        $ErrorLog = Get-ErrorLog $Name
        if (Test-Path $ErrorLog) {
            Get-Content -Tail $Tail $ErrorLog
        }
    }
}

function Start-DevelopmentStack {
    New-Item -ItemType Directory -Force -Path $CacheRoot | Out-Null

    if (-not (Test-Path $EnvFile)) {
        if (-not (Test-Path $EnvExample)) {
            throw ".env and .env.example are both missing."
        }
        Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
        Write-Host "Created local .env from .env.example." -ForegroundColor Yellow
    }
    if (-not (Test-Path $Uv) -or -not (Test-Path $Python)) {
        throw "Python dependencies are missing. Run .\scripts\bootstrap.ps1 first."
    }
    if ($null -eq $NodeCommand -or -not (Test-Path $NextCli)) {
        throw "Web dependencies are missing. Install Node.js and run pnpm install first."
    }

    if (-not $SkipInfra) {
        & (Join-Path $PSScriptRoot "infra.ps1") up
    }

    Push-Location $ProjectRoot
    try {
        & $Uv run alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw "Database migration failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }

    $SavedEnvironment = @{}
    foreach ($Name in @("APP_URL", "API_URL", "NEXT_PUBLIC_API_URL", "CORS_ORIGINS")) {
        $SavedEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
    }

    $ApiUrl = "http://127.0.0.1:$ApiPort"
    $WebUrl = "http://127.0.0.1:$WebPort"
    $ApiStarted = $false
    $WebStarted = $false
    try {
        $env:APP_URL = $WebUrl
        $env:API_URL = $ApiUrl
        $env:NEXT_PUBLIC_API_URL = $ApiUrl
        $env:CORS_ORIGINS = "[`"http://localhost:$WebPort`",`"$WebUrl`"]"

        $ApiStarted = Start-ManagedProcess `
            -Name "api" `
            -Executable $Python `
            -Arguments @("-m", "uvicorn", "discovery_lab.main:app", "--host", "127.0.0.1", "--port", [string]$ApiPort) `
            -Port $ApiPort `
            -Url $ApiUrl
        Wait-HttpEndpoint "$ApiUrl/health"

        $WebStarted = Start-ManagedProcess `
            -Name "web" `
            -Executable $NodeCommand.Source `
            -Arguments @($NextCli, "dev", "--hostname", "127.0.0.1", "--port", [string]$WebPort) `
            -Port $WebPort `
            -Url $WebUrl `
            -WorkingDirectory (Join-Path $ProjectRoot "apps\web")
        Wait-HttpEndpoint $WebUrl
    }
    catch {
        if ($WebStarted) {
            Stop-ManagedProcess "web"
        }
        if ($ApiStarted) {
            Stop-ManagedProcess "api"
        }
        throw
    }
    finally {
        foreach ($Name in $SavedEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($Name, $SavedEnvironment[$Name], "Process")
        }
    }

    Write-Host "`nDiscoveryLab is ready:" -ForegroundColor Cyan
    Write-Host "  Product: $WebUrl"
    Write-Host "  API:     $ApiUrl/docs"
    Write-Host "  Logs:    $CacheRoot"
}

function Stop-DevelopmentStack {
    Stop-ManagedProcess "web"
    Stop-ManagedProcess "api"
}

switch ($Action) {
    "start" {
        Start-DevelopmentStack
    }
    "stop" {
        Stop-DevelopmentStack
        if ($StopInfra) {
            & (Join-Path $PSScriptRoot "infra.ps1") down
        }
    }
    "restart" {
        Stop-DevelopmentStack
        Start-DevelopmentStack
    }
    "status" {
        Show-Status
    }
    "logs" {
        Show-Logs
    }
}
