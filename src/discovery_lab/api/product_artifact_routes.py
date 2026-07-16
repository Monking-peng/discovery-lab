from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from discovery_lab.api.dependencies import get_session
from discovery_lab.domain.product_artifact_schemas import (
    PrdArtifactCreate,
    PrdArtifactRead,
    ProductArtifactBundleRead,
    ProductDecisionCreate,
    ProductDecisionRead,
)
from discovery_lab.services.product_artifacts import (
    ProductArtifactService,
    decision_response,
    prd_response,
)

router = APIRouter(tags=["product-artifacts"])
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get(
    "/studies/{study_id}/product-artifacts",
    response_model=ProductArtifactBundleRead,
)
def list_product_artifacts(
    study_id: UUID,
    session: SessionDependency,
) -> ProductArtifactBundleRead:
    return ProductArtifactService(session).list_product_artifacts(study_id)


@router.post(
    "/experiments/{experiment_id}/decisions",
    response_model=ProductDecisionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_product_decision(
    experiment_id: UUID,
    payload: ProductDecisionCreate,
    session: SessionDependency,
) -> ProductDecisionRead:
    return decision_response(
        ProductArtifactService(session).create_decision(experiment_id, payload)
    )


@router.post(
    "/decisions/{decision_id}/prds",
    response_model=PrdArtifactRead,
    status_code=status.HTTP_201_CREATED,
)
def create_prd(
    decision_id: UUID,
    payload: PrdArtifactCreate,
    session: SessionDependency,
) -> PrdArtifactRead:
    return prd_response(ProductArtifactService(session).create_prd(decision_id, payload))


@router.get("/prds/{prd_id}", response_model=PrdArtifactRead)
def get_prd(prd_id: UUID, session: SessionDependency) -> PrdArtifactRead:
    return prd_response(ProductArtifactService(session).get_prd(prd_id))
