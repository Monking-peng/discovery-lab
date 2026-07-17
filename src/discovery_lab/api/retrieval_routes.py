from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from discovery_lab.api.dependencies import get_session
from discovery_lab.domain.retrieval_schemas import ContextManifestRead, RetrievalCreate
from discovery_lab.services.retrieval import RetrievalService, context_manifest_response

router = APIRouter(tags=["retrieval"])
SessionDependency = Annotated[Session, Depends(get_session)]


@router.post(
    "/studies/{study_id}/retrievals",
    response_model=ContextManifestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_retrieval(
    study_id: UUID,
    payload: RetrievalCreate,
    session: SessionDependency,
) -> ContextManifestRead:
    return context_manifest_response(
        RetrievalService(session).create_context_manifest(study_id, payload)
    )


@router.get("/context-manifests/{manifest_id}", response_model=ContextManifestRead)
@router.get(
    "/retrievals/{manifest_id}",
    response_model=ContextManifestRead,
    include_in_schema=False,
)
def get_context_manifest(
    manifest_id: UUID,
    session: SessionDependency,
) -> ContextManifestRead:
    return context_manifest_response(RetrievalService(session).get_context_manifest(manifest_id))
