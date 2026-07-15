[CmdletBinding()]
param(
    [string]$ApiUrl = "http://127.0.0.1:8000",
    [string]$WebUrl = "http://127.0.0.1:3000",
    [string]$StudyTitle = "HelpHub Support Workflow Discovery",
    [string]$StateFile = "",
    [switch]$ForceNew
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FixtureRoot = Join-Path $ProjectRoot "fixtures\helphub"
$CacheRoot = Join-Path $ProjectRoot ".cache"
$ApiUrl = $ApiUrl.TrimEnd("/")
if ([string]::IsNullOrWhiteSpace($StateFile)) {
    $StateFile = Join-Path $CacheRoot "helphub-seed.json"
}
elseif (-not [IO.Path]::IsPathRooted($StateFile)) {
    $StateFile = Join-Path $ProjectRoot $StateFile
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $StateFile) | Out-Null

Add-Type -AssemblyName System.Net.Http
$HttpClient = [Net.Http.HttpClient]::new()
$HttpClient.Timeout = [TimeSpan]::FromSeconds(60)
$HttpClient.DefaultRequestHeaders.Accept.Add(
    [Net.Http.Headers.MediaTypeWithQualityHeaderValue]::new("application/json")
)

function Invoke-ApiRequest {
    param(
        [string]$Method,
        [string]$Path,
        [Net.Http.HttpContent]$Content = $null
    )

    $Request = [Net.Http.HttpRequestMessage]::new(
        [Net.Http.HttpMethod]::new($Method),
        "$ApiUrl$Path"
    )
    if ($null -ne $Content) {
        $Request.Content = $Content
    }

    $Response = $null
    try {
        $Response = $HttpClient.SendAsync($Request).GetAwaiter().GetResult()
        $ResponseText = $Response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $Response.IsSuccessStatusCode) {
            $Message = $Response.ReasonPhrase
            try {
                $ErrorPayload = $ResponseText | ConvertFrom-Json
                if ($ErrorPayload.detail) {
                    $Message = [string]$ErrorPayload.detail
                }
            }
            catch {
                if (-not [string]::IsNullOrWhiteSpace($ResponseText)) {
                    $Message = $ResponseText
                }
            }
            $StatusCode = [int]$Response.StatusCode
            throw "API $Method $Path failed (${StatusCode}): $Message"
        }

        if ([string]::IsNullOrWhiteSpace($ResponseText)) {
            return $null
        }
        return $ResponseText | ConvertFrom-Json
    }
    finally {
        if ($null -ne $Response) {
            $Response.Dispose()
        }
        $Request.Dispose()
    }
}

function Invoke-JsonApiRequest {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null
    )

    $Content = $null
    if ($null -ne $Body) {
        $Json = $Body | ConvertTo-Json -Depth 10
        $Content = [Net.Http.StringContent]::new($Json, [Text.Encoding]::UTF8, "application/json")
    }
    return Invoke-ApiRequest -Method $Method -Path $Path -Content $Content
}

function Send-SourceFile {
    param(
        [string]$StudyId,
        [string]$Path,
        [string]$MimeType
    )

    $Stream = [IO.File]::OpenRead($Path)
    $Multipart = [Net.Http.MultipartFormDataContent]::new()
    $FileContent = [Net.Http.StreamContent]::new($Stream)
    $FileContent.Headers.ContentType = [Net.Http.Headers.MediaTypeHeaderValue]::new($MimeType)
    $Multipart.Add($FileContent, "file", [IO.Path]::GetFileName($Path))
    return Invoke-ApiRequest `
        -Method "POST" `
        -Path "/v1/studies/$StudyId/sources" `
        -Content $Multipart
}

function Import-SeedState {
    if (-not (Test-Path $StateFile)) {
        return $null
    }

    try {
        $Payload = Get-Content -Raw -Encoding UTF8 $StateFile | ConvertFrom-Json
        $Sources = @{}
        if ($null -ne $Payload.sources) {
            foreach ($Property in $Payload.sources.PSObject.Properties) {
                $Sources[$Property.Name] = @{
                    source_id = [string]$Property.Value.source_id
                    processed = [bool]$Property.Value.processed
                    run_id = [string]$Property.Value.run_id
                }
            }
        }
        return @{
            api_url = [string]$Payload.api_url
            study_id = [string]$Payload.study_id
            title = [string]$Payload.title
            sources = $Sources
        }
    }
    catch {
        Write-Host "Ignoring unreadable seed state at $StateFile." -ForegroundColor Yellow
        return $null
    }
}

function Save-SeedState {
    param([hashtable]$State)

    $State | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $StateFile
}

function Show-SeedSummary {
    param(
        [object]$Study,
        [object]$EvidencePayload
    )

    $EvidenceItems = @($EvidencePayload.items)
    $IntegrityPassed = 0
    foreach ($Evidence in ($EvidenceItems | Select-Object -First 3)) {
        $Context = Invoke-JsonApiRequest -Method "GET" -Path "/v1/evidence/$($Evidence.id)/context"
        if (
            $Context.integrity.segment_hash_matches -and
            $Context.integrity.evidence_hash_matches -and
            $Context.integrity.quote_matches_segment
        ) {
            $IntegrityPassed += 1
        }
    }

    Write-Host "`nHelpHub seed is ready." -ForegroundColor Green
    Write-Host "  Study:    $($Study.title)"
    Write-Host "  Study ID: $($Study.id)"
    Write-Host "  Sources:  $($Study.source_count)"
    Write-Host "  Evidence: $($EvidencePayload.total)"
    Write-Host "  Integrity spot-checks: $IntegrityPassed/$([Math]::Min(3, $EvidenceItems.Count))"
    Write-Host "  Open: $WebUrl"

    if ($EvidenceItems.Count -gt 0) {
        Write-Host "`nEvidence preview:" -ForegroundColor Cyan
        foreach ($Evidence in ($EvidenceItems | Select-Object -First 5)) {
            $Quote = ([string]$Evidence.quote -replace "\s+", " ").Trim()
            if ($Quote.Length -gt 110) {
                $Quote = $Quote.Substring(0, 107) + "..."
            }
            Write-Host "  - [$($Evidence.source_name) | $($Evidence.locator_label)] $Quote"
        }
    }
}

$Fixtures = @(
    @{
        name = "interviews.md"
        path = Join-Path $FixtureRoot "interviews.md"
        mime_type = "text/markdown"
    },
    @{
        name = "tickets.csv"
        path = Join-Path $FixtureRoot "tickets.csv"
        mime_type = "text/csv"
    }
)

try {
    foreach ($Fixture in $Fixtures) {
        if (-not (Test-Path $Fixture.path)) {
            throw "Missing HelpHub fixture: $($Fixture.path)"
        }
    }

    $Health = Invoke-JsonApiRequest -Method "GET" -Path "/health"
    if ($Health.status -ne "ok") {
        throw "DiscoveryLab API health check did not return ok."
    }

    $State = if ($ForceNew) { $null } else { Import-SeedState }
    $Study = $null
    if ($null -ne $State -and $State.api_url -ne $ApiUrl) {
        Write-Host "Seed state belongs to another API URL; it will not be reused." -ForegroundColor Yellow
        $State = $null
    }
    if ($null -ne $State -and $State.api_url -eq $ApiUrl) {
        try {
            $Study = Invoke-JsonApiRequest -Method "GET" -Path "/v1/studies/$($State.study_id)"
            Write-Host "Resuming HelpHub seed study $($Study.id)." -ForegroundColor Cyan
        }
        catch {
            Write-Host "Saved seed study no longer exists; discovering or creating one." -ForegroundColor Yellow
            $State = $null
        }
    }

    if ($null -eq $Study -and -not $ForceNew) {
        $Studies = Invoke-JsonApiRequest -Method "GET" -Path "/v1/studies?limit=100&offset=0"
        $Study = $Studies.items |
            Where-Object { $_.title -eq $StudyTitle } |
            Select-Object -First 1

        if ($null -ne $Study) {
            if ([int]$Study.source_count -ge $Fixtures.Count -and [int]$Study.evidence_count -gt 0) {
                Write-Host "Found an already-complete HelpHub study; no files were uploaded." -ForegroundColor Green
                $Evidence = Invoke-JsonApiRequest `
                    -Method "GET" `
                    -Path "/v1/studies/$($Study.id)/evidence?limit=200&offset=0"
                Show-SeedSummary -Study $Study -EvidencePayload $Evidence
                return
            }
            if ([int]$Study.source_count -gt 0) {
                throw "Found a partial HelpHub study without resumable local state. Re-run with -ForceNew."
            }
        }
    }

    if ($null -eq $Study) {
        $EffectiveTitle = $StudyTitle
        if ($ForceNew) {
            $EffectiveTitle = "$StudyTitle ($(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))"
        }
        $Study = Invoke-JsonApiRequest -Method "POST" -Path "/v1/studies" -Body @{
            title = $EffectiveTitle
            description = "Synthetic HelpHub research study used to demonstrate traceable evidence extraction."
            decision_question = "Which support workflow should HelpHub improve first, and what evidence supports that choice?"
        }
        $State = @{
            api_url = $ApiUrl
            study_id = [string]$Study.id
            title = [string]$Study.title
            sources = @{}
        }
        Save-SeedState $State
        Write-Host "Created HelpHub study $($Study.id)." -ForegroundColor Cyan
    }
    elseif ($null -eq $State) {
        $State = @{
            api_url = $ApiUrl
            study_id = [string]$Study.id
            title = [string]$Study.title
            sources = @{}
        }
        Save-SeedState $State
    }

    foreach ($Fixture in $Fixtures) {
        $Name = [string]$Fixture.name
        $SourceState = if ($State.sources.ContainsKey($Name)) { $State.sources[$Name] } else { $null }
        if ($null -eq $SourceState) {
            Write-Host "Uploading $Name..." -ForegroundColor Cyan
            $Source = Send-SourceFile `
                -StudyId ([string]$Study.id) `
                -Path ([string]$Fixture.path) `
                -MimeType ([string]$Fixture.mime_type)
            $SourceState = @{
                source_id = [string]$Source.id
                processed = $false
                run_id = ""
            }
            $State.sources[$Name] = $SourceState
            Save-SeedState $State
        }
        else {
            Write-Host "Reusing uploaded $Name ($($SourceState.source_id))."
        }

        if (-not [bool]$SourceState.processed) {
            Write-Host "Processing $Name..." -ForegroundColor Cyan
            $Run = Invoke-JsonApiRequest `
                -Method "POST" `
                -Path "/v1/sources/$($SourceState.source_id):process"
            if ([string]$Run.status -notmatch "^(COMPLETED|completed|SUCCEEDED|succeeded)$") {
                throw "Processing $Name returned unexpected run status '$($Run.status)'."
            }
            $SourceState.processed = $true
            $SourceState.run_id = [string]$Run.id
            Save-SeedState $State
        }
    }

    $Study = Invoke-JsonApiRequest -Method "GET" -Path "/v1/studies/$($Study.id)"
    $Evidence = Invoke-JsonApiRequest `
        -Method "GET" `
        -Path "/v1/studies/$($Study.id)/evidence?limit=200&offset=0"
    Show-SeedSummary -Study $Study -EvidencePayload $Evidence
}
finally {
    $HttpClient.Dispose()
}
