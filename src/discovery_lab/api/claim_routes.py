from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from discovery_lab.api.dependencies import get_session
from discovery_lab.db.models import ClaimReview, EvidenceReview, EvidenceRevision
from discovery_lab.domain.claim_schemas import (
    ClaimCreate,
    ClaimEvidenceEdgeRead,
    ClaimList,
    ClaimRead,
    ClaimReviewCreate,
    ClaimReviewRead,
    ClaimRevisionCreate,
    EvidenceReviewCreate,
    EvidenceReviewRead,
    EvidenceRevisionAuthorCreate,
    EvidenceRevisionAuthoredRead,
)
from discovery_lab.domain.enums import (
    ClaimEvidenceRelation,
    ClaimStatus,
    CounterevidenceStatus,
    ReviewDecision,
)
from discovery_lab.services.claims import ClaimEdgeRecord, ClaimRecord, ClaimService

router = APIRouter(tags=["claims"])
SessionDependency = Annotated[Session, Depends(get_session)]


def _evidence_review_response(review: EvidenceReview) -> EvidenceReviewRead:
    return EvidenceReviewRead(
        id=review.id,
        evidence_id=review.evidence_unit_id,
        evidence_revision_id=review.evidence_revision_id,
        decision=ReviewDecision(review.decision),
        reviewer=review.reviewer,
        rationale=review.rationale,
        client_request_id=review.client_request_id,
        created_at=review.created_at,
    )


def _claim_review_response(review: ClaimReview, claim_id: UUID) -> ClaimReviewRead:
    return ClaimReviewRead(
        id=review.id,
        claim_id=claim_id,
        claim_revision_id=review.claim_revision_id,
        decision=ReviewDecision(review.decision),
        reviewer=review.reviewer,
        rationale=review.rationale,
        evidence_review_snapshot=review.evidence_review_snapshot,
        client_request_id=review.client_request_id,
        created_at=review.created_at,
    )


def _authored_evidence_response(
    revision: EvidenceRevision,
) -> EvidenceRevisionAuthoredRead:
    if revision.parent_revision_id is None or revision.client_request_id is None:
        raise RuntimeError("Human-authored Evidence Revision is missing lineage metadata")
    return EvidenceRevisionAuthoredRead(
        evidence_id=revision.evidence_unit_id,
        evidence_revision_id=revision.id,
        parent_revision_id=revision.parent_revision_id,
        revision=revision.revision,
        source_revision_id=revision.source_revision_id,
        segment_id=revision.segment_id,
        review_status=revision.review_status,
        content_hash=revision.content_hash,
        provenance=revision.provenance,
        client_request_id=revision.client_request_id,
        created_at=revision.created_at,
    )


def _edge_response(record: ClaimEdgeRecord) -> ClaimEvidenceEdgeRead:
    edge = record.edge
    revision = record.evidence_revision
    source_revision = record.source_revision
    review = record.latest_evidence_review
    return ClaimEvidenceEdgeRead(
        id=edge.id,
        evidence_id=edge.evidence_unit_id,
        evidence_revision_id=edge.evidence_revision_id,
        source_id=source_revision.source_id,
        source_revision_id=source_revision.id,
        relation=ClaimEvidenceRelation(edge.relation),
        relation_confirmed=edge.relation_confirmed,
        rationale=edge.rationale,
        relevance=edge.relevance,
        context_url=(
            f"/v1/evidence/{edge.evidence_unit_id}/context?evidence_revision_id={revision.id}"
        ),
        latest_evidence_review=(_evidence_review_response(review) if review is not None else None),
    )


def _claim_response(record: ClaimRecord) -> ClaimRead:
    claim = record.claim
    revision = record.revision
    return ClaimRead(
        id=claim.id,
        claim_id=claim.id,
        study_id=claim.study_id,
        status=ClaimStatus(claim.status),
        revision_status=record.revision_status,
        is_current=record.is_current,
        revision_id=revision.id,
        claim_revision_id=revision.id,
        revision=revision.revision,
        base_revision_id=revision.base_revision_id,
        statement=revision.statement,
        topic_key=revision.topic_key,
        summary=revision.summary,
        rationale=revision.rationale,
        confidence=revision.confidence,
        counterevidence_status=CounterevidenceStatus(revision.counterevidence_status),
        counterevidence_summary=revision.counterevidence_summary,
        provenance=revision.provenance,
        content_hash=revision.content_hash,
        created_at=revision.created_at,
        evidence_edges=[_edge_response(edge) for edge in record.edges],
        latest_review=(
            _claim_review_response(record.latest_review, claim.id)
            if record.latest_review is not None
            else None
        ),
        publication_blockers=list(record.publication_blockers),
    )


@router.post(
    "/evidence/{evidence_id}/reviews",
    response_model=EvidenceReviewRead,
    status_code=status.HTTP_201_CREATED,
)
def review_evidence(
    evidence_id: UUID,
    payload: EvidenceReviewCreate,
    session: SessionDependency,
) -> EvidenceReviewRead:
    review = ClaimService(session).review_evidence(evidence_id, payload)
    return _evidence_review_response(review)


@router.post(
    "/evidence/{evidence_id}/revisions",
    response_model=EvidenceRevisionAuthoredRead,
    status_code=status.HTTP_201_CREATED,
)
def author_evidence_revision(
    evidence_id: UUID,
    payload: EvidenceRevisionAuthorCreate,
    session: SessionDependency,
) -> EvidenceRevisionAuthoredRead:
    revision = ClaimService(session).author_evidence_revision(evidence_id, payload)
    return _authored_evidence_response(revision)


@router.post(
    "/studies/{study_id}/claims",
    response_model=ClaimRead,
    status_code=status.HTTP_201_CREATED,
)
def create_claim(
    study_id: UUID,
    payload: ClaimCreate,
    session: SessionDependency,
) -> ClaimRead:
    return _claim_response(ClaimService(session).create_claim(study_id, payload))


@router.get("/studies/{study_id}/claims", response_model=ClaimList)
def list_claims(
    study_id: UUID,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClaimList:
    records, total = ClaimService(session).list_claims(
        study_id,
        limit=limit,
        offset=offset,
    )
    return ClaimList(
        items=[_claim_response(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/claims/{claim_id}", response_model=ClaimRead)
def get_claim(
    claim_id: UUID,
    session: SessionDependency,
    claim_revision_id: Annotated[
        UUID | None,
        Query(description="Replay this exact immutable Claim Revision"),
    ] = None,
) -> ClaimRead:
    return _claim_response(
        ClaimService(session).get_claim(
            claim_id,
            claim_revision_id=claim_revision_id,
        )
    )


@router.post(
    "/claims/{claim_id}/revisions",
    response_model=ClaimRead,
    status_code=status.HTTP_201_CREATED,
)
def create_claim_revision(
    claim_id: UUID,
    payload: ClaimRevisionCreate,
    session: SessionDependency,
) -> ClaimRead:
    return _claim_response(ClaimService(session).create_claim_revision(claim_id, payload))


@router.post(
    "/claim-revisions/{claim_revision_id}/reviews",
    response_model=ClaimReviewRead,
    status_code=status.HTTP_201_CREATED,
)
def review_claim(
    claim_revision_id: UUID,
    payload: ClaimReviewCreate,
    session: SessionDependency,
) -> ClaimReviewRead:
    review, claim = ClaimService(session).review_claim(claim_revision_id, payload)
    return _claim_review_response(review, claim.id)
