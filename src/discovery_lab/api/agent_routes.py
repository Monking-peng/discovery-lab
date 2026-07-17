from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from discovery_lab.api.dependencies import get_session
from discovery_lab.domain.agent_schemas import (
    AgentRunCreate,
    AgentRunList,
    AgentRunRead,
    ToolApprovalCreate,
    ToolRegistryRead,
)
from discovery_lab.services.agent_runs import (
    AgentRunService,
    agent_run_list_response,
    agent_run_response,
    tool_registry_response,
)

router = APIRouter(tags=["agent-harness"])
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("/tools", response_model=ToolRegistryRead)
def list_tools() -> ToolRegistryRead:
    return tool_registry_response()


@router.post(
    "/studies/{study_id}/agent-runs",
    response_model=AgentRunRead,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_run(
    study_id: UUID,
    payload: AgentRunCreate,
    session: SessionDependency,
) -> AgentRunRead:
    return agent_run_response(AgentRunService(session).create_run(study_id, payload))


@router.get("/studies/{study_id}/agent-runs", response_model=AgentRunList)
def list_agent_runs(
    study_id: UUID,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AgentRunList:
    records, total = AgentRunService(session).list_runs(
        study_id,
        limit=limit,
        offset=offset,
    )
    return agent_run_list_response(records, total)


@router.get("/agent-runs/{run_id}", response_model=AgentRunRead)
def get_agent_run(run_id: UUID, session: SessionDependency) -> AgentRunRead:
    return agent_run_response(AgentRunService(session).get_run(run_id))


@router.post(
    "/tool-calls/{tool_call_id}/approvals",
    response_model=AgentRunRead,
    status_code=status.HTTP_201_CREATED,
)
def approve_tool_call(
    tool_call_id: UUID,
    payload: ToolApprovalCreate,
    session: SessionDependency,
) -> AgentRunRead:
    return agent_run_response(AgentRunService(session).approve_tool_call(tool_call_id, payload))
