from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from discovery_lab.api.dependencies import get_session
from discovery_lab.domain.enums import OpportunityStatus
from discovery_lab.domain.opportunity_schemas import (
    OpportunityDraftCreate,
    OpportunityDraftList,
    OpportunityDraftRead,
)
from discovery_lab.services.opportunities import OpportunityDraftRecord, OpportunityService

router = APIRouter(tags=["opportunities"])
SessionDependency = Annotated[Session, Depends(get_session)]


def _draft_response(record: OpportunityDraftRecord) -> OpportunityDraftRead:
    draft = record.draft
    claim_revision = record.claim_record.revision
    return OpportunityDraftRead(
        id=draft.id,
        study_id=draft.study_id,
        claim_id=draft.claim_id,
        claim_revision_id=draft.claim_revision_id,
        status=OpportunityStatus(draft.status),
        title=draft.title,
        problem_statement=draft.problem_statement,
        desired_outcome=draft.desired_outcome,
        next_step=draft.next_step,
        rationale=draft.rationale,
        confidence=draft.confidence,
        assumptions=list(draft.assumptions),
        risks=list(draft.risks),
        provenance=draft.provenance,
        content_hash=draft.content_hash,
        client_request_id=draft.client_request_id,
        created_at=draft.created_at,
        claim_statement=claim_revision.statement,
        claim_context_url=(
            f"/v1/claims/{draft.claim_id}?claim_revision_id={draft.claim_revision_id}"
        ),
        publishable=False,
        publication_blockers=list(record.publication_blockers),
    )


@router.post(
    "/studies/{study_id}/opportunities",
    response_model=OpportunityDraftRead,
    status_code=status.HTTP_201_CREATED,
)
def create_opportunity_draft(
    study_id: UUID,
    payload: OpportunityDraftCreate,
    session: SessionDependency,
) -> OpportunityDraftRead:
    return _draft_response(OpportunityService(session).create_draft(study_id, payload))


@router.get("/studies/{study_id}/opportunities", response_model=OpportunityDraftList)
def list_opportunity_drafts(
    study_id: UUID,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OpportunityDraftList:
    records, total = OpportunityService(session).list_drafts(
        study_id,
        limit=limit,
        offset=offset,
    )
    return OpportunityDraftList(
        items=[_draft_response(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityDraftRead)
def get_opportunity_draft(
    opportunity_id: UUID,
    session: SessionDependency,
) -> OpportunityDraftRead:
    return _draft_response(OpportunityService(session).get_draft(opportunity_id))
