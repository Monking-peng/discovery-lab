from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "fixtures" / "helphub"


def _manifest() -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / "curated-evidence.json").read_text(encoding="utf-8"))


def _ticket_ids() -> set[str]:
    with (FIXTURE_ROOT / "tickets.csv").open(encoding="utf-8", newline="") as handle:
        return {row["ticket_id"] for row in csv.DictReader(handle)}


def test_curated_manifest_is_referentially_complete_and_honest() -> None:
    manifest = _manifest()
    items = manifest["items"]
    curated_ids = [item["match"]["ticket_id"] for item in items]

    assert manifest["profile"] == "helphub-curated-evidence.v1"
    assert len(curated_ids) == len(set(curated_ids)) == 6
    assert set(curated_ids) <= _ticket_ids()
    assert all(item["match"]["source_name"] == "tickets.csv" for item in items)
    assert all(item["observation"] and item["interpretation"] for item in items)
    assert "fixture" in manifest["review_note"].lower()

    claim = manifest["claim"]
    edges = claim["edges"]
    assert {edge["ticket_id"] for edge in edges} == set(curated_ids)
    assert {edge["relationship"] for edge in edges} >= {
        "supports",
        "contradicts",
        "contextualizes",
    }
    assert all(0 <= edge["relevance"] <= 100 for edge in edges)
    assert claim["counterevidence_check_status"] == "FOUND"
    assert claim["review"]["decision"] == "ACCEPT"

    opportunity = manifest["opportunity"]
    assert opportunity["client_request_id"].endswith(".v1")
    assert 0 <= opportunity["confidence"] <= 1
    assert opportunity["assumptions"]
    assert opportunity["risks"]


def test_seed_script_uses_only_the_public_workflow_endpoints() -> None:
    script = (ROOT / "scripts" / "seed-helphub.ps1").read_text(encoding="utf-8-sig")

    for endpoint in (
        "/v1/evidence/$($Evidence.evidence_id)/revisions",
        "/v1/evidence/$($Evidence.evidence_id)/reviews",
        "/v1/studies/$StudyId/claims",
        "/v1/claim-revisions/$($Claim.claim_revision_id)/reviews",
        "/v1/studies/$StudyId/opportunities",
        "/v1/studies/$StudyId/agent-runs",
        "/v1/tool-calls/$($WriteCall.id)/approvals",
        "/v1/experiments/$ExperimentId/decisions",
        "/v1/decisions/$($Decision.id)/prds",
        "/v1/prds/$($Prd.id)",
    ):
        assert endpoint in script

    lowered = script.lower()
    assert "invoke-sqlcmd" not in lowered
    assert "psql" not in lowered
    assert "sqlalchemy" not in lowered


def test_one_click_launcher_migrates_then_seeds_the_repeatable_demo() -> None:
    launcher = (ROOT / "scripts" / "launch.ps1").read_text(encoding="utf-8-sig")
    dev_script = (ROOT / "scripts" / "dev.ps1").read_text(encoding="utf-8-sig")

    assert "alembic upgrade head" in dev_script
    assert '"seed-helphub.ps1"' in launcher
    assert "-ApiUrl $ApiUrl" in launcher
    assert "-WebUrl $ProductUrl" in launcher
    assert "[switch]$SkipSeed" in launcher
