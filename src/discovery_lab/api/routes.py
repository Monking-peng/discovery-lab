from __future__ import annotations

import mimetypes
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from discovery_lab.api.dependencies import (
    get_app_settings,
    get_blob_store,
    get_ingestion_runner,
    get_session,
)
from discovery_lab.api.errors import AppError
from discovery_lab.config import Settings
from discovery_lab.domain.schemas import (
    ContextSegment,
    EvidenceContext,
    EvidenceList,
    EvidenceRead,
    EvidenceSourceContext,
    IntegrityCheck,
    RunList,
    RunRead,
    SourceList,
    SourceRead,
    SourceRevisionRead,
    StudyCreate,
    StudyList,
    StudyRead,
)
from discovery_lab.ingestion.models import CsvLocator, Locator, PdfLocator, TextLocator
from discovery_lab.services.discovery import (
    DiscoveryService,
    EvidenceContextRecord,
    EvidenceRecord,
    SourceRecord,
    StudyRecord,
)
from discovery_lab.services.evidence_integrity import evidence_content_hash
from discovery_lab.services.hashing import sha256_text
from discovery_lab.services.ingestion_runner import IngestionRunner
from discovery_lab.services.storage import BlobStore

router = APIRouter()
LOCATOR_ADAPTER: TypeAdapter[Locator] = TypeAdapter(Locator)

SessionDependency = Annotated[Session, Depends(get_session)]
BlobStoreDependency = Annotated[BlobStore, Depends(get_blob_store)]
IngestionRunnerDependency = Annotated[IngestionRunner, Depends(get_ingestion_runner)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]


def _service(
    session: Session,
    blob_store: BlobStore,
    ingestion_runner: IngestionRunner,
) -> DiscoveryService:
    return DiscoveryService(
        session,
        blob_store=blob_store,
        ingestion_runner=ingestion_runner,
    )


def _study_response(record: StudyRecord) -> StudyRead:
    study = record.study
    question = study.research_question or ""
    api_status = "archived" if study.status == "ARCHIVED" else "draft"
    return StudyRead(
        id=study.id,
        title=study.title,
        description=study.description,
        research_question=study.research_question,
        decision_question=question,
        status=api_status,
        created_at=study.created_at,
        updated_at=study.created_at,
        source_count=record.source_count,
        evidence_count=record.evidence_count,
    )


def _run_progress(record: SourceRecord) -> int:
    run = record.latest_run
    if run is None or not run.steps:
        return 0
    if run.status == "SUCCEEDED":
        return 100
    succeeded = sum(step.status == "SUCCEEDED" for step in run.steps)
    return min(99, int((succeeded / len(run.steps)) * 100))


def _source_response(record: SourceRecord) -> SourceRead:
    source = record.source
    status, progress = {
        "UPLOADED": ("queued", 0),
        "PROCESSING": ("processing", _run_progress(record)),
        "PROCESSED": ("ready", 100),
        "FAILED": ("failed", _run_progress(record)),
    }.get(source.status, ("failed", _run_progress(record)))
    latest_activity = (
        record.latest_run.completed_at
        or record.latest_run.started_at
        or record.latest_run.created_at
        if record.latest_run is not None
        else record.revision.created_at
    )
    return SourceRead(
        id=source.id,
        source_id=source.id,
        study_id=source.study_id,
        name=source.display_name,
        display_name=source.display_name,
        type=source.source_type,
        source_type=source.source_type,
        status=status,
        domain_status=source.status,
        progress=progress,
        created_at=source.created_at,
        updated_at=latest_activity,
        revision=SourceRevisionRead.model_validate(record.revision),
    )


def _locator_label(locator: dict[str, object]) -> str:
    kind = locator.get("kind")
    if kind == "text":
        start = locator.get("char_start")
        end = locator.get("char_end")
        if isinstance(start, int) and isinstance(end, int):
            return f"字符 {start}-{end}"
    elif kind == "csv":
        row_number = locator.get("row_number")
        stable_row_id = locator.get("stable_row_id")
        if isinstance(row_number, int):
            suffix = f" · {stable_row_id}" if isinstance(stable_row_id, str) else ""
            return f"第 {row_number} 行{suffix}"
    elif kind == "pdf":
        page_number = locator.get("page_number")
        start = locator.get("page_char_start")
        end = locator.get("page_char_end")
        if isinstance(page_number, int):
            span = (
                f" · 字符 {start}-{end}" if isinstance(start, int) and isinstance(end, int) else ""
            )
            return f"第 {page_number} 页{span}"
    return "原文定位可用"


def _evidence_response(record: EvidenceRecord) -> EvidenceRead:
    revision = record.revision
    title_source = revision.observation or revision.quote
    title = title_source.strip().splitlines()[0][:120] or "原文摘录"
    review_status = {
        "PROPOSED": "pending",
        "REVIEWED": "reviewed",
        "REJECTED": "rejected",
    }.get(revision.review_status, "pending")
    confidence_value = revision.provenance.get("confidence")
    confidence = (
        float(confidence_value)
        if isinstance(confidence_value, (int, float)) and not isinstance(confidence_value, bool)
        else 0.0
    )
    tags_value = revision.provenance.get("tags")
    tags = (
        [tag for tag in tags_value if isinstance(tag, str)]
        if isinstance(tags_value, list)
        else ["unreviewed", "source-excerpt"]
    )
    return EvidenceRead(
        id=record.evidence_unit.id,
        evidence_id=record.evidence_unit.id,
        evidence_revision_id=revision.id,
        revision=revision.revision,
        study_id=record.evidence_unit.study_id,
        source_id=record.source.id,
        source_name=record.source.display_name,
        source_type=record.source.source_type,
        source_revision_id=revision.source_revision_id,
        segment_id=revision.segment_id,
        run_step_id=revision.run_step_id,
        evidence_type=revision.evidence_type,
        quote=revision.quote,
        observation=revision.observation,
        interpretation=revision.interpretation,
        inference=revision.inference,
        review_status=review_status,
        locator=revision.locator,
        locator_label=_locator_label(revision.locator),
        content_hash=revision.content_hash,
        provenance=revision.provenance,
        kind="signal",
        title=title,
        confidence=max(0.0, min(1.0, confidence)),
        relationship="neutral",
        tags=tags,
        created_at=revision.created_at,
    )


@router.post("/studies", response_model=StudyRead, status_code=status.HTTP_201_CREATED)
def create_study(
    payload: StudyCreate,
    session: SessionDependency,
    blob_store: BlobStoreDependency,
    ingestion_runner: IngestionRunnerDependency,
) -> StudyRead:
    service = _service(session, blob_store, ingestion_runner)
    study = service.create_study(payload)
    return _study_response(StudyRecord(study, 0, 0))


@router.get("/studies", response_model=StudyList)
def list_studies(
    session: SessionDependency,
    blob_store: BlobStoreDependency,
    ingestion_runner: IngestionRunnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StudyList:
    records, total = _service(session, blob_store, ingestion_runner).list_studies(
        limit=limit,
        offset=offset,
    )
    return StudyList(items=[_study_response(item) for item in records], total=total)


@router.get("/studies/{study_id}", response_model=StudyRead)
def get_study(
    study_id: UUID,
    session: SessionDependency,
    blob_store: BlobStoreDependency,
    ingestion_runner: IngestionRunnerDependency,
) -> StudyRead:
    record = _service(session, blob_store, ingestion_runner).get_study_record(study_id)
    return _study_response(record)


@router.post(
    "/studies/{study_id}/sources",
    response_model=SourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_source(
    study_id: UUID,
    session: SessionDependency,
    blob_store: BlobStoreDependency,
    ingestion_runner: IngestionRunnerDependency,
    settings: SettingsDependency,
    file: Annotated[
        UploadFile,
        File(description="UTF-8 text, Markdown, CSV, or PDF source"),
    ],
    display_name: Annotated[str | None, Form(max_length=255)] = None,
) -> SourceRead:
    filename = file.filename or "untitled"
    declared_type = file.content_type
    content = await file.read(settings.upload_max_bytes + 1)
    await file.close()
    if len(content) > settings.upload_max_bytes:
        raise AppError(
            code="upload_too_large",
            message="Uploaded file exceeds the configured size limit",
            status_code=413,
            details={"max_bytes": settings.upload_max_bytes},
        )
    guessed_type = mimetypes.guess_type(filename)[0]
    mime_type = (
        guessed_type
        if declared_type in (None, "application/octet-stream") and guessed_type is not None
        else declared_type or "application/octet-stream"
    )
    source, revision = _service(session, blob_store, ingestion_runner).upload_source(
        study_id=study_id,
        filename=filename,
        display_name=display_name,
        mime_type=mime_type,
        content=content,
    )
    return _source_response(SourceRecord(source=source, revision=revision, latest_run=None))


@router.get("/studies/{study_id}/sources", response_model=SourceList)
def list_sources(
    study_id: UUID,
    session: SessionDependency,
    blob_store: BlobStoreDependency,
    ingestion_runner: IngestionRunnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SourceList:
    records, total = _service(session, blob_store, ingestion_runner).list_sources(
        study_id,
        limit=limit,
        offset=offset,
    )
    return SourceList(items=[_source_response(item) for item in records], total=total)


@router.post("/sources/{source_id}:process", response_model=RunRead)
def process_source(
    source_id: UUID,
    session: SessionDependency,
    blob_store: BlobStoreDependency,
    ingestion_runner: IngestionRunnerDependency,
) -> RunRead:
    run = _service(session, blob_store, ingestion_runner).process_source(source_id)
    return RunRead.model_validate(run)


@router.get("/studies/{study_id}/runs", response_model=RunList)
def list_runs(
    study_id: UUID,
    session: SessionDependency,
    blob_store: BlobStoreDependency,
    ingestion_runner: IngestionRunnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunList:
    runs, total = _service(session, blob_store, ingestion_runner).list_runs(
        study_id,
        limit=limit,
        offset=offset,
    )
    return RunList(items=[RunRead.model_validate(run) for run in runs], total=total)


@router.get("/studies/{study_id}/evidence", response_model=EvidenceList)
def list_evidence(
    study_id: UUID,
    session: SessionDependency,
    blob_store: BlobStoreDependency,
    ingestion_runner: IngestionRunnerDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EvidenceList:
    records, total = _service(session, blob_store, ingestion_runner).list_evidence(
        study_id,
        limit=limit,
        offset=offset,
    )
    return EvidenceList(
        items=[_evidence_response(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


def _relative_quote_span(
    segment_locator: Locator,
    evidence_locator: Locator,
) -> tuple[int, int] | None:
    if isinstance(segment_locator, TextLocator) and isinstance(evidence_locator, TextLocator):
        return (
            evidence_locator.char_start - segment_locator.char_start,
            evidence_locator.char_end - segment_locator.char_start,
        )
    if isinstance(segment_locator, CsvLocator) and isinstance(evidence_locator, CsvLocator):
        return (
            evidence_locator.rendered_char_start,
            evidence_locator.rendered_char_end,
        )
    if isinstance(segment_locator, PdfLocator) and isinstance(evidence_locator, PdfLocator):
        return (
            evidence_locator.page_char_start - segment_locator.page_char_start,
            evidence_locator.page_char_end - segment_locator.page_char_start,
        )
    return None


def _context_response(record: EvidenceContextRecord) -> EvidenceContext:
    evidence = _evidence_response(
        EvidenceRecord(record.evidence_unit, record.revision, record.source)
    )
    target_index = next(
        index
        for index, segment in enumerate(record.context_segments)
        if segment.id == record.segment.id
    )
    try:
        segment_locator = LOCATOR_ADAPTER.validate_python(record.segment.locator)
        evidence_locator = LOCATOR_ADAPTER.validate_python(record.revision.locator)
    except ValidationError as exc:
        raise AppError(
            code="provenance_corrupt",
            message="Stored evidence provenance failed its typed locator schema",
            status_code=500,
        ) from exc
    relative_span = _relative_quote_span(segment_locator, evidence_locator)
    valid_span = relative_span is not None and 0 <= relative_span[0] <= relative_span[1] <= len(
        record.segment.text
    )
    if valid_span and relative_span is not None:
        quote_start, quote_end = relative_span
        before_parts = [
            *(segment.text for segment in record.context_segments[:target_index]),
            record.segment.text[:quote_start],
        ]
        after_parts = [
            record.segment.text[quote_end:],
            *(segment.text for segment in record.context_segments[target_index + 1 :]),
        ]
        before = "\n\n".join(part for part in before_parts if part)
        after = "\n\n".join(part for part in after_parts if part)
        quote_matches_text = record.segment.text[quote_start:quote_end] == record.revision.quote
    else:
        before = "\n\n".join(segment.text for segment in record.context_segments[:target_index])
        after = "\n\n".join(segment.text for segment in record.context_segments[target_index + 1 :])
        quote_matches_text = False

    confidence_value = record.revision.provenance.get("confidence")
    confidence = (
        float(confidence_value)
        if isinstance(confidence_value, (int, float)) and not isinstance(confidence_value, bool)
        else 0.0
    )
    tags_value = record.revision.provenance.get("tags")
    tags = (
        [tag for tag in tags_value if isinstance(tag, str)] if isinstance(tags_value, list) else []
    )
    synthetic_demo = record.revision.provenance.get("synthetic_demo") is True
    method_value = record.revision.provenance.get("extraction_method")
    extraction_method = method_value if isinstance(method_value, str) else "unknown"
    stable_segment_id = record.segment.provenance.get("stable_segment_id")
    locator_identity_matches = (
        isinstance(stable_segment_id, str)
        and evidence_locator.segment_id == stable_segment_id
        and evidence_locator.source_revision_id == str(record.source_revision.id)
        and evidence_locator.source_sha256 == record.source_revision.content_hash
        and evidence_locator.quote_sha256 == sha256_text(record.revision.quote)
    )
    locator_label = _locator_label(record.revision.locator)
    return EvidenceContext(
        evidence_id=record.evidence_unit.id,
        source_name=record.source.display_name,
        locator_label=locator_label,
        before=before,
        highlight=record.revision.quote,
        after=after,
        evidence=evidence,
        source=EvidenceSourceContext(
            source_id=record.source.id,
            source_revision_id=record.source_revision.id,
            source_name=record.source.display_name,
            filename=record.source_revision.filename,
            mime_type=record.source_revision.mime_type,
            source_content_hash=record.source_revision.content_hash,
        ),
        context_segments=[
            ContextSegment(
                id=segment.id,
                ordinal=segment.ordinal,
                text=segment.text,
                locator=segment.locator,
                content_hash=segment.content_hash,
                is_target=segment.id == record.segment.id,
            )
            for segment in record.context_segments
        ],
        integrity=IntegrityCheck(
            segment_hash_matches=(sha256_text(record.segment.text) == record.segment.content_hash),
            evidence_hash_matches=(
                evidence_content_hash(
                    quote=record.revision.quote,
                    observation=record.revision.observation,
                    interpretation=record.revision.interpretation,
                    inference=record.revision.inference,
                    evidence_type=record.revision.evidence_type,
                    locator=record.revision.locator,
                    confidence=confidence,
                    tags=tags,
                    synthetic_demo=synthetic_demo,
                    extraction_method=extraction_method,
                )
                == record.revision.content_hash
            ),
            quote_matches_segment=quote_matches_text and locator_identity_matches,
        ),
    )


@router.get("/evidence/{evidence_id}/context", response_model=EvidenceContext)
def get_evidence_context(
    evidence_id: UUID,
    session: SessionDependency,
    blob_store: BlobStoreDependency,
    ingestion_runner: IngestionRunnerDependency,
) -> EvidenceContext:
    record = _service(session, blob_store, ingestion_runner).get_evidence_context(evidence_id)
    return _context_response(record)
