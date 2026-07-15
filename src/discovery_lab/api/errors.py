from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: object) -> None:
        super().__init__(
            code="not_found",
            message=f"{resource} was not found",
            status_code=404,
            details={"resource": resource, "id": str(resource_id)},
        )


class ConflictError(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(code="conflict", message=message, status_code=409, details=details)


class UnsupportedSourceError(AppError):
    def __init__(self, mime_type: str) -> None:
        super().__init__(
            code="unsupported_source",
            message="This source type is not supported by the active processor",
            status_code=422,
            details={"mime_type": mime_type},
        )


class InvalidSourceError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(code="invalid_source", message=message, status_code=422)


class ProcessingError(AppError):
    def __init__(self, run_id: object) -> None:
        super().__init__(
            code="source_processing_failed",
            message="Source processing failed; inspect the run record for a safe error summary",
            status_code=500,
            details={"run_id": str(run_id)},
        )
