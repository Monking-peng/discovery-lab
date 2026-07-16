[CmdletBinding()]
param(
    [string]$ApiUrl = "http://127.0.0.1:8010",
    [string]$WebUrl = "http://127.0.0.1:3010",
    [string]$StudyTitle = "HelpHub Support Workflow Discovery",
    [string]$StateFile = "",
    [switch]$ForceNew
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FixtureRoot = Join-Path $ProjectRoot "fixtures\helphub"
$CuratedManifestPath = Join-Path $FixtureRoot "curated-evidence.json"
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
                $ErrorProperty = $ErrorPayload.PSObject.Properties["error"]
                $DetailProperty = $ErrorPayload.PSObject.Properties["detail"]
                if (
                    $null -ne $ErrorProperty -and
                    $null -ne $ErrorProperty.Value.PSObject.Properties["message"] -and
                    -not [string]::IsNullOrWhiteSpace(
                        [string]$ErrorProperty.Value.PSObject.Properties["message"].Value
                    )
                ) {
                    $Message = [string]$ErrorProperty.Value.PSObject.Properties["message"].Value
                }
                elseif ($null -ne $DetailProperty) {
                    $Message = [string]$DetailProperty.Value
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

function ConvertTo-HashtableDeep {
    param([object]$InputObject)

    if ($null -eq $InputObject) {
        return $null
    }
    if ($InputObject -is [Collections.IDictionary]) {
        $Result = @{}
        foreach ($Key in $InputObject.Keys) {
            $Result[[string]$Key] = ConvertTo-HashtableDeep $InputObject[$Key]
        }
        return $Result
    }
    if ($InputObject -is [PSCustomObject]) {
        $Result = @{}
        foreach ($Property in $InputObject.PSObject.Properties) {
            $Result[$Property.Name] = ConvertTo-HashtableDeep $Property.Value
        }
        return $Result
    }
    if (
        $InputObject -is [Collections.IEnumerable] -and
        $InputObject -isnot [string]
    ) {
        $Items = @()
        foreach ($Item in $InputObject) {
            $Items += , (ConvertTo-HashtableDeep $Item)
        }
        return , $Items
    }
    return $InputObject
}

function Initialize-SeedStateShape {
    param([hashtable]$State)

    if (-not $State.ContainsKey("schema_version")) {
        $State.schema_version = 2
    }
    if (-not $State.ContainsKey("sources") -or $null -eq $State.sources) {
        $State.sources = @{}
    }
    if (-not $State.ContainsKey("curation") -or $null -eq $State.curation) {
        $State.curation = @{}
    }
    if (-not $State.curation.ContainsKey("evidence") -or $null -eq $State.curation.evidence) {
        $State.curation.evidence = @{}
    }
    if (-not $State.curation.ContainsKey("claim") -or $null -eq $State.curation.claim) {
        $State.curation.claim = @{}
    }
    if (
        -not $State.curation.ContainsKey("opportunity") -or
        $null -eq $State.curation.opportunity
    ) {
        $State.curation.opportunity = @{}
    }
    return $State
}

function Import-SeedState {
    if (-not (Test-Path -LiteralPath $StateFile -PathType Leaf)) {
        return $null
    }

    try {
        $Payload = Get-Content -Raw -Encoding UTF8 -LiteralPath $StateFile | ConvertFrom-Json
        $State = ConvertTo-HashtableDeep $Payload
        if (
            $State -isnot [hashtable] -or
            -not $State.ContainsKey("api_url") -or
            -not $State.ContainsKey("study_id")
        ) {
            throw "Seed state is missing its API URL or Study ID."
        }
        return Initialize-SeedStateShape $State
    }
    catch {
        Write-Host "Ignoring unreadable seed state at $StateFile." -ForegroundColor Yellow
        return $null
    }
}

function Save-SeedState {
    param([hashtable]$State)

    $State.updated_at = [DateTime]::UtcNow.ToString("o")
    $TemporaryPath = "$StateFile.tmp"
    $State | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 -LiteralPath $TemporaryPath
    Move-Item -Force -LiteralPath $TemporaryPath -Destination $StateFile
}

function Get-ProvenanceValue {
    param(
        [object]$Evidence,
        [string]$Name
    )

    if ($null -eq $Evidence.provenance) {
        return $null
    }
    $Property = $Evidence.provenance.PSObject.Properties[$Name]
    if ($null -eq $Property) {
        return $null
    }
    return $Property.Value
}

function Test-EvidenceQuoteMatchesTicket {
    param(
        [object]$Evidence,
        [object]$TicketRow
    )

    try {
        $QuoteRow = [string]$Evidence.quote | ConvertFrom-Json
    }
    catch {
        return $false
    }
    $TicketProperties = @($TicketRow.PSObject.Properties)
    $QuoteProperties = @($QuoteRow.PSObject.Properties)
    if ($TicketProperties.Count -ne $QuoteProperties.Count) {
        return $false
    }
    foreach ($Property in $TicketProperties) {
        $QuoteProperty = $QuoteRow.PSObject.Properties[$Property.Name]
        if (
            $null -eq $QuoteProperty -or
            [string]$QuoteProperty.Value -cne [string]$Property.Value
        ) {
            return $false
        }
    }
    return $true
}

function Get-TicketRows {
    param([string]$CsvPath)

    $Rows = @{}
    foreach ($Row in @(Import-Csv -LiteralPath $CsvPath -Encoding UTF8)) {
        $TicketId = [string]$Row.ticket_id
        if ([string]::IsNullOrWhiteSpace($TicketId) -or $Rows.ContainsKey($TicketId)) {
            throw "tickets.csv must contain unique, non-empty ticket_id values."
        }
        $Rows[$TicketId] = $Row
    }
    return $Rows
}

function Assert-CuratedManifest {
    param(
        [object]$Manifest,
        [hashtable]$TicketRows
    )

    if ([string]$Manifest.profile -notmatch '^helphub-curated-evidence\.v\d+$') {
        throw "curated-evidence.json has an unsupported or missing profile version."
    }
    if (
        [string]::IsNullOrWhiteSpace([string]$Manifest.reviewer_name) -or
        [string]::IsNullOrWhiteSpace([string]$Manifest.review_note)
    ) {
        throw "curated-evidence.json must name the fixture curator and review note."
    }

    $CuratedTicketIds = @{}
    foreach ($Item in @($Manifest.items)) {
        $TicketId = [string]$Item.match.ticket_id
        if (
            [string]::IsNullOrWhiteSpace($TicketId) -or
            -not $TicketRows.ContainsKey($TicketId) -or
            $CuratedTicketIds.ContainsKey($TicketId)
        ) {
            throw "Curated ticket '$TicketId' is missing from tickets.csv or duplicated."
        }
        if ([string]$Item.match.source_name -cne "tickets.csv") {
            throw "Curated ticket '$TicketId' must be pinned to tickets.csv."
        }
        if ([string]::IsNullOrWhiteSpace([string]$Item.observation)) {
            throw "Curated ticket '$TicketId' is missing its human-authored observation."
        }
        $CuratedTicketIds[$TicketId] = $true
    }

    $SupportCount = 0
    $AllowedRelationships = @("supports", "contradicts", "contextualizes", "insufficient_for")
    foreach ($Edge in @($Manifest.claim.edges)) {
        $TicketId = [string]$Edge.ticket_id
        if (-not $CuratedTicketIds.ContainsKey($TicketId)) {
            throw "Claim edge '$TicketId' does not reference a curated Evidence item."
        }
        $Relationship = [string]$Edge.relationship
        if ($Relationship -notin $AllowedRelationships) {
            throw "Claim edge '$TicketId' has unsupported relationship '$Relationship'."
        }
        if ($Relationship -eq "supports") {
            $SupportCount += 1
        }
        $Relevance = [double]$Edge.relevance
        if ($Relevance -lt 0 -or $Relevance -gt 100) {
            throw "Claim edge '$TicketId' relevance must be between 0 and 100."
        }
    }
    if ($SupportCount -eq 0) {
        throw "The curated Claim must contain at least one supporting Evidence edge."
    }
    if ([string]$Manifest.claim.review.decision -ne "ACCEPT") {
        throw "The curated Claim review must explicitly use ACCEPT."
    }
    if (
        [string]::IsNullOrWhiteSpace([string]$Manifest.opportunity.title) -or
        [string]::IsNullOrWhiteSpace([string]$Manifest.opportunity.problem_statement) -or
        [string]::IsNullOrWhiteSpace([string]$Manifest.opportunity.desired_outcome) -or
        [string]::IsNullOrWhiteSpace([string]$Manifest.opportunity.next_step)
    ) {
        throw "The curated Opportunity must include a title, problem, outcome, and next step."
    }
}

function Find-TicketEvidence {
    param(
        [object]$EvidencePayload,
        [object]$ManifestItem,
        [object]$TicketRow
    )

    $SourceName = [string]$ManifestItem.match.source_name
    $TicketId = [string]$ManifestItem.match.ticket_id
    $Matches = @(
        foreach ($Evidence in @($EvidencePayload.items)) {
            if (
                [string]$Evidence.source_name -ceq $SourceName -and
                (Test-EvidenceQuoteMatchesTicket -Evidence $Evidence -TicketRow $TicketRow)
            ) {
                $Evidence
            }
        }
    )
    if ($Matches.Count -ne 1) {
        throw ((
                "Expected exactly one immutable Evidence match for {0}/{1}; found {2}. " +
                "Use -ForceNew if this Study was manually modified."
            ) -f $SourceName, $TicketId, $Matches.Count)
    }
    return $Matches[0]
}

function Invoke-CuratedEvidenceSeed {
    param(
        [object]$Manifest,
        [hashtable]$TicketRows,
        [object]$EvidencePayload,
        [string]$StudyId,
        [hashtable]$State
    )

    $ByTicket = @{}
    foreach ($Item in @($Manifest.items)) {
        $TicketId = [string]$Item.match.ticket_id
        $Evidence = Find-TicketEvidence `
            -EvidencePayload $EvidencePayload `
            -ManifestItem $Item `
            -TicketRow $TicketRows[$TicketId]

        $Saved = if ($State.curation.evidence.ContainsKey($TicketId)) {
            $State.curation.evidence[$TicketId]
        }
        else {
            $null
        }
        if (
            $null -ne $Saved -and
            -not [string]::IsNullOrWhiteSpace([string]$Saved.evidence_id) -and
            [string]$Saved.evidence_id -ne [string]$Evidence.evidence_id
        ) {
            throw "Seed state for '$TicketId' points to another Evidence Unit. Use -ForceNew."
        }

        $BaseRevisionId = [string]$Evidence.evidence_revision_id
        if (
            $null -ne $Saved -and
            -not [string]::IsNullOrWhiteSpace([string]$Saved.base_revision_id)
        ) {
            $BaseRevisionId = [string]$Saved.base_revision_id
        }
        elseif ((Get-ProvenanceValue -Evidence $Evidence -Name "human_authored") -eq $true) {
            $Editor = [string](Get-ProvenanceValue -Evidence $Evidence -Name "editor")
            $EditRationale = [string](
                Get-ProvenanceValue -Evidence $Evidence -Name "edit_rationale"
            )
            $ParentRevisionId = [string](
                Get-ProvenanceValue -Evidence $Evidence -Name "parent_revision_id"
            )
            if (
                $Editor -ne [string]$Manifest.reviewer_name -or
                $EditRationale -ne [string]$Manifest.review_note -or
                [string]$Evidence.observation -ne [string]$Item.observation -or
                [string]::IsNullOrWhiteSpace($ParentRevisionId)
            ) {
                throw (
                    "Evidence for '$TicketId' already has a non-fixture human revision. " +
                    "The seed will not overwrite it; use -ForceNew for a clean demo."
                )
            }
            $BaseRevisionId = $ParentRevisionId
        }

        $AuthorRequestId = "{0}:{1}:evidence:{2}:author" -f @(
            [string]$Manifest.profile,
            $StudyId,
            $TicketId
        )
        Write-Host "Curating Evidence for $TicketId..." -ForegroundColor Cyan
        $Authored = Invoke-JsonApiRequest `
            -Method "POST" `
            -Path "/v1/evidence/$($Evidence.evidence_id)/revisions" `
            -Body @{
                base_revision_id = $BaseRevisionId
                observation = [string]$Item.observation
                interpretation = [string]$Item.interpretation
                inference = [string]$Item.inference
                confidence = [double]$Item.confidence
                tags = @($Item.tags)
                editor = [string]$Manifest.reviewer_name
                rationale = [string]$Manifest.review_note
                client_request_id = $AuthorRequestId
            }
        if ([string]$Authored.evidence_id -ne [string]$Evidence.evidence_id) {
            throw "Authored revision for '$TicketId' returned another Evidence Unit."
        }

        $State.curation.evidence[$TicketId] = @{
            ticket_id = $TicketId
            evidence_id = [string]$Evidence.evidence_id
            source_id = [string]$Evidence.source_id
            base_revision_id = $BaseRevisionId
            evidence_revision_id = [string]$Authored.evidence_revision_id
            author_client_request_id = $AuthorRequestId
            author_status = "SUCCEEDED"
        }
        Save-SeedState $State

        $ReviewRequestId = "{0}:{1}:evidence:{2}:review" -f @(
            [string]$Manifest.profile,
            $StudyId,
            $TicketId
        )
        $Review = Invoke-JsonApiRequest `
            -Method "POST" `
            -Path "/v1/evidence/$($Evidence.evidence_id)/reviews" `
            -Body @{
                evidence_revision_id = [string]$Authored.evidence_revision_id
                decision = "ACCEPT"
                reviewer = [string]$Manifest.reviewer_name
                rationale = [string]$Manifest.review_note
                client_request_id = $ReviewRequestId
            }
        $State.curation.evidence[$TicketId].review_id = [string]$Review.id
        $State.curation.evidence[$TicketId].review_client_request_id = $ReviewRequestId
        $State.curation.evidence[$TicketId].review_status = [string]$Review.decision
        Save-SeedState $State

        $Context = Invoke-JsonApiRequest `
            -Method "GET" `
            -Path (
                "/v1/evidence/{0}/context?evidence_revision_id={1}" -f @(
                    [string]$Evidence.evidence_id,
                    [string]$Authored.evidence_revision_id
                )
            )
        if (
            -not $Context.integrity.segment_hash_matches -or
            -not $Context.integrity.evidence_hash_matches -or
            -not $Context.integrity.quote_matches_segment -or
            [string]$Context.evidence.review_status -ne "reviewed" -or
            (Get-ProvenanceValue -Evidence $Context.evidence -Name "human_authored") -ne $true -or
            -not (
                Test-EvidenceQuoteMatchesTicket `
                    -Evidence $Context.evidence `
                    -TicketRow $TicketRows[$TicketId]
            )
        ) {
            throw "Curated Evidence '$TicketId' failed exact-revision integrity or review checks."
        }

        $ByTicket[$TicketId] = @{
            evidence_id = [string]$Evidence.evidence_id
            evidence_revision_id = [string]$Authored.evidence_revision_id
            source_id = [string]$Evidence.source_id
        }
    }
    return $ByTicket
}

function Invoke-CuratedClaimSeed {
    param(
        [object]$Manifest,
        [hashtable]$EvidenceByTicket,
        [string]$StudyId,
        [hashtable]$State
    )

    $Edges = @()
    foreach ($ManifestEdge in @($Manifest.claim.edges)) {
        $TicketId = [string]$ManifestEdge.ticket_id
        $Evidence = $EvidenceByTicket[$TicketId]
        if ($null -eq $Evidence) {
            throw "Claim edge '$TicketId' has no curated Evidence Revision."
        }
        $Relevance = [double]$ManifestEdge.relevance
        if ($Relevance -gt 1) {
            $Relevance = $Relevance / 100
        }
        $Edges += , @{
            evidence_id = [string]$Evidence.evidence_id
            evidence_revision_id = [string]$Evidence.evidence_revision_id
            relation = [string]$ManifestEdge.relationship
            relation_confirmed = $true
            rationale = [string]$ManifestEdge.rationale
            relevance = $Relevance
        }
    }

    $ClaimRequestId = "{0}:{1}" -f @(
        [string]$Manifest.claim.client_request_id,
        $StudyId
    )
    Write-Host "Creating the revision-pinned HelpHub Claim..." -ForegroundColor Cyan
    $Claim = Invoke-JsonApiRequest `
        -Method "POST" `
        -Path "/v1/studies/$StudyId/claims" `
        -Body @{
            statement = [string]$Manifest.claim.statement
            topic_key = [string]$Manifest.claim.topic_key
            summary = [string]$Manifest.claim.summary
            rationale = [string]$Manifest.claim.rationale
            confidence = [double]$Manifest.claim.confidence
            counterevidence_status = [string]$Manifest.claim.counterevidence_check_status
            counterevidence_summary = [string]$Manifest.claim.counterevidence_summary
            provenance = @{
                authoring_mode = "human"
                fixture_profile = [string]$Manifest.profile
                seeded_via = "public_api"
                synthetic_portfolio = $true
            }
            evidence_edges = $Edges
            client_request_id = $ClaimRequestId
        }
    $State.curation.claim = @{
        claim_id = [string]$Claim.claim_id
        claim_revision_id = [string]$Claim.claim_revision_id
        create_client_request_id = $ClaimRequestId
        create_status = "SUCCEEDED"
    }
    Save-SeedState $State

    $ReviewRequestId = "{0}:{1}:review" -f @(
        [string]$Manifest.claim.client_request_id,
        $StudyId
    )
    $ClaimReview = Invoke-JsonApiRequest `
        -Method "POST" `
        -Path "/v1/claim-revisions/$($Claim.claim_revision_id)/reviews" `
        -Body @{
            decision = [string]$Manifest.claim.review.decision
            reviewer = [string]$Manifest.claim.review.reviewer_name
            rationale = [string]$Manifest.claim.review.note
            client_request_id = $ReviewRequestId
        }
    $State.curation.claim.review_id = [string]$ClaimReview.id
    $State.curation.claim.review_client_request_id = $ReviewRequestId
    $State.curation.claim.review_status = [string]$ClaimReview.decision
    Save-SeedState $State

    $FinalClaim = Invoke-JsonApiRequest `
        -Method "GET" `
        -Path (
            "/v1/claims/{0}?claim_revision_id={1}" -f @(
                [string]$Claim.claim_id,
                [string]$Claim.claim_revision_id
            )
        )
    if (
        [string]$FinalClaim.status -ne "REVIEWED" -or
        [string]$FinalClaim.revision_status -ne "REVIEWED" -or
        @($FinalClaim.publication_blockers).Count -ne 0
    ) {
        throw (
            "The curated Claim is not publishable after replay. This Study may have " +
            "newer human review activity; use -ForceNew for a clean demo."
        )
    }
    $State.curation.claim.final_status = [string]$FinalClaim.status
    Save-SeedState $State
    return $FinalClaim
}

function Invoke-CuratedOpportunitySeed {
    param(
        [object]$Manifest,
        [object]$Claim,
        [string]$StudyId,
        [hashtable]$State
    )

    $OpportunityRequestId = "{0}:{1}" -f @(
        [string]$Manifest.opportunity.client_request_id,
        $StudyId
    )
    Write-Host "Creating the Claim-bound Opportunity Draft..." -ForegroundColor Cyan
    $Opportunity = Invoke-JsonApiRequest `
        -Method "POST" `
        -Path "/v1/studies/$StudyId/opportunities" `
        -Body @{
            claim_id = [string]$Claim.claim_id
            claim_revision_id = [string]$Claim.claim_revision_id
            title = [string]$Manifest.opportunity.title
            problem_statement = [string]$Manifest.opportunity.problem_statement
            desired_outcome = [string]$Manifest.opportunity.desired_outcome
            next_step = [string]$Manifest.opportunity.next_step
            rationale = [string]$Manifest.opportunity.rationale
            confidence = [double]$Manifest.opportunity.confidence
            assumptions = @($Manifest.opportunity.assumptions)
            risks = @($Manifest.opportunity.risks)
            provenance = @{
                authoring_mode = "human"
                fixture_profile = [string]$Manifest.profile
                seeded_via = "public_api"
                synthetic_portfolio = $true
            }
            client_request_id = $OpportunityRequestId
        }
    if (
        [string]$Opportunity.status -ne "DRAFT" -or
        [string]$Opportunity.claim_id -ne [string]$Claim.claim_id -or
        [string]$Opportunity.claim_revision_id -ne [string]$Claim.claim_revision_id -or
        [bool]$Opportunity.publishable -ne $false -or
        "OPPORTUNITY_DRAFT_NOT_PUBLISHED" -notin @($Opportunity.publication_blockers)
    ) {
        throw "The Opportunity Draft did not preserve its exact Claim lineage or draft gate."
    }
    $State.curation.opportunity = @{
        status = [string]$Opportunity.status
        opportunity_id = [string]$Opportunity.id
        client_request_id = $OpportunityRequestId
        bound_claim_id = [string]$Claim.claim_id
        bound_claim_revision_id = [string]$Claim.claim_revision_id
        title = [string]$Manifest.opportunity.title
    }
    Save-SeedState $State
    return $Opportunity
}

function Show-SeedSummary {
    param(
        [object]$Study,
        [object]$EvidencePayload,
        [hashtable]$CuratedEvidence,
        [object]$Claim,
        [object]$Opportunity
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
    Write-Host "  Human-reviewed Evidence: $($CuratedEvidence.Count)"
    Write-Host "  Reviewed Claim: $($Claim.claim_id) (revision $($Claim.revision))"
    Write-Host "  Opportunity Draft: $($Opportunity.id) (pinned to Claim revision $($Claim.revision))"
    Write-Host "  Integrity spot-checks: $IntegrityPassed/$([Math]::Min(3, $EvidenceItems.Count))"
    Write-Host "  Resume state: $StateFile"
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
        if (-not (Test-Path -LiteralPath $Fixture.path -PathType Leaf)) {
            throw "Missing HelpHub fixture: $($Fixture.path)"
        }
    }
    if (-not (Test-Path -LiteralPath $CuratedManifestPath -PathType Leaf)) {
        throw "Missing HelpHub curated manifest: $CuratedManifestPath"
    }
    $Manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $CuratedManifestPath |
        ConvertFrom-Json
    $TicketRows = Get-TicketRows (Join-Path $FixtureRoot "tickets.csv")
    Assert-CuratedManifest -Manifest $Manifest -TicketRows $TicketRows

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
                Write-Host (
                    "Found an existing HelpHub study; source upload will be recovered " +
                    "from its public API state."
                ) -ForegroundColor Green
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
        $State = Initialize-SeedStateShape @{
            schema_version = 2
            api_url = $ApiUrl
            study_id = [string]$Study.id
            title = [string]$Study.title
            sources = @{}
            manifest_profile = [string]$Manifest.profile
        }
        Save-SeedState $State
        Write-Host "Created HelpHub study $($Study.id)." -ForegroundColor Cyan
    }
    elseif ($null -eq $State) {
        $State = Initialize-SeedStateShape @{
            schema_version = 2
            api_url = $ApiUrl
            study_id = [string]$Study.id
            title = [string]$Study.title
            sources = @{}
            manifest_profile = [string]$Manifest.profile
        }
        Save-SeedState $State
    }

    if (
        $State.ContainsKey("manifest_profile") -and
        -not [string]::IsNullOrWhiteSpace([string]$State.manifest_profile) -and
        [string]$State.manifest_profile -ne [string]$Manifest.profile
    ) {
        throw (
            "Seed state uses manifest profile '$($State.manifest_profile)' but the fixture " +
            "uses '$($Manifest.profile)'. Use -ForceNew to preserve immutable revisions."
        )
    }
    $State.manifest_profile = [string]$Manifest.profile
    Save-SeedState $State

    $ExistingSources = Invoke-JsonApiRequest `
        -Method "GET" `
        -Path "/v1/studies/$($Study.id)/sources?limit=100&offset=0"
    foreach ($Fixture in $Fixtures) {
        $Name = [string]$Fixture.name
        $SavedSource = if ($State.sources.ContainsKey($Name)) {
            $State.sources[$Name]
        }
        else {
            $null
        }
        $Matches = @(
            $ExistingSources.items | Where-Object {
                [string]$_.display_name -ceq $Name -or
                [string]$_.revision.filename -ceq $Name
            }
        )
        if ($null -ne $SavedSource) {
            $Matches = @(
                $Matches | Where-Object { [string]$_.source_id -eq [string]$SavedSource.source_id }
            )
            if ($Matches.Count -eq 0) {
                Write-Host "Saved source '$Name' no longer exists; recovering from Study state." `
                    -ForegroundColor Yellow
                $State.sources.Remove($Name)
                $SavedSource = $null
                $Matches = @(
                    $ExistingSources.items | Where-Object {
                        [string]$_.display_name -ceq $Name -or
                        [string]$_.revision.filename -ceq $Name
                    }
                )
            }
        }
        if ($null -eq $SavedSource -and $Matches.Count -gt 1) {
            throw (
                "Study has multiple sources named '$Name' and no unambiguous resume state. " +
                "Use -ForceNew."
            )
        }
        if ($Matches.Count -eq 1) {
            $ExistingSource = $Matches[0]
            $RunId = if (
                $null -ne $SavedSource -and $SavedSource.ContainsKey("run_id")
            ) {
                [string]$SavedSource.run_id
            }
            else {
                ""
            }
            $State.sources[$Name] = @{
                source_id = [string]$ExistingSource.source_id
                processed = [string]$ExistingSource.domain_status -eq "PROCESSED"
                run_id = $RunId
            }
            Save-SeedState $State
        }
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
    $CuratedEvidence = Invoke-CuratedEvidenceSeed `
        -Manifest $Manifest `
        -TicketRows $TicketRows `
        -EvidencePayload $Evidence `
        -StudyId ([string]$Study.id) `
        -State $State
    $Claim = Invoke-CuratedClaimSeed `
        -Manifest $Manifest `
        -EvidenceByTicket $CuratedEvidence `
        -StudyId ([string]$Study.id) `
        -State $State
    $Opportunity = Invoke-CuratedOpportunitySeed `
        -Manifest $Manifest `
        -Claim $Claim `
        -StudyId ([string]$Study.id) `
        -State $State

    $Study = Invoke-JsonApiRequest -Method "GET" -Path "/v1/studies/$($Study.id)"
    $Evidence = Invoke-JsonApiRequest `
        -Method "GET" `
        -Path "/v1/studies/$($Study.id)/evidence?limit=200&offset=0"
    Show-SeedSummary `
        -Study $Study `
        -EvidencePayload $Evidence `
        -CuratedEvidence $CuratedEvidence `
        -Claim $Claim `
        -Opportunity $Opportunity
}
finally {
    $HttpClient.Dispose()
}
