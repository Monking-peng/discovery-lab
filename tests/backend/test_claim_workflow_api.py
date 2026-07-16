from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from discovery_lab.db.models import (
    Claim,
    ClaimReview,
    ClaimRevision,
    EvidenceReview,
    EvidenceRevision,
    EvidenceUnit,
    Segment,
    Source,
    SourceRevision,
)
from discovery_lab.services.evidence_integrity import evidence_content_hash
from discovery_lab.services.hashing import sha256_text


@dataclass(frozen=True, slots=True)
class EvidenceSeed:
    evidence_id: UUID
    evidence_revision_id: UUID
    source_id: UUID
    source_revision_id: UUID


def _study(client: TestClient, title: str = "Claim workflow") -> dict[str, object]:
    response = client.post(
        "/v1/studies",
        json={"title": title, "research_question": "What should we build?"},
    )
    assert response.status_code == 201
    return response.json()


def _evidence(
    session_factory: sessionmaker[Session],
    study_id: str,
    *,
    quote: str,
    synthetic: bool = False,
    simulation: bool = False,
) -> EvidenceSeed:
    source_hash = sha256_text(quote)
    with session_factory() as session:
        source = Source(
            study_id=UUID(study_id),
            display_name=f"Source for {quote[:20]}",
            source_type="upload",
            status="PROCESSED",
        )
        session.add(source)
        session.flush()
        source_revision = SourceRevision(
            source_id=source.id,
            revision=1,
            filename="research.txt",
            mime_type="text/plain",
            byte_size=len(quote.encode()),
            content_hash=source_hash,
            blob_uri=f"memory://{source_hash}",
            provenance={"fixture": True},
        )
        session.add(source_revision)
        session.flush()
        stable_segment_id = f"segment-{uuid4()}"
        locator = {
            "kind": "text",
            "source_revision_id": str(source_revision.id),
            "segment_id": stable_segment_id,
            "source_sha256": source_hash,
            "char_start": 0,
            "char_end": len(quote),
            "quote_sha256": sha256_text(quote),
        }
        segment = Segment(
            source_revision_id=source_revision.id,
            ordinal=0,
            text=quote,
            content_hash=sha256_text(quote),
            locator=locator,
            provenance={"stable_segment_id": stable_segment_id},
        )
        session.add(segment)
        evidence_unit = EvidenceUnit(study_id=UUID(study_id))
        session.add(evidence_unit)
        session.flush()
        provenance = {
            "confidence": 0.92,
            "tags": ["fixture", "human"],
            "synthetic_demo": synthetic,
            "simulation_output": simulation,
            "extraction_method": "deterministic_demo" if synthetic else "openai_responses",
            "verification": {
                "verified": True,
                "exact_quote_match": True,
                "locator_replayable": True,
                "source_hash_match": True,
                "semantic_support_checked": False,
            },
        }
        evidence_revision = EvidenceRevision(
            evidence_unit_id=evidence_unit.id,
            source_revision_id=source_revision.id,
            segment_id=segment.id,
            revision=1,
            evidence_type="source_excerpt",
            quote=quote,
            observation=quote,
            interpretation=None,
            inference=None,
            review_status="PROPOSED",
            locator=locator,
            content_hash=evidence_content_hash(
                quote=quote,
                observation=quote,
                interpretation=None,
                inference=None,
                evidence_type="source_excerpt",
                locator=locator,
                confidence=0.92,
                tags=["fixture", "human"],
                synthetic_demo=synthetic,
                extraction_method=("deterministic_demo" if synthetic else "openai_responses"),
            ),
            provenance=provenance,
        )
        session.add(evidence_revision)
        session.commit()
        return EvidenceSeed(
            evidence_id=evidence_unit.id,
            evidence_revision_id=evidence_revision.id,
            source_id=source.id,
            source_revision_id=source_revision.id,
        )


def _review_evidence(
    client: TestClient,
    evidence: EvidenceSeed,
    *,
    decision: str = "ACCEPT",
    request_id: str | None = None,
) -> dict[str, object]:
    response = client.post(
        f"/v1/evidence/{evidence.evidence_id}/reviews",
        json={
            "evidence_revision_id": str(evidence.evidence_revision_id),
            "decision": decision,
            "reviewer": "human@example.test",
            "rationale": f"Human review: {decision}",
            "client_request_id": request_id or f"evidence-review-{uuid4()}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _author_evidence(
    client: TestClient,
    evidence: EvidenceSeed,
    *,
    request_id: str = "human-evidence-revision-1",
    observation: str = "A human reviewer authored this exact-source observation.",
) -> dict[str, object]:
    response = client.post(
        f"/v1/evidence/{evidence.evidence_id}/revisions",
        json={
            "base_revision_id": str(evidence.evidence_revision_id),
            "observation": observation,
            "interpretation": "The source may indicate a product workflow problem.",
            "inference": "A bounded experiment should test the proposed change.",
            "confidence": 0.88,
            "tags": ["human-curated", "workflow"],
            "editor": "curator@example.test",
            "rationale": "Replace the demo-only observation with reviewed human authorship.",
            "client_request_id": request_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _edge(
    evidence: EvidenceSeed,
    *,
    relation: str,
    confirmed: bool,
) -> dict[str, object]:
    return {
        "evidence_id": str(evidence.evidence_id),
        "evidence_revision_id": str(evidence.evidence_revision_id),
        "relation": relation,
        "relation_confirmed": confirmed,
        "rationale": f"Human explanation for {relation}",
        "relevance": 0.9,
    }


def _claim_payload(
    edges: list[dict[str, object]],
    *,
    request_id: str | None = None,
    statement: str = "Teams need a faster evidence review workflow.",
    counterevidence_status: str = "SEARCHED_NONE_FOUND",
) -> dict[str, object]:
    return {
        "statement": statement,
        "topic_key": "workflow-speed",
        "summary": "A traceable workflow opportunity.",
        "rationale": "The statement separates source facts from product interpretation.",
        "confidence": 0.82,
        "counterevidence_status": counterevidence_status,
        "counterevidence_summary": "A skeptic search found no direct contradiction.",
        "provenance": {"authoring_mode": "human"},
        "evidence_edges": edges,
        "client_request_id": request_id or f"claim-{uuid4()}",
    }


def test_evidence_reviews_are_append_only_idempotent_and_drive_existing_reads(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study = _study(client)
    evidence = _evidence(
        session_factory,
        str(study["id"]),
        quote="Customers manually reconcile evidence every Friday.",
    )
    request_id = "review-idempotency-1"
    accepted = _review_evidence(client, evidence, request_id=request_id)
    repeated = _review_evidence(client, evidence, request_id=request_id)
    assert repeated["id"] == accepted["id"]

    conflict = client.post(
        f"/v1/evidence/{evidence.evidence_id}/reviews",
        json={
            "evidence_revision_id": str(evidence.evidence_revision_id),
            "decision": "REJECT",
            "reviewer": "human@example.test",
            "rationale": "Changed payload",
            "client_request_id": request_id,
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"]["reason"] == "idempotency_key_reuse"

    evidence_list = client.get(f"/v1/studies/{study['id']}/evidence")
    assert evidence_list.status_code == 200
    assert evidence_list.json()["items"][0]["review_status"] == "reviewed"
    context = client.get(
        f"/v1/evidence/{evidence.evidence_id}/context",
        params={"evidence_revision_id": str(evidence.evidence_revision_id)},
    )
    assert context.status_code == 200
    assert context.json()["evidence"]["review_status"] == "reviewed"
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(EvidenceReview)) == 1


def test_synthetic_or_unverified_evidence_cannot_be_accepted(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study = _study(client)
    synthetic = _evidence(
        session_factory,
        str(study["id"]),
        quote="Synthetic demo evidence.",
        synthetic=True,
    )
    response = client.post(
        f"/v1/evidence/{synthetic.evidence_id}/reviews",
        json={
            "evidence_revision_id": str(synthetic.evidence_revision_id),
            "decision": "ACCEPT",
            "reviewer": "human@example.test",
            "rationale": "Do not allow this.",
            "client_request_id": "synthetic-accept",
        },
    )
    assert response.status_code == 422
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(EvidenceReview)) == 0


def test_human_revision_preserves_source_lineage_and_can_promote_demo_evidence(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study = _study(client)
    synthetic = _evidence(
        session_factory,
        str(study["id"]),
        quote="An exact source quote that needs a human-authored observation.",
        synthetic=True,
    )
    authored = _author_evidence(client, synthetic)
    repeated = _author_evidence(client, synthetic)
    assert repeated["evidence_revision_id"] == authored["evidence_revision_id"]
    assert authored["parent_revision_id"] == str(synthetic.evidence_revision_id)
    assert authored["source_revision_id"] == str(synthetic.source_revision_id)
    assert authored["revision"] == 2
    assert authored["review_status"] == "PROPOSED"
    provenance = authored["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["human_authored"] is True
    assert provenance["synthetic_demo"] is False
    assert provenance["derived_from_synthetic_demo"] is True

    context = client.get(
        f"/v1/evidence/{synthetic.evidence_id}/context",
        params={"evidence_revision_id": authored["evidence_revision_id"]},
    )
    assert context.status_code == 200, context.text
    replay = context.json()
    assert replay["highlight"] == "An exact source quote that needs a human-authored observation."
    assert replay["source"]["source_revision_id"] == str(synthetic.source_revision_id)
    assert all(replay["integrity"].values())
    assert replay["evidence"]["provenance"]["human_authored"] is True
    assert replay["evidence"]["review_status"] == "pending"

    reviewed = _review_evidence(
        client,
        EvidenceSeed(
            evidence_id=synthetic.evidence_id,
            evidence_revision_id=UUID(str(authored["evidence_revision_id"])),
            source_id=synthetic.source_id,
            source_revision_id=synthetic.source_revision_id,
        ),
    )
    assert reviewed["decision"] == "ACCEPT"
    latest = client.get(f"/v1/studies/{study['id']}/evidence").json()["items"][0]
    assert latest["evidence_revision_id"] == authored["evidence_revision_id"]
    assert latest["review_status"] == "reviewed"
    assert latest["provenance"]["human_authored"] is True

    changed = client.post(
        f"/v1/evidence/{synthetic.evidence_id}/revisions",
        json={
            "base_revision_id": str(synthetic.evidence_revision_id),
            "observation": "Changed content with a reused key.",
            "interpretation": None,
            "inference": None,
            "confidence": 1,
            "tags": [],
            "editor": "curator@example.test",
            "rationale": "This must conflict.",
            "client_request_id": "human-evidence-revision-1",
        },
    )
    assert changed.status_code == 409


def test_human_evidence_successor_stales_a_reviewed_dependent_claim(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study = _study(client)
    original = _evidence(
        session_factory,
        str(study["id"]),
        quote="A source quote that receives two human interpretations.",
        synthetic=True,
    )
    first_revision = _author_evidence(
        client,
        original,
        request_id="human-successor-base",
    )
    reviewed_evidence = EvidenceSeed(
        evidence_id=original.evidence_id,
        evidence_revision_id=UUID(str(first_revision["evidence_revision_id"])),
        source_id=original.source_id,
        source_revision_id=original.source_revision_id,
    )
    _review_evidence(client, reviewed_evidence)
    claim_response = client.post(
        f"/v1/studies/{study['id']}/claims",
        json=_claim_payload([_edge(reviewed_evidence, relation="supports", confirmed=True)]),
    )
    assert claim_response.status_code == 201, claim_response.text
    claim = claim_response.json()
    accepted = client.post(
        f"/v1/claim-revisions/{claim['claim_revision_id']}/reviews",
        json={
            "decision": "ACCEPT",
            "reviewer": "lead@example.test",
            "rationale": "Accept the exact human-authored Evidence Revision.",
            "client_request_id": "accept-claim-before-evidence-successor",
        },
    )
    assert accepted.status_code == 201, accepted.text
    pending_claim_response = client.post(
        f"/v1/studies/{study['id']}/claims",
        json=_claim_payload(
            [_edge(reviewed_evidence, relation="supports", confirmed=True)],
            request_id="pending-claim-before-evidence-successor",
        ),
    )
    assert pending_claim_response.status_code == 201, pending_claim_response.text
    pending_claim = pending_claim_response.json()

    successor = _author_evidence(
        client,
        reviewed_evidence,
        request_id="human-successor-revision-two",
        observation="A second human reading narrows the supported cohort.",
    )
    assert successor["revision"] == 3

    replay = client.get(f"/v1/claims/{claim['claim_id']}")
    assert replay.status_code == 200
    assert replay.json()["status"] == "STALE"
    assert "CLAIM_STALE" in replay.json()["publication_blockers"]

    accept_old_revision = client.post(
        f"/v1/claim-revisions/{pending_claim['claim_revision_id']}/reviews",
        json={
            "decision": "ACCEPT",
            "reviewer": "lead@example.test",
            "rationale": "This now references an old Evidence Revision.",
            "client_request_id": "accept-after-evidence-successor",
        },
    )
    assert accept_old_revision.status_code == 422
    new_claim_on_old_revision = client.post(
        f"/v1/studies/{study['id']}/claims",
        json=_claim_payload(
            [_edge(reviewed_evidence, relation="supports", confirmed=True)],
            request_id="new-claim-on-old-evidence-revision",
        ),
    )
    assert new_claim_on_old_revision.status_code == 422


def test_simulation_output_cannot_be_converted_to_human_evidence(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study = _study(client)
    simulation = _evidence(
        session_factory,
        str(study["id"]),
        quote="A simulated persona statement.",
        synthetic=True,
        simulation=True,
    )
    response = client.post(
        f"/v1/evidence/{simulation.evidence_id}/revisions",
        json={
            "base_revision_id": str(simulation.evidence_revision_id),
            "observation": "Attempted laundering.",
            "confidence": 1,
            "tags": [],
            "editor": "curator@example.test",
            "rationale": "This must be rejected.",
            "client_request_id": "simulation-laundering",
        },
    )
    assert response.status_code == 422


def test_pending_evidence_is_context_only_and_formal_edges_require_confirmation(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study = _study(client)
    evidence = _evidence(
        session_factory,
        str(study["id"]),
        quote="A participant described a slow handoff.",
    )

    contextual = client.post(
        f"/v1/studies/{study['id']}/claims",
        json=_claim_payload([_edge(evidence, relation="contextualizes", confirmed=False)]),
    )
    assert contextual.status_code == 201, contextual.text
    assert contextual.json()["evidence_edges"][0]["relation_confirmed"] is False
    assert "NO_CONFIRMED_SUPPORT" in contextual.json()["publication_blockers"]

    unconfirmed_support = client.post(
        f"/v1/studies/{study['id']}/claims",
        json=_claim_payload([_edge(evidence, relation="supports", confirmed=False)]),
    )
    assert unconfirmed_support.status_code == 422
    pending_support = client.post(
        f"/v1/studies/{study['id']}/claims",
        json=_claim_payload([_edge(evidence, relation="supports", confirmed=True)]),
    )
    assert pending_support.status_code == 422

    review_context_only = client.post(
        f"/v1/claim-revisions/{contextual.json()['claim_revision_id']}/reviews",
        json={
            "decision": "ACCEPT",
            "reviewer": "human@example.test",
            "rationale": "There is no support edge.",
            "client_request_id": "context-only-claim-review",
        },
    )
    assert review_context_only.status_code == 422


def test_claim_accept_requires_every_formal_edge_to_remain_accepted(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study = _study(client)
    support = _evidence(session_factory, str(study["id"]), quote="Support quote.")
    contradiction = _evidence(session_factory, str(study["id"]), quote="Contradiction quote.")
    _review_evidence(client, support)
    _review_evidence(client, contradiction)
    claim = client.post(
        f"/v1/studies/{study['id']}/claims",
        json=_claim_payload(
            [
                _edge(support, relation="supports", confirmed=True),
                _edge(contradiction, relation="contradicts", confirmed=True),
            ]
        ),
    )
    assert claim.status_code == 201, claim.text
    _review_evidence(client, contradiction, decision="REQUEST_CHANGES")

    response = client.post(
        f"/v1/claim-revisions/{claim.json()['claim_revision_id']}/reviews",
        json={
            "decision": "ACCEPT",
            "reviewer": "human@example.test",
            "rationale": "Should fail because one formal edge lost acceptance.",
            "client_request_id": "all-formal-edges-gate",
        },
    )
    assert response.status_code == 422
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ClaimReview)) == 0


def test_reviewed_claim_becomes_stale_when_support_review_is_downgraded(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study = _study(client)
    evidence = _evidence(
        session_factory,
        str(study["id"]),
        quote="Eight participants repeated the same manual workaround.",
    )
    evidence_review = _review_evidence(client, evidence)
    claim_response = client.post(
        f"/v1/studies/{study['id']}/claims",
        json=_claim_payload([_edge(evidence, relation="supports", confirmed=True)]),
    )
    assert claim_response.status_code == 201, claim_response.text
    claim = claim_response.json()
    accepted = client.post(
        f"/v1/claim-revisions/{claim['claim_revision_id']}/reviews",
        json={
            "decision": "ACCEPT",
            "reviewer": "lead@example.test",
            "rationale": "The exact support is human-confirmed.",
            "client_request_id": "claim-accept-1",
        },
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["evidence_review_snapshot"] == {
        claim["evidence_edges"][0]["id"]: evidence_review["id"]
    }
    assert client.get(f"/v1/claims/{claim['claim_id']}").json()["status"] == "REVIEWED"

    _review_evidence(client, evidence, decision="REQUEST_CHANGES")
    stale = client.get(f"/v1/claims/{claim['claim_id']}")
    assert stale.status_code == 200
    stale_claim = stale.json()
    assert stale_claim["status"] == "STALE"
    assert stale_claim["revision_status"] == "REVIEWED"
    assert "CLAIM_STALE" in stale_claim["publication_blockers"]
    assert "EVIDENCE_REVIEW_NOT_ACCEPTED" in stale_claim["publication_blockers"]
    assert stale_claim["evidence_edges"][0]["latest_evidence_review"]["decision"] == (
        "REQUEST_CHANGES"
    )
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ClaimReview)) == 1
        assert session.scalar(select(func.count()).select_from(ClaimRevision)) == 1


def test_revision_base_idempotency_and_historical_replay_do_not_drift(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study = _study(client)
    evidence = _evidence(session_factory, str(study["id"]), quote="Pinned evidence quote.")
    _review_evidence(client, evidence)
    first_response = client.post(
        f"/v1/studies/{study['id']}/claims",
        json=_claim_payload([_edge(evidence, relation="supports", confirmed=True)]),
    )
    assert first_response.status_code == 201, first_response.text
    first = first_response.json()
    accepted = client.post(
        f"/v1/claim-revisions/{first['claim_revision_id']}/reviews",
        json={
            "decision": "ACCEPT",
            "reviewer": "lead@example.test",
            "rationale": "Accept revision one.",
            "client_request_id": "claim-one-review",
        },
    )
    assert accepted.status_code == 201

    revision_payload = _claim_payload(
        [_edge(evidence, relation="supports", confirmed=True)],
        request_id="claim-revision-idempotency",
        statement="Revision two adds a narrower cohort.",
    )
    revision_payload["base_revision_id"] = first["claim_revision_id"]
    second_response = client.post(
        f"/v1/claims/{first['claim_id']}/revisions",
        json=revision_payload,
    )
    assert second_response.status_code == 201, second_response.text
    second = second_response.json()
    repeated = client.post(
        f"/v1/claims/{first['claim_id']}/revisions",
        json=revision_payload,
    )
    assert repeated.status_code == 201
    assert repeated.json()["claim_revision_id"] == second["claim_revision_id"]

    changed_payload = {**revision_payload, "statement": "Key reuse with changed content."}
    conflict = client.post(
        f"/v1/claims/{first['claim_id']}/revisions",
        json=changed_payload,
    )
    assert conflict.status_code == 409
    stale_base = {
        **revision_payload,
        "client_request_id": "stale-base-request",
        "statement": "Attempt to overwrite from revision one.",
    }
    stale_base_response = client.post(
        f"/v1/claims/{first['claim_id']}/revisions",
        json=stale_base,
    )
    assert stale_base_response.status_code == 409

    historical = client.get(
        f"/v1/claims/{first['claim_id']}",
        params={"claim_revision_id": first["claim_revision_id"]},
    )
    assert historical.status_code == 200
    old = historical.json()
    assert old["statement"] == first["statement"]
    assert old["revision"] == 1
    assert old["is_current"] is False
    assert old["revision_status"] == "REVIEWED"
    assert old["status"] == "PROPOSED"
    assert "NOT_CURRENT_REVISION" in old["publication_blockers"]
    assert old["evidence_edges"][0]["evidence_revision_id"] == str(evidence.evidence_revision_id)
    assert (
        f"evidence_revision_id={evidence.evidence_revision_id}"
        in old["evidence_edges"][0]["context_url"]
    )
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ClaimRevision)) == 2


def test_cross_study_evidence_rejects_entire_claim_transaction(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    first_study = _study(client, "First")
    second_study = _study(client, "Second")
    foreign_evidence = _evidence(
        session_factory,
        str(second_study["id"]),
        quote="Evidence from the wrong Study.",
    )
    response = client.post(
        f"/v1/studies/{first_study['id']}/claims",
        json=_claim_payload([_edge(foreign_evidence, relation="contextualizes", confirmed=False)]),
    )
    assert response.status_code == 422
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Claim)) == 0


def test_same_process_rapid_reviews_have_deterministic_latest_state(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study = _study(client)
    evidence = _evidence(session_factory, str(study["id"]), quote="Rapid review quote.")
    _review_evidence(client, evidence, decision="ACCEPT")
    latest = _review_evidence(client, evidence, decision="REQUEST_CHANGES")
    listed = client.get(f"/v1/studies/{study['id']}/evidence").json()["items"][0]
    assert listed["review_status"] == "pending"

    claim = client.post(
        f"/v1/studies/{study['id']}/claims",
        json=_claim_payload([_edge(evidence, relation="contextualizes", confirmed=False)]),
    )
    assert claim.status_code == 201
    assert claim.json()["evidence_edges"][0]["latest_evidence_review"]["id"] == latest["id"]
