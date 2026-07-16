from typing import Annotated

from fastapi import APIRouter, Depends

from discovery_lab.api.errors import AppError
from discovery_lab.services.evaluation_reporting import (
    BadCaseInbox,
    CurrentEvaluationReport,
    EvaluationDataError,
    EvaluationReportingService,
    get_evaluation_reporting_service,
)

router = APIRouter(tags=["evaluation"])
EvaluationServiceDependency = Annotated[
    EvaluationReportingService,
    Depends(get_evaluation_reporting_service),
]


def _invalid_evaluation_data(exc: EvaluationDataError) -> AppError:
    return AppError(
        code="evaluation_data_invalid",
        message="Evaluation data failed strict validation",
        status_code=500,
        details={"resource": exc.resource, "file": exc.filename},
    )


@router.get("/evaluation/reports/current", response_model=CurrentEvaluationReport)
def current_evaluation_report(
    service: EvaluationServiceDependency,
) -> CurrentEvaluationReport:
    try:
        return service.current_report()
    except EvaluationDataError as exc:
        raise _invalid_evaluation_data(exc) from exc


@router.get("/evaluation/bad-cases", response_model=BadCaseInbox)
def bad_case_inbox(service: EvaluationServiceDependency) -> BadCaseInbox:
    try:
        return service.bad_case_inbox()
    except EvaluationDataError as exc:
        raise _invalid_evaluation_data(exc) from exc
