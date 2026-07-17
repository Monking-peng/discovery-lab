from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from test_claim_workflow_api import (
    EvidenceSeed,
    _claim_payload,
    _edge,
    _evidence,
    _review_evidence,
    _study,
)

from discovery_lab.db.models import OpportunityDraft


def _reviewed_claim(
    client: TestClient,
    session_factory: sessionmaker[Session],
    *,
    counterevidence_status: str = "SEARCHED_NONE_FOUND",
) -> tuple[dict[str, object], EvidenceSeed, dict[str, object], dict[str, object]]:
    study = _study(client, title=f"Opportunity workflow {uuid4()}")
    evidence = _evidence(
        session_factory,
        str(study["id"]),
        quote="Reviewed source evidence identifies a bounded workflow problem.",
    )
    _review_evidence(client, evidence)
    payload = _claim_payload(
        [_edge(evidence, relation="supports", confirmed=True)],
        counterevidence_status=counterevidence_status,
    )
    created = client.post(f"/v1/studies/{study['id']}/claims", json=payload)
    assert created.status_code == 201, created.text
    claim = created.json()
    reviewed = client.post(
        f"/v1/claim-revisions/{claim['claim_revision_id']}/reviews",
        json={
            "decision": "ACCEPT",
            "reviewer": "opportunity-reviewer@example.test",
            "rationale": "The exact Claim Revision is suitable for opportunity authoring.",
            "client_request_id": f"claim-review-{uuid4()}",
        },
    )
    assert reviewed.status_code == 201, reviewed.text
    return study, evidence, payload, claim


def _opportunity_payload(
    claim: dict[str, object],
    *,
    request_id: str = "opportunity-draft-1",
) -> dict[str, object]:
    return {
        "claim_id": claim["claim_id"],
        "claim_revision_id": claim["claim_revision_id"],
        "title": "Evidence-backed assisted triage",
        "problem_statement": "Teams miss material signals when reviewing records in isolation.",
        "desired_outcome": "Help a human reviewer recognize risk earlier with exact citations.",
        "next_step": "Test a citation-first suggestion with five support specialists.",
        "rationale": "The reviewed Claim establishes a bounded problem, not a promised solution.",
        "confidence": 0.74,
        "assumptions": [
            "Reviewers can act on cited signals.",
            "Reviewers can act on cited signals.",
        ],
        "risks": ["Automation bias"],
        "provenance": {"authoring_mode": "human"},
        "client_request_id": request_id,
    }


def test_create_list_and_get_draft_preserve_exact_claim_revision_and_never_publish(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study, evidence_seed, _claim_source, claim = _reviewed_claim(client, session_factory)
    response = client.post(
        f"/v1/studies/{study['id']}/opportunities",
        json=_opportunity_payload(claim),
    )
    assert response.status_code == 201, response.text
    draft = response.json()
    assert draft["status"] == "DRAFT"
    assert draft["claim_id"] == claim["claim_id"]
    assert draft["claim_revision_id"] == claim["claim_revision_id"]
    assert draft["claim_context_url"].endswith(f"claim_revision_id={claim['claim_revision_id']}")
    assert draft["publishable"] is False
    assert draft["publication_blockers"] == ["OPPORTUNITY_DRAFT_NOT_PUBLISHED"]
    assert draft["assumptions"] == ["Reviewers can act on cited signals."]
    assert len(draft["content_hash"]) == 64

    replay = client.get(f"/v1/opportunities/{draft['id']}")
    assert replay.status_code == 200
    assert replay.json() == draft

    listing = client.get(f"/v1/studies/{study['id']}/opportunities")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"] == [draft]

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(OpportunityDraft)) == 1

    # The immutable Draft remains replayable, while later lineage changes are
    # reflected as blockers rather than being hidden behind the old response.
    _review_evidence(client, evidence_seed, decision="REJECT")
    blocked_replay = client.get(f"/v1/opportunities/{draft['id']}")
    assert blocked_replay.status_code == 200
    assert blocked_replay.json()["publishable"] is False
    assert "CLAIM_STALE" in blocked_replay.json()["publication_blockers"]
    assert "EVIDENCE_REVIEW_NOT_ACCEPTED" in blocked_replay.json()["publication_blockers"]


def test_counterevidence_not_run_allows_draft_but_remains_a_publication_blocker(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study, _evidence_seed, _claim_source, claim = _reviewed_claim(
        client,
        session_factory,
        counterevidence_status="NOT_RUN",
    )
    response = client.post(
        f"/v1/studies/{study['id']}/opportunities",
        json=_opportunity_payload(claim, request_id="not-run-draft"),
    )
    assert response.status_code == 201, response.text
    assert response.json()["publishable"] is False
    assert response.json()["publication_blockers"] == [
        "OPPORTUNITY_DRAFT_NOT_PUBLISHED",
        "COUNTEREVIDENCE_NOT_RUN",
    ]


def test_opportunity_draft_idempotency_replays_and_rejects_payload_reuse(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study, _evidence_seed, _claim_source, claim = _reviewed_claim(client, session_factory)
    payload = _opportunity_payload(claim, request_id="stable-opportunity-request")
    first = client.post(f"/v1/studies/{study['id']}/opportunities", json=payload)
    repeated = client.post(f"/v1/studies/{study['id']}/opportunities", json=payload)
    assert first.status_code == 201
    assert repeated.status_code == 201
    assert repeated.json()["id"] == first.json()["id"]

    changed = {**payload, "title": "A different title"}
    conflict = client.post(f"/v1/studies/{study['id']}/opportunities", json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"]["reason"] == "idempotency_key_reuse"


def test_proposed_stale_old_and_cross_study_claims_are_ineligible(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    # A Claim without an ACCEPT review is not eligible.
    proposed_study = _study(client, title="Proposed")
    proposed_evidence = _evidence(
        session_factory,
        str(proposed_study["id"]),
        quote="Proposed evidence.",
    )
    _review_evidence(client, proposed_evidence)
    proposed_response = client.post(
        f"/v1/studies/{proposed_study['id']}/claims",
        json=_claim_payload([_edge(proposed_evidence, relation="supports", confirmed=True)]),
    )
    assert proposed_response.status_code == 201
    proposed_claim = proposed_response.json()
    ineligible = client.post(
        f"/v1/studies/{proposed_study['id']}/opportunities",
        json=_opportunity_payload(proposed_claim, request_id="proposed-opportunity"),
    )
    assert ineligible.status_code == 422
    assert ineligible.json()["error"]["code"] == "invalid_opportunity_claim"

    # A later negative Evidence Review explicitly stales an accepted Claim.
    stale_study, stale_evidence, _claim_source, stale_claim = _reviewed_claim(
        client, session_factory
    )
    _review_evidence(client, stale_evidence, decision="REJECT")
    stale = client.post(
        f"/v1/studies/{stale_study['id']}/opportunities",
        json=_opportunity_payload(stale_claim, request_id="stale-opportunity"),
    )
    assert stale.status_code == 422
    assert stale.json()["error"]["details"]["claim_status"] == "STALE"

    # Creating a newer revision makes the formerly reviewed revision historical.
    old_study, _old_evidence, original_payload, old_claim = _reviewed_claim(client, session_factory)
    revision_payload = {
        **original_payload,
        "base_revision_id": old_claim["claim_revision_id"],
        "statement": "A newer exact Claim Revision supersedes the old one.",
        "client_request_id": "newer-claim-revision",
    }
    newer = client.post(
        f"/v1/claims/{old_claim['claim_id']}/revisions",
        json=revision_payload,
    )
    assert newer.status_code == 201, newer.text
    old = client.post(
        f"/v1/studies/{old_study['id']}/opportunities",
        json=_opportunity_payload(old_claim, request_id="old-revision-opportunity"),
    )
    assert old.status_code == 422
    assert "current Claim Revision" in old.json()["error"]["message"]

    other_study = _study(client, title="Wrong study")
    cross_study = client.post(
        f"/v1/studies/{other_study['id']}/opportunities",
        json=_opportunity_payload(newer.json(), request_id="cross-study-opportunity"),
    )
    assert cross_study.status_code == 422
    assert "same Study" in cross_study.json()["error"]["message"]
