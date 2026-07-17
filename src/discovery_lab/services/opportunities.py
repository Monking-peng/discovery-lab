from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Never
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from discovery_lab.api.errors import AppError, ConflictError, NotFoundError
from discovery_lab.db.models import Claim, OpportunityDraft, Study
from discovery_lab.domain.enums import ClaimStatus, OpportunityStatus
from discovery_lab.domain.opportunity_schemas import OpportunityDraftCreate
from discovery_lab.services.claims import ClaimRecord, ClaimService
from discovery_lab.services.hashing import canonical_json_hash


@dataclass(frozen=True, slots=True)
class OpportunityDraftRecord:
    draft: OpportunityDraft
    claim_record: ClaimRecord
    publication_blockers: tuple[str, ...]


class OpportunityService:
    """Creates replayable drafts without implying a publication transition."""

    _DRAFT_BLOCKER = "OPPORTUNITY_DRAFT_NOT_PUBLISHED"

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_draft(
        self,
        study_id: UUID,
        payload: OpportunityDraftCreate,
    ) -> OpportunityDraftRecord:
        request_hash = canonical_json_hash(
            {
                "operation": "create_opportunity_draft",
                "study_id": str(study_id),
                "content": payload.model_dump(mode="json"),
            }
        )
        existing = self.session.scalar(
            select(OpportunityDraft).where(
                OpportunityDraft.client_request_id == payload.client_request_id
            )
        )
        if existing is not None:
            self._assert_idempotent(existing.request_hash, request_hash)
            return self._record(existing)

        if self.session.get(Study, study_id) is None:
            raise NotFoundError("Study", study_id)

        # Lock the stable Claim row so a competing review/revision cannot make the
        # eligibility decision stale between validation and insert.
        claim = self.session.scalar(
            select(Claim).where(Claim.id == payload.claim_id).with_for_update()
        )
        if claim is None:
            raise NotFoundError("Claim", payload.claim_id)
        claim_record = ClaimService(self.session).get_claim(
            payload.claim_id,
            claim_revision_id=payload.claim_revision_id,
        )
        self._assert_eligible(study_id, claim_record)

        content = payload.model_dump(mode="json", exclude={"client_request_id"})
        draft = OpportunityDraft(
            study_id=study_id,
            claim_id=payload.claim_id,
            claim_revision_id=payload.claim_revision_id,
            status=OpportunityStatus.DRAFT.value,
            title=payload.title,
            problem_statement=payload.problem_statement,
            desired_outcome=payload.desired_outcome,
            next_step=payload.next_step,
            rationale=payload.rationale,
            confidence=payload.confidence,
            assumptions=payload.assumptions,
            risks=payload.risks,
            provenance=payload.provenance,
            content_hash=canonical_json_hash(content),
            client_request_id=payload.client_request_id,
            request_hash=request_hash,
            created_at=datetime.now(UTC),
        )
        self.session.add(draft)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            concurrent = self.session.scalar(
                select(OpportunityDraft).where(
                    OpportunityDraft.client_request_id == payload.client_request_id
                )
            )
            if concurrent is None:
                raise
            self._assert_idempotent(concurrent.request_hash, request_hash)
            return self._record(concurrent)
        self.session.refresh(draft)
        return self._record(draft)

    def get_draft(self, opportunity_id: UUID) -> OpportunityDraftRecord:
        draft = self.session.get(OpportunityDraft, opportunity_id)
        if draft is None:
            raise NotFoundError("Opportunity draft", opportunity_id)
        return self._record(draft)

    def list_drafts(
        self,
        study_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[OpportunityDraftRecord], int]:
        if self.session.get(Study, study_id) is None:
            raise NotFoundError("Study", study_id)
        total = (
            self.session.scalar(
                select(func.count())
                .select_from(OpportunityDraft)
                .where(OpportunityDraft.study_id == study_id)
            )
            or 0
        )
        drafts = self.session.scalars(
            select(OpportunityDraft)
            .where(OpportunityDraft.study_id == study_id)
            .order_by(OpportunityDraft.created_at.desc(), OpportunityDraft.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return [self._record(draft) for draft in drafts], total

    def _record(self, draft: OpportunityDraft) -> OpportunityDraftRecord:
        claim_record = ClaimService(self.session).get_claim(
            draft.claim_id,
            claim_revision_id=draft.claim_revision_id,
        )
        inherited = claim_record.publication_blockers
        blockers = tuple(dict.fromkeys((self._DRAFT_BLOCKER, *inherited)))
        return OpportunityDraftRecord(
            draft=draft,
            claim_record=claim_record,
            publication_blockers=blockers,
        )

    @classmethod
    def _assert_eligible(cls, study_id: UUID, record: ClaimRecord) -> None:
        if record.claim.study_id != study_id:
            cls._invalid(
                "Opportunity and Claim must belong to the same Study",
                study_id=study_id,
                claim_id=record.claim.id,
            )
        if not record.is_current:
            cls._invalid(
                "Opportunity Draft must pin the current Claim Revision",
                claim_id=record.claim.id,
                claim_revision_id=record.revision.id,
            )
        if (
            record.claim.status != ClaimStatus.REVIEWED.value
            or record.revision_status != ClaimStatus.REVIEWED
        ):
            cls._invalid(
                "Opportunity Draft requires a current, reviewed, non-stale Claim Revision",
                claim_id=record.claim.id,
                claim_revision_id=record.revision.id,
                claim_status=record.claim.status,
                claim_revision_status=record.revision_status.value,
            )

    @staticmethod
    def _assert_idempotent(stored_hash: str, request_hash: str) -> None:
        if stored_hash != request_hash:
            raise ConflictError(
                "client_request_id was already used with a different request",
                details={"reason": "idempotency_key_reuse"},
            )

    @staticmethod
    def _invalid(message: str, **details: object) -> Never:
        raise AppError(
            code="invalid_opportunity_claim",
            message=message,
            status_code=422,
            details={key: str(value) for key, value in details.items()},
        )
