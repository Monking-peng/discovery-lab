from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from discovery_lab.agent_harness.openai_responses import (
    MissingModelCredentialError,
    ModelExtractionIntegrityError,
    ModelProviderError,
)
from discovery_lab.api.errors import (
    AppError,
    ConflictError,
    InvalidSourceError,
    NotFoundError,
    ProcessingError,
    UnsupportedSourceError,
)
from discovery_lab.db.models import (
    EvidenceRevision,
    EvidenceUnit,
    Run,
    RunStep,
    Segment,
    Source,
    SourceRevision,
    Study,
)
from discovery_lab.domain.enums import (
    EvidenceReviewStatus,
    RunStatus,
    RunStepStatus,
    SourceStatus,
    StudyStatus,
)
from discovery_lab.domain.schemas import StudyCreate
from discovery_lab.ingestion.models import Segment as ParsedSegment
from discovery_lab.ingestion.parsers import (
    ParseError,
)
from discovery_lab.ingestion.parsers import (
    UnsupportedSourceError as IngestionUnsupportedSourceError,
)
from discovery_lab.services.evidence_integrity import evidence_content_hash
from discovery_lab.services.hashing import canonical_json_hash, sha256_bytes
from discovery_lab.services.ingestion_runner import (
    CitationIntegrityFailure,
    IngestionExecutionResult,
    IngestionRunner,
)
from discovery_lab.services.storage import BlobStore


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_unit: EvidenceUnit
    revision: EvidenceRevision
    source: Source


@dataclass(frozen=True, slots=True)
class StudyRecord:
    study: Study
    source_count: int
    evidence_count: int


@dataclass(frozen=True, slots=True)
class SourceRecord:
    source: Source
    revision: SourceRevision
    latest_run: Run | None


@dataclass(frozen=True, slots=True)
class EvidenceContextRecord:
    evidence_unit: EvidenceUnit
    revision: EvidenceRevision
    segment: Segment
    source_revision: SourceRevision
    source: Source
    context_segments: tuple[Segment, ...]


class DiscoveryService:
    """Transactional application service for the Source -> Evidence slice."""

    def __init__(
        self,
        session: Session,
        *,
        blob_store: BlobStore,
        ingestion_runner: IngestionRunner,
    ) -> None:
        self.session = session
        self.blob_store = blob_store
        self.ingestion_runner = ingestion_runner

    def create_study(self, payload: StudyCreate) -> Study:
        study = Study(
            title=payload.title.strip(),
            description=payload.description,
            research_question=payload.research_question,
            status=StudyStatus.DRAFT.value,
        )
        self.session.add(study)
        self.session.commit()
        self.session.refresh(study)
        return study

    def list_studies(self, *, limit: int, offset: int) -> tuple[list[StudyRecord], int]:
        total = self.session.scalar(select(func.count()).select_from(Study)) or 0
        source_counts = (
            select(Source.study_id.label("study_id"), func.count(Source.id).label("count"))
            .group_by(Source.study_id)
            .subquery()
        )
        evidence_counts = (
            select(
                EvidenceUnit.study_id.label("study_id"),
                func.count(EvidenceUnit.id).label("count"),
            )
            .group_by(EvidenceUnit.study_id)
            .subquery()
        )
        rows = self.session.execute(
            select(
                Study,
                func.coalesce(source_counts.c.count, 0),
                func.coalesce(evidence_counts.c.count, 0),
            )
            .outerjoin(source_counts, source_counts.c.study_id == Study.id)
            .outerjoin(evidence_counts, evidence_counts.c.study_id == Study.id)
            .order_by(Study.created_at.desc(), Study.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [StudyRecord(row[0], int(row[1]), int(row[2])) for row in rows], total

    def get_study_record(self, study_id: UUID) -> StudyRecord:
        study = self.get_study(study_id)
        source_count = self.session.scalar(
            select(func.count()).select_from(Source).where(Source.study_id == study_id)
        )
        evidence_count = self.session.scalar(
            select(func.count()).select_from(EvidenceUnit).where(EvidenceUnit.study_id == study_id)
        )
        return StudyRecord(study, int(source_count or 0), int(evidence_count or 0))

    def get_study(self, study_id: UUID) -> Study:
        study = self.session.get(Study, study_id)
        if study is None:
            raise NotFoundError("study", study_id)
        return study

    def list_sources(
        self,
        study_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[SourceRecord], int]:
        self.get_study(study_id)
        total = (
            self.session.scalar(
                select(func.count()).select_from(Source).where(Source.study_id == study_id)
            )
            or 0
        )
        latest_revision_id = (
            select(SourceRevision.id)
            .where(SourceRevision.source_id == Source.id)
            .order_by(
                SourceRevision.revision.desc(),
                SourceRevision.created_at.desc(),
                SourceRevision.id.desc(),
            )
            .limit(1)
            .correlate(Source)
            .scalar_subquery()
        )
        latest_run_id = (
            select(Run.id)
            .where(Run.source_id == Source.id)
            .order_by(Run.created_at.desc(), Run.id.desc())
            .limit(1)
            .correlate(Source)
            .scalar_subquery()
        )
        rows = self.session.execute(
            select(Source, SourceRevision, Run)
            .join(SourceRevision, SourceRevision.id == latest_revision_id)
            .outerjoin(Run, Run.id == latest_run_id)
            .options(selectinload(Run.steps))
            .where(Source.study_id == study_id)
            .order_by(Source.created_at.desc(), Source.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return [
            SourceRecord(source=row[0], revision=row[1], latest_run=row[2]) for row in rows
        ], int(total)

    def list_runs(
        self,
        study_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Run], int]:
        self.get_study(study_id)
        total = (
            self.session.scalar(
                select(func.count()).select_from(Run).where(Run.study_id == study_id)
            )
            or 0
        )
        runs = list(
            self.session.scalars(
                select(Run)
                .options(selectinload(Run.steps))
                .where(Run.study_id == study_id)
                .order_by(Run.created_at.desc(), Run.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return runs, int(total)

    def upload_source(
        self,
        *,
        study_id: UUID,
        filename: str,
        display_name: str | None,
        mime_type: str,
        content: bytes,
    ) -> tuple[Source, SourceRevision]:
        self.get_study(study_id)
        if not content:
            raise InvalidSourceError("Uploaded files must not be empty")

        safe_filename = Path(filename).name.strip() or "untitled"
        if len(safe_filename) > 255:
            raise InvalidSourceError("Source filenames must be 255 characters or fewer")
        if len(mime_type) > 150:
            raise InvalidSourceError("Source MIME types must be 150 characters or fewer")
        content_hash = sha256_bytes(content)
        blob_uri = self.blob_store.put(content, content_hash=content_hash)
        now = datetime.now(UTC).isoformat()

        source = Source(
            study_id=study_id,
            display_name=(display_name or safe_filename).strip() or safe_filename,
            source_type="upload",
            status=SourceStatus.UPLOADED.value,
        )
        revision = SourceRevision(
            source=source,
            revision=1,
            filename=safe_filename,
            mime_type=mime_type,
            byte_size=len(content),
            content_hash=content_hash,
            blob_uri=blob_uri,
            provenance={
                "ingested_via": "multipart_upload",
                "original_filename": safe_filename,
                "declared_mime_type": mime_type,
                "uploaded_at": now,
            },
        )
        self.session.add(source)
        self.session.commit()
        self.session.refresh(source)
        self.session.refresh(revision)
        return source, revision

    def process_source(self, source_id: UUID) -> Run:
        source = self.session.get(Source, source_id)
        if source is None:
            raise NotFoundError("source", source_id)
        source_revision = self.session.scalar(
            select(SourceRevision)
            .where(SourceRevision.source_id == source_id)
            .order_by(SourceRevision.revision.desc())
            .limit(1)
        )
        if source_revision is None:
            raise NotFoundError("source_revision", source_id)

        profile = self.ingestion_runner.profile
        workflow = profile["workflow"]
        workflow_name = str(workflow["name"])
        workflow_version = str(workflow["version"])
        input_snapshot = {
            "source_revision_id": str(source_revision.id),
            "source_content_hash": source_revision.content_hash,
            "ingestion_profile": profile,
        }
        input_hash = canonical_json_hash(input_snapshot)
        existing = self._active_run(source_id=source_id, input_hash=input_hash)
        if existing is not None:
            if existing.status == RunStatus.SUCCEEDED.value:
                return existing
            raise ConflictError(
                "An identical source processing run is already active",
                details={"run_id": str(existing.id)},
            )

        now = datetime.now(UTC)
        run = Run(
            study_id=source.study_id,
            source_id=source.id,
            workflow_name=workflow_name,
            workflow_version=workflow_version,
            status=RunStatus.RUNNING.value,
            input_snapshot=input_snapshot,
            input_hash=input_hash,
            output_summary={},
            started_at=now,
        )
        parse_step = RunStep(
            run=run,
            name="parse_source",
            ordinal=0,
            status=RunStepStatus.RUNNING.value,
            input_snapshot={
                "source_revision_id": str(source_revision.id),
                "source_content_hash": source_revision.content_hash,
                "parser": profile["parser"],
            },
            input_hash=canonical_json_hash({"run_input_hash": input_hash, "step": "parse_source"}),
            output_summary={},
            started_at=now,
        )
        extract_step = RunStep(
            run=run,
            name="extract_evidence",
            ordinal=1,
            status=RunStepStatus.PENDING.value,
            input_snapshot={"extractor": profile["extractor"]},
            input_hash=canonical_json_hash(
                {"run_input_hash": input_hash, "step": "extract_evidence"}
            ),
            output_summary={},
        )
        verify_step = RunStep(
            run=run,
            name="verify_citations",
            ordinal=2,
            status=RunStepStatus.PENDING.value,
            input_snapshot={"verifier": profile["verifier"]},
            input_hash=canonical_json_hash(
                {"run_input_hash": input_hash, "step": "verify_citations"}
            ),
            output_summary={},
        )
        source.status = SourceStatus.PROCESSING.value
        self.session.add(run)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            competing = self._active_run(source_id=source_id, input_hash=input_hash)
            if competing is not None and competing.status == RunStatus.SUCCEEDED.value:
                return competing
            details = {"run_id": str(competing.id)} if competing is not None else None
            raise ConflictError(
                "An identical source processing run was started concurrently",
                details=details,
            ) from exc

        run_id = run.id
        try:
            raw_content = self.blob_store.get(source_revision.blob_uri)
            if sha256_bytes(raw_content) != source_revision.content_hash:
                raise InvalidSourceError(
                    "Stored source bytes no longer match their immutable revision hash"
                )
            result = self.ingestion_runner.run(
                run_id=str(run.id),
                source_revision_id=str(source_revision.id),
                content=raw_content,
                filename=source_revision.filename,
                media_type=source_revision.mime_type,
            )
            if not result.segments:
                raise InvalidSourceError("The source contains no extractable text segments")

            segment_by_stable_id = self._persist_or_reuse_segments(
                source_revision=source_revision,
                parsed_segments=result.segments,
            )
            self._persist_verified_evidence(
                source=source,
                source_revision=source_revision,
                run=run,
                extract_step=extract_step,
                verify_step=verify_step,
                result=result,
                segment_by_stable_id=segment_by_stable_id,
            )
            self._complete_run(
                source=source,
                run=run,
                parse_step=parse_step,
                extract_step=extract_step,
                verify_step=verify_step,
                result=result,
            )
            self.session.commit()
            return self._load_run(run.id)
        except Exception as exc:
            self.session.rollback()
            mapped_error = self._map_processing_error(
                exc,
                run_id=run_id,
                mime_type=source_revision.mime_type,
            )
            failed_step = self._failed_step_for(exc)
            self._mark_run_failed(
                run_id,
                source_id,
                mapped_error,
                failed_step_name=failed_step,
            )
            raise mapped_error from exc

    def _active_run(self, *, source_id: UUID, input_hash: str) -> Run | None:
        return self.session.scalar(
            select(Run)
            .options(selectinload(Run.steps))
            .where(
                Run.source_id == source_id,
                Run.input_hash == input_hash,
                Run.status.in_([RunStatus.RUNNING.value, RunStatus.SUCCEEDED.value]),
            )
            .order_by(Run.created_at.desc())
            .limit(1)
        )

    def _persist_or_reuse_segments(
        self,
        *,
        source_revision: SourceRevision,
        parsed_segments: tuple[ParsedSegment, ...],
    ) -> dict[str, Segment]:
        existing = list(
            self.session.scalars(
                select(Segment)
                .where(Segment.source_revision_id == source_revision.id)
                .order_by(Segment.ordinal)
            )
        )
        if existing:
            if len(existing) != len(parsed_segments):
                raise InvalidSourceError("Parser output drifted for this immutable source revision")
            reused: dict[str, Segment] = {}
            for ordinal, (stored, parsed) in enumerate(zip(existing, parsed_segments, strict=True)):
                parsed_locator = parsed.locator.model_dump(mode="json")
                stable_id = stored.provenance.get("stable_segment_id")
                if (
                    stored.ordinal != ordinal
                    or stored.text != parsed.text
                    or stored.content_hash != parsed.text_sha256
                    or stored.locator != parsed_locator
                    or stable_id != parsed.segment_id
                ):
                    raise InvalidSourceError(
                        "Parser output drifted for this immutable source revision"
                    )
                reused[parsed.segment_id] = stored
            return reused

        created: dict[str, Segment] = {}
        for ordinal, parsed in enumerate(parsed_segments):
            segment = Segment(
                source_revision_id=source_revision.id,
                ordinal=ordinal,
                text=parsed.text,
                content_hash=parsed.text_sha256,
                locator=parsed.locator.model_dump(mode="json"),
                provenance={
                    "schema_version": parsed.schema_version,
                    "stable_segment_id": parsed.segment_id,
                    "source_kind": parsed.source_kind.value,
                    "source_sha256": parsed.source_sha256,
                    "metadata": parsed.metadata,
                    "parser_schema": self.ingestion_runner.profile["parser"]["schema_version"],
                },
            )
            self.session.add(segment)
            created[parsed.segment_id] = segment
        self.session.flush()
        return created

    def _persist_verified_evidence(
        self,
        *,
        source: Source,
        source_revision: SourceRevision,
        run: Run,
        extract_step: RunStep,
        verify_step: RunStep,
        result: IngestionExecutionResult,
        segment_by_stable_id: dict[str, Segment],
    ) -> None:
        checks = {check.draft_id: check for check in result.verification.checks}
        drafts = {draft.draft_id: draft for draft in result.extraction.drafts}
        if (
            len(checks) != len(result.verification.checks)
            or len(drafts) != len(result.extraction.drafts)
            or checks.keys() != drafts.keys()
            or any(not check.verified for check in checks.values())
        ):
            raise CitationIntegrityFailure(
                "citation verification did not match every unique evidence draft"
            )

        usage = (
            result.extraction.usage.model_dump(mode="json")
            if result.extraction.usage is not None
            else None
        )
        for draft in result.extraction.drafts:
            target_segment = segment_by_stable_id.get(draft.segment_id)
            if target_segment is None:
                raise CitationIntegrityFailure(
                    "verified evidence referenced an unknown persisted segment"
                )
            check = checks[draft.draft_id]
            locator = draft.locator.model_dump(mode="json")
            tags = list(draft.tags)
            extraction_method = draft.extraction_method.value
            evidence_type = "source_excerpt"
            provenance = {
                "schema_version": draft.schema_version,
                "draft_id": draft.draft_id,
                "stable_segment_id": draft.segment_id,
                "source_kind": target_segment.provenance.get("source_kind"),
                "extractor": {
                    "name": result.extraction.extractor_name,
                    "version": result.extraction.extractor_version,
                    "prompt_version": result.extraction.prompt_version,
                    "model": result.extraction.model,
                    "response_id": result.extraction.response_id,
                },
                "extraction_method": extraction_method,
                "synthetic_demo": draft.synthetic_demo,
                "confidence": draft.confidence,
                "tags": tags,
                "usage": usage,
                "verification": check.model_dump(mode="json"),
                "semantic_support_checked": False,
                "run": {
                    "run_id": str(run.id),
                    "extract_step_id": str(extract_step.id),
                    "verify_step_id": str(verify_step.id),
                },
            }
            evidence_unit = EvidenceUnit(study_id=source.study_id)
            evidence_revision = EvidenceRevision(
                evidence_unit=evidence_unit,
                source_revision_id=source_revision.id,
                segment_id=target_segment.id,
                run_step_id=extract_step.id,
                revision=1,
                evidence_type=evidence_type,
                quote=draft.quote,
                observation=draft.observation,
                interpretation=draft.interpretation,
                inference=draft.inference,
                review_status=EvidenceReviewStatus.PROPOSED.value,
                locator=locator,
                content_hash=evidence_content_hash(
                    quote=draft.quote,
                    observation=draft.observation,
                    interpretation=draft.interpretation,
                    inference=draft.inference,
                    evidence_type=evidence_type,
                    locator=locator,
                    confidence=draft.confidence,
                    tags=tags,
                    synthetic_demo=draft.synthetic_demo,
                    extraction_method=extraction_method,
                ),
                provenance=provenance,
            )
            self.session.add(evidence_revision)

    def _complete_run(
        self,
        *,
        source: Source,
        run: Run,
        parse_step: RunStep,
        extract_step: RunStep,
        verify_step: RunStep,
        result: IngestionExecutionResult,
    ) -> None:
        completed_at = datetime.now(UTC)
        segment_artifact_hash = canonical_json_hash(
            [segment.model_dump(mode="json") for segment in result.segments]
        )
        extraction_artifact_hash = canonical_json_hash(result.extraction.model_dump(mode="json"))
        verification_artifact_hash = canonical_json_hash(
            result.verification.model_dump(mode="json")
        )
        warnings = list(result.extraction.warnings)
        if not result.extraction.drafts:
            warnings.append("no_evidence_proposals")

        parse_step.status = RunStepStatus.SUCCEEDED.value
        parse_step.completed_at = completed_at
        parse_step.output_summary = {
            "segment_count": len(result.segments),
            "source_kinds": sorted({segment.source_kind.value for segment in result.segments}),
            "artifact_sha256": segment_artifact_hash,
        }
        extract_step.status = RunStepStatus.SUCCEEDED.value
        extract_step.started_at = completed_at
        extract_step.completed_at = completed_at
        extract_step.output_summary = {
            "evidence_candidate_count": len(result.extraction.drafts),
            "artifact_sha256": extraction_artifact_hash,
            "extractor": {
                "name": result.extraction.extractor_name,
                "version": result.extraction.extractor_version,
                "prompt_version": result.extraction.prompt_version,
                "model": result.extraction.model,
                "response_id": result.extraction.response_id,
            },
            "synthetic_demo": result.extraction.synthetic_demo,
            "warnings": warnings,
            "usage": (
                result.extraction.usage.model_dump(mode="json")
                if result.extraction.usage is not None
                else None
            ),
        }
        verify_step.status = RunStepStatus.SUCCEEDED.value
        verify_step.started_at = completed_at
        verify_step.completed_at = completed_at
        verify_step.output_summary = {
            "checked_count": len(result.verification.checks),
            "verified_count": sum(check.verified for check in result.verification.checks),
            "all_verified": result.verification.all_verified,
            "semantic_support_checked": False,
            "artifact_sha256": verification_artifact_hash,
        }
        run.status = RunStatus.SUCCEEDED.value
        run.completed_at = completed_at
        run.output_summary = {
            "stage": result.graph_state["stage"],
            "segment_count": len(result.segments),
            "evidence_candidate_count": len(result.extraction.drafts),
            "verified_citation_count": len(result.verification.checks),
            "synthetic_demo": result.extraction.synthetic_demo,
            "warnings": warnings,
            "artifact_hashes": {
                "segments": segment_artifact_hash,
                "extraction": extraction_artifact_hash,
                "verification": verification_artifact_hash,
            },
        }
        source.status = SourceStatus.PROCESSED.value

    @staticmethod
    def _map_processing_error(
        exc: Exception,
        *,
        run_id: UUID,
        mime_type: str,
    ) -> AppError:
        if isinstance(exc, AppError):
            return exc
        if isinstance(exc, IngestionUnsupportedSourceError):
            return UnsupportedSourceError(mime_type)
        if isinstance(exc, ParseError):
            return InvalidSourceError(str(exc))
        if isinstance(exc, CitationIntegrityFailure):
            return InvalidSourceError(
                "Evidence citations failed deterministic replay; no evidence was persisted"
            )
        if isinstance(exc, MissingModelCredentialError):
            return AppError(
                code="model_not_configured",
                message="The configured evidence model is missing its API credential",
                status_code=422,
            )
        if isinstance(exc, ModelExtractionIntegrityError):
            return AppError(
                code="model_output_invalid",
                message="The evidence model returned output that failed integrity checks",
                status_code=502,
            )
        if isinstance(exc, ModelProviderError):
            status_code = 429 if exc.status_code == 429 else 502
            return AppError(
                code=("model_rate_limited" if status_code == 429 else "model_provider_failed"),
                message="The configured evidence model provider could not complete the request",
                status_code=status_code,
            )
        return ProcessingError(run_id)

    @staticmethod
    def _failed_step_for(exc: Exception) -> str:
        if isinstance(exc, (IngestionUnsupportedSourceError, ParseError, InvalidSourceError)):
            return "parse_source"
        if isinstance(
            exc,
            (
                MissingModelCredentialError,
                ModelExtractionIntegrityError,
                ModelProviderError,
            ),
        ):
            return "extract_evidence"
        if isinstance(exc, CitationIntegrityFailure):
            return "verify_citations"
        return "verify_citations"

    def list_evidence(
        self,
        study_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[EvidenceRecord], int]:
        self.get_study(study_id)
        latest_revision = (
            select(func.max(EvidenceRevision.revision))
            .where(EvidenceRevision.evidence_unit_id == EvidenceUnit.id)
            .correlate(EvidenceUnit)
            .scalar_subquery()
        )
        statement = (
            select(EvidenceUnit, EvidenceRevision, Source)
            .join(
                EvidenceRevision,
                EvidenceRevision.evidence_unit_id == EvidenceUnit.id,
            )
            .join(
                SourceRevision,
                SourceRevision.id == EvidenceRevision.source_revision_id,
            )
            .join(Source, Source.id == SourceRevision.source_id)
            .where(
                EvidenceUnit.study_id == study_id,
                EvidenceRevision.revision == latest_revision,
            )
            .order_by(EvidenceUnit.created_at.desc(), EvidenceUnit.id)
            .limit(limit)
            .offset(offset)
        )
        records = [
            EvidenceRecord(evidence_unit=row[0], revision=row[1], source=row[2])
            for row in self.session.execute(statement).all()
        ]
        total = (
            self.session.scalar(
                select(func.count())
                .select_from(EvidenceUnit)
                .where(EvidenceUnit.study_id == study_id)
            )
            or 0
        )
        return records, total

    def get_evidence_context(self, evidence_id: UUID) -> EvidenceContextRecord:
        row = self.session.execute(
            select(EvidenceUnit, EvidenceRevision, Segment, SourceRevision, Source)
            .join(
                EvidenceRevision,
                EvidenceRevision.evidence_unit_id == EvidenceUnit.id,
            )
            .join(Segment, Segment.id == EvidenceRevision.segment_id)
            .join(SourceRevision, SourceRevision.id == EvidenceRevision.source_revision_id)
            .join(Source, Source.id == SourceRevision.source_id)
            .where(EvidenceUnit.id == evidence_id)
            .order_by(EvidenceRevision.revision.desc())
            .limit(1)
        ).one_or_none()
        if row is None:
            raise NotFoundError("evidence", evidence_id)
        evidence_unit, revision, segment, source_revision, source = row
        context_segments = tuple(
            self.session.scalars(
                select(Segment)
                .where(
                    Segment.source_revision_id == source_revision.id,
                    Segment.ordinal >= max(0, segment.ordinal - 1),
                    Segment.ordinal <= segment.ordinal + 1,
                )
                .order_by(Segment.ordinal)
            )
        )
        return EvidenceContextRecord(
            evidence_unit=evidence_unit,
            revision=revision,
            segment=segment,
            source_revision=source_revision,
            source=source,
            context_segments=context_segments,
        )

    def _load_run(self, run_id: UUID) -> Run:
        run = self.session.scalar(
            select(Run).options(selectinload(Run.steps)).where(Run.id == run_id)
        )
        if run is None:
            raise NotFoundError("run", run_id)
        return run

    def _mark_run_failed(
        self,
        run_id: UUID,
        source_id: UUID,
        exc: AppError,
        *,
        failed_step_name: str,
    ) -> None:
        run = self._load_run(run_id)
        source = self.session.get(Source, source_id)
        now = datetime.now(UTC)
        run.status = RunStatus.FAILED.value
        run.completed_at = now
        run.error = {"code": exc.code}
        failed_ordinal = next(
            (step.ordinal for step in run.steps if step.name == failed_step_name),
            0,
        )
        for step in run.steps:
            step.completed_at = now
            if step.ordinal < failed_ordinal:
                step.status = RunStepStatus.SUCCEEDED.value
                step.started_at = step.started_at or run.started_at
                step.output_summary = {"completed_before_failure": True}
            elif step.ordinal == failed_ordinal:
                step.status = RunStepStatus.FAILED.value
                step.started_at = step.started_at or now
                step.error = {"code": exc.code}
            else:
                step.status = RunStepStatus.SKIPPED.value
        if source is not None:
            source.status = SourceStatus.FAILED.value
        self.session.commit()
