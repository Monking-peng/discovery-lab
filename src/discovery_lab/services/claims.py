from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Never
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from discovery_lab.api.errors import AppError, ConflictError, NotFoundError
from discovery_lab.db.models import (
    Claim,
    ClaimEvidenceEdge,
    ClaimReview,
    ClaimRevision,
    EvidenceReview,
    EvidenceRevision,
    EvidenceUnit,
    SourceRevision,
    Study,
)
from discovery_lab.domain.claim_schemas import (
    ClaimCreate,
    ClaimEvidenceEdgeCreate,
    ClaimReviewCreate,
    ClaimRevisionCreate,
    EvidenceReviewCreate,
    EvidenceRevisionAuthorCreate,
)
from discovery_lab.domain.enums import (
    ClaimEvidenceRelation,
    ClaimStatus,
    EvidenceReviewStatus,
    ReviewDecision,
)
from discovery_lab.services.evidence_integrity import evidence_content_hash
from discovery_lab.services.hashing import canonical_json_hash


@dataclass(frozen=True, slots=True)
class ClaimEdgeRecord:
    edge: ClaimEvidenceEdge
    evidence_revision: EvidenceRevision
    source_revision: SourceRevision
    latest_evidence_review: EvidenceReview | None


@dataclass(frozen=True, slots=True)
class ClaimRecord:
    claim: Claim
    revision: ClaimRevision
    edges: tuple[ClaimEdgeRecord, ...]
    latest_review: ClaimReview | None
    is_current: bool
    revision_status: ClaimStatus
    publication_blockers: tuple[str, ...]


class ClaimService:
    """Transactional, revision-pinned Evidence Review and Claim application service."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def review_evidence(
        self,
        evidence_id: UUID,
        payload: EvidenceReviewCreate,
    ) -> EvidenceReview:
        request_hash = self._request_hash(
            "review_evidence",
            {"evidence_id": str(evidence_id), **payload.model_dump(mode="json")},
        )
        existing = self.session.scalar(
            select(EvidenceReview).where(
                EvidenceReview.client_request_id == payload.client_request_id
            )
        )
        if existing is not None:
            self._assert_idempotent(existing.request_hash, request_hash)
            return existing

        evidence_revision = self._evidence_revision(evidence_id, payload.evidence_revision_id)
        if payload.decision is ReviewDecision.ACCEPT and self._is_synthetic(evidence_revision):
            self._invalid(
                "Synthetic or simulated evidence cannot be accepted as formal evidence",
                evidence_id=evidence_id,
                evidence_revision_id=evidence_revision.id,
            )
        if payload.decision is ReviewDecision.ACCEPT:
            self._assert_formally_traceable(evidence_revision)

        review = EvidenceReview(
            evidence_unit_id=evidence_id,
            evidence_revision_id=evidence_revision.id,
            decision=payload.decision.value,
            reviewer=payload.reviewer,
            rationale=payload.rationale,
            client_request_id=payload.client_request_id,
            request_hash=request_hash,
            created_at=datetime.now(UTC),
        )
        self.session.add(review)

        if payload.decision is not ReviewDecision.ACCEPT:
            self._mark_dependent_reviewed_claims_stale(evidence_revision.id)

        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            concurrent = self.session.scalar(
                select(EvidenceReview).where(
                    EvidenceReview.client_request_id == payload.client_request_id
                )
            )
            if concurrent is None:
                raise
            self._assert_idempotent(concurrent.request_hash, request_hash)
            return concurrent
        self.session.refresh(review)
        return review

    def author_evidence_revision(
        self,
        evidence_id: UUID,
        payload: EvidenceRevisionAuthorCreate,
    ) -> EvidenceRevision:
        """Create a human-authored revision without changing its pinned source quote."""

        request_hash = self._request_hash(
            "author_evidence_revision",
            {"evidence_id": str(evidence_id), **payload.model_dump(mode="json")},
        )
        existing = self.session.scalar(
            select(EvidenceRevision).where(
                EvidenceRevision.client_request_id == payload.client_request_id
            )
        )
        if existing is not None:
            if existing.request_hash is None:
                raise RuntimeError("Authored Evidence Revision is missing its request hash")
            self._assert_idempotent(existing.request_hash, request_hash)
            if existing.evidence_unit_id != evidence_id:
                raise ConflictError(
                    "client_request_id belongs to another Evidence Unit",
                    details={"reason": "idempotency_key_reuse"},
                )
            return existing

        base = self._evidence_revision(evidence_id, payload.base_revision_id)
        latest = self.session.scalar(
            select(EvidenceRevision)
            .where(EvidenceRevision.evidence_unit_id == evidence_id)
            .order_by(EvidenceRevision.revision.desc())
            .limit(1)
        )
        if latest is None:
            raise RuntimeError("Evidence Unit has no revision")
        if latest.id != base.id:
            raise ConflictError(
                "Evidence revision base is not the current revision",
                details={
                    "evidence_id": str(evidence_id),
                    "base_revision_id": str(base.id),
                    "current_revision_id": str(latest.id),
                },
            )
        if base.provenance.get("simulation_output") is True:
            self._invalid(
                "Simulation output cannot be converted into real user evidence",
                evidence_revision_id=base.id,
            )
        self._assert_formally_traceable(base)

        tags = self._human_revision_tags(payload.tags)
        provenance = dict(base.provenance)
        provenance.update(
            {
                "confidence": payload.confidence,
                "tags": tags,
                "synthetic_demo": False,
                "simulation_output": False,
                "extraction_method": "human_authored",
                "human_authored": True,
                "derived_from_synthetic_demo": self._is_synthetic(base),
                "parent_revision_id": str(base.id),
                "editor": payload.editor,
                "edit_rationale": payload.rationale,
            }
        )
        authored = EvidenceRevision(
            evidence_unit_id=evidence_id,
            parent_revision_id=base.id,
            source_revision_id=base.source_revision_id,
            segment_id=base.segment_id,
            run_step_id=None,
            revision=base.revision + 1,
            evidence_type=base.evidence_type,
            quote=base.quote,
            observation=payload.observation,
            interpretation=payload.interpretation,
            inference=payload.inference,
            review_status=EvidenceReviewStatus.PROPOSED.value,
            locator=base.locator,
            content_hash=evidence_content_hash(
                quote=base.quote,
                observation=payload.observation,
                interpretation=payload.interpretation,
                inference=payload.inference,
                evidence_type=base.evidence_type,
                locator=base.locator,
                confidence=payload.confidence,
                tags=tags,
                synthetic_demo=False,
                extraction_method="human_authored",
            ),
            provenance=provenance,
            client_request_id=payload.client_request_id,
            request_hash=request_hash,
            created_at=datetime.now(UTC),
        )
        self.session.add(authored)
        # The old Claim remains replayable, but a successor Evidence Revision
        # means its judgment must be revisited before downstream publication.
        self._mark_dependent_reviewed_claims_stale(base.id)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            concurrent = self.session.scalar(
                select(EvidenceRevision).where(
                    EvidenceRevision.client_request_id == payload.client_request_id
                )
            )
            if concurrent is not None and concurrent.request_hash is not None:
                self._assert_idempotent(concurrent.request_hash, request_hash)
                return concurrent
            raise ConflictError(
                "Evidence changed while the new revision was being created",
                details={"evidence_id": str(evidence_id), "reason": "revision_conflict"},
            ) from exc
        self.session.refresh(authored)
        return authored

    def create_claim(self, study_id: UUID, payload: ClaimCreate) -> ClaimRecord:
        request_hash = self._request_hash(
            "create_claim",
            {"study_id": str(study_id), **payload.model_dump(mode="json")},
        )
        existing = self.session.scalar(
            select(ClaimRevision).where(
                ClaimRevision.client_request_id == payload.client_request_id
            )
        )
        if existing is not None:
            self._assert_idempotent(existing.request_hash, request_hash)
            return self._claim_record_for_revision(existing)

        if self.session.get(Study, study_id) is None:
            raise NotFoundError("Study", study_id)
        validated_edges = self._validate_edges(study_id, payload.evidence_edges)

        claim = Claim(study_id=study_id, status=ClaimStatus.PROPOSED.value)
        self.session.add(claim)
        self.session.flush()
        revision = self._new_revision(
            claim=claim,
            revision_number=1,
            base_revision_id=None,
            payload=payload,
            request_hash=request_hash,
        )
        self.session.add(revision)
        self.session.flush()
        self._add_edges(revision.id, payload.evidence_edges, validated_edges)
        return self._commit_claim_creation(revision, request_hash, payload.client_request_id)

    def create_claim_revision(
        self,
        claim_id: UUID,
        payload: ClaimRevisionCreate,
    ) -> ClaimRecord:
        request_hash = self._request_hash(
            "create_claim_revision",
            {"claim_id": str(claim_id), **payload.model_dump(mode="json")},
        )
        existing = self.session.scalar(
            select(ClaimRevision).where(
                ClaimRevision.client_request_id == payload.client_request_id
            )
        )
        if existing is not None:
            self._assert_idempotent(existing.request_hash, request_hash)
            return self._claim_record_for_revision(existing)

        claim = self.session.get(Claim, claim_id)
        if claim is None:
            raise NotFoundError("Claim", claim_id)
        latest = self._latest_revision(claim_id)
        if latest.id != payload.base_revision_id:
            raise ConflictError(
                "Claim revision base is not the current revision",
                details={
                    "claim_id": str(claim_id),
                    "base_revision_id": str(payload.base_revision_id),
                    "current_revision_id": str(latest.id),
                },
            )
        validated_edges = self._validate_edges(claim.study_id, payload.evidence_edges)

        revision = self._new_revision(
            claim=claim,
            revision_number=latest.revision + 1,
            base_revision_id=latest.id,
            payload=payload,
            request_hash=request_hash,
        )
        self.session.add(revision)
        self.session.flush()
        self._add_edges(revision.id, payload.evidence_edges, validated_edges)
        claim.status = ClaimStatus.PROPOSED.value
        return self._commit_claim_creation(revision, request_hash, payload.client_request_id)

    def list_claims(
        self,
        study_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[ClaimRecord], int]:
        if self.session.get(Study, study_id) is None:
            raise NotFoundError("Study", study_id)
        total = (
            self.session.scalar(
                select(func.count()).select_from(Claim).where(Claim.study_id == study_id)
            )
            or 0
        )
        claims = self.session.scalars(
            select(Claim)
            .where(Claim.study_id == study_id)
            .order_by(Claim.created_at.desc(), Claim.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        records = [
            self._claim_record_for_revision(self._latest_revision(item.id)) for item in claims
        ]
        return records, total

    def get_claim(
        self,
        claim_id: UUID,
        *,
        claim_revision_id: UUID | None = None,
    ) -> ClaimRecord:
        claim = self.session.get(Claim, claim_id)
        if claim is None:
            raise NotFoundError("Claim", claim_id)
        if claim_revision_id is None:
            selected_revision = self._latest_revision(claim_id)
        else:
            candidate = self.session.get(ClaimRevision, claim_revision_id)
            if candidate is None or candidate.claim_id != claim_id:
                raise NotFoundError("Claim revision", claim_revision_id)
            selected_revision = candidate
        return self._claim_record_for_revision(selected_revision)

    def review_claim(
        self,
        claim_revision_id: UUID,
        payload: ClaimReviewCreate,
    ) -> tuple[ClaimReview, Claim]:
        request_hash = self._request_hash(
            "review_claim",
            {
                "claim_revision_id": str(claim_revision_id),
                **payload.model_dump(mode="json"),
            },
        )
        existing = self.session.scalar(
            select(ClaimReview).where(ClaimReview.client_request_id == payload.client_request_id)
        )
        if existing is not None:
            self._assert_idempotent(existing.request_hash, request_hash)
            existing_revision = self.session.get(ClaimRevision, existing.claim_revision_id)
            if existing_revision is None:
                raise RuntimeError("Claim review points to a missing immutable revision")
            existing_claim = self.session.get(Claim, existing_revision.claim_id)
            if existing_claim is None:
                raise RuntimeError("Claim review points to a missing claim")
            return existing, existing_claim

        revision = self.session.get(ClaimRevision, claim_revision_id)
        if revision is None:
            raise NotFoundError("Claim revision", claim_revision_id)
        claim = self.session.get(Claim, revision.claim_id)
        if claim is None:
            raise RuntimeError("Claim revision points to a missing claim")

        evidence_review_snapshot = (
            self._assert_claim_is_acceptable(revision)
            if payload.decision is ReviewDecision.ACCEPT
            else {}
        )

        review = ClaimReview(
            claim_revision_id=revision.id,
            decision=payload.decision.value,
            reviewer=payload.reviewer,
            rationale=payload.rationale,
            evidence_review_snapshot=evidence_review_snapshot,
            client_request_id=payload.client_request_id,
            request_hash=request_hash,
            created_at=datetime.now(UTC),
        )
        self.session.add(review)
        latest = self._latest_revision(claim.id)
        if latest.id == revision.id:
            claim.status = {
                ReviewDecision.ACCEPT: ClaimStatus.REVIEWED.value,
                ReviewDecision.REQUEST_CHANGES: ClaimStatus.PROPOSED.value,
                ReviewDecision.REJECT: ClaimStatus.REJECTED.value,
            }[payload.decision]
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            concurrent = self.session.scalar(
                select(ClaimReview).where(
                    ClaimReview.client_request_id == payload.client_request_id
                )
            )
            if concurrent is None:
                raise
            self._assert_idempotent(concurrent.request_hash, request_hash)
            concurrent_revision = self.session.get(ClaimRevision, concurrent.claim_revision_id)
            if concurrent_revision is None:
                raise RuntimeError("Claim review points to a missing immutable revision") from None
            concurrent_claim = self.session.get(Claim, concurrent_revision.claim_id)
            if concurrent_claim is None:
                raise RuntimeError("Claim review points to a missing claim") from None
            return concurrent, concurrent_claim
        self.session.refresh(review)
        return review, claim

    def _commit_claim_creation(
        self,
        revision: ClaimRevision,
        request_hash: str,
        client_request_id: str,
    ) -> ClaimRecord:
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            concurrent = self.session.scalar(
                select(ClaimRevision).where(ClaimRevision.client_request_id == client_request_id)
            )
            if concurrent is None:
                raise
            self._assert_idempotent(concurrent.request_hash, request_hash)
            return self._claim_record_for_revision(concurrent)
        self.session.refresh(revision)
        return self._claim_record_for_revision(revision)

    def _new_revision(
        self,
        *,
        claim: Claim,
        revision_number: int,
        base_revision_id: UUID | None,
        payload: ClaimCreate | ClaimRevisionCreate,
        request_hash: str,
    ) -> ClaimRevision:
        content = payload.model_dump(mode="json", exclude={"client_request_id", "base_revision_id"})
        return ClaimRevision(
            claim_id=claim.id,
            revision=revision_number,
            base_revision_id=base_revision_id,
            statement=payload.statement,
            topic_key=payload.topic_key,
            summary=payload.summary,
            rationale=payload.rationale,
            confidence=payload.confidence,
            counterevidence_status=payload.counterevidence_status.value,
            counterevidence_summary=payload.counterevidence_summary,
            provenance=payload.provenance,
            content_hash=canonical_json_hash(content),
            client_request_id=payload.client_request_id,
            request_hash=request_hash,
        )

    def _validate_edges(
        self,
        study_id: UUID,
        inputs: list[ClaimEvidenceEdgeCreate],
    ) -> dict[UUID, EvidenceRevision]:
        seen: set[UUID] = set()
        revisions: dict[UUID, EvidenceRevision] = {}
        for edge in inputs:
            if edge.evidence_revision_id in seen:
                self._invalid(
                    "A Claim Revision cannot link the same Evidence Revision more than once",
                    evidence_revision_id=edge.evidence_revision_id,
                )
            seen.add(edge.evidence_revision_id)
            evidence_revision = self._evidence_revision(edge.evidence_id, edge.evidence_revision_id)
            evidence_unit = self.session.get(EvidenceUnit, edge.evidence_id)
            if evidence_unit is None or evidence_unit.study_id != study_id:
                self._invalid(
                    "Claim and evidence must belong to the same Study",
                    study_id=study_id,
                    evidence_id=edge.evidence_id,
                    evidence_revision_id=edge.evidence_revision_id,
                )
            if edge.relation in {
                ClaimEvidenceRelation.SUPPORTS,
                ClaimEvidenceRelation.CONTRADICTS,
            }:
                if not edge.relation_confirmed:
                    self._invalid(
                        "supports/contradicts edges must be explicitly human-confirmed",
                        evidence_revision_id=edge.evidence_revision_id,
                        relation=edge.relation.value,
                    )
                if self._is_synthetic(evidence_revision):
                    self._invalid(
                        "Synthetic or simulated evidence cannot form a formal Claim relation",
                        evidence_revision_id=edge.evidence_revision_id,
                        relation=edge.relation.value,
                    )
                if not self._is_current_evidence_revision(evidence_revision):
                    self._invalid(
                        "A new formal Claim relation must use the current Evidence Revision",
                        evidence_revision_id=edge.evidence_revision_id,
                        relation=edge.relation.value,
                    )
                self._assert_formally_traceable(evidence_revision)
                latest_review = self._latest_evidence_review(evidence_revision.id)
                if latest_review is None or latest_review.decision != ReviewDecision.ACCEPT.value:
                    self._invalid(
                        "supports/contradicts edges require the exact Evidence Revision "
                        "to have a latest ACCEPT review",
                        evidence_revision_id=edge.evidence_revision_id,
                        relation=edge.relation.value,
                    )
            revisions[evidence_revision.id] = evidence_revision
        return revisions

    def _add_edges(
        self,
        claim_revision_id: UUID,
        inputs: list[ClaimEvidenceEdgeCreate],
        revisions: dict[UUID, EvidenceRevision],
    ) -> None:
        self.session.add_all(
            [
                ClaimEvidenceEdge(
                    claim_revision_id=claim_revision_id,
                    evidence_unit_id=edge.evidence_id,
                    evidence_revision_id=revisions[edge.evidence_revision_id].id,
                    relation=edge.relation.value,
                    relation_confirmed=edge.relation_confirmed,
                    rationale=edge.rationale,
                    relevance=edge.relevance,
                )
                for edge in inputs
            ]
        )

    def _assert_claim_is_acceptable(self, revision: ClaimRevision) -> dict[str, str]:
        formal_edges = self.session.scalars(
            select(ClaimEvidenceEdge).where(
                ClaimEvidenceEdge.claim_revision_id == revision.id,
                ClaimEvidenceEdge.relation.in_(
                    (
                        ClaimEvidenceRelation.SUPPORTS.value,
                        ClaimEvidenceRelation.CONTRADICTS.value,
                    )
                ),
                ClaimEvidenceEdge.relation_confirmed.is_(True),
            )
        ).all()
        if not any(edge.relation == ClaimEvidenceRelation.SUPPORTS.value for edge in formal_edges):
            self._invalid(
                "Accepting a Claim requires at least one human-confirmed supports edge",
                claim_revision_id=revision.id,
            )
        review_snapshot: dict[str, str] = {}
        for edge in formal_edges:
            evidence_revision = self.session.get(EvidenceRevision, edge.evidence_revision_id)
            if evidence_revision is None:
                raise RuntimeError("Claim edge points to a missing Evidence Revision")
            if not self._is_current_evidence_revision(evidence_revision):
                self._invalid(
                    "Accepting a Claim requires the current Evidence Revision",
                    claim_revision_id=revision.id,
                    evidence_revision_id=edge.evidence_revision_id,
                )
            latest_review = self._latest_evidence_review(edge.evidence_revision_id)
            if latest_review is None or latest_review.decision != ReviewDecision.ACCEPT.value:
                self._invalid(
                    "Every confirmed supports/contradicts edge must retain a latest "
                    "ACCEPT Evidence Review",
                    claim_revision_id=revision.id,
                    evidence_revision_id=edge.evidence_revision_id,
                )
            review_snapshot[str(edge.id)] = str(latest_review.id)
        return review_snapshot

    def _claim_record_for_revision(self, revision: ClaimRevision) -> ClaimRecord:
        claim = self.session.get(Claim, revision.claim_id)
        if claim is None:
            raise RuntimeError("Claim revision points to a missing claim")
        edges = (
            self.session.scalars(
                select(ClaimEvidenceEdge)
                .where(ClaimEvidenceEdge.claim_revision_id == revision.id)
                .options(
                    joinedload(ClaimEvidenceEdge.evidence_revision).joinedload(
                        EvidenceRevision.source_revision
                    )
                )
                .order_by(ClaimEvidenceEdge.created_at, ClaimEvidenceEdge.id)
            )
            .unique()
            .all()
        )
        edge_records = tuple(
            ClaimEdgeRecord(
                edge=edge,
                evidence_revision=edge.evidence_revision,
                source_revision=edge.evidence_revision.source_revision,
                latest_evidence_review=self._latest_evidence_review(edge.evidence_revision_id),
            )
            for edge in edges
        )
        latest_review = self.session.scalar(
            select(ClaimReview)
            .where(ClaimReview.claim_revision_id == revision.id)
            .order_by(ClaimReview.created_at.desc(), ClaimReview.id.desc())
            .limit(1)
        )
        latest_revision = self._latest_revision(claim.id)
        is_current = latest_revision.id == revision.id
        revision_status = self._revision_status(latest_review)
        publication_blockers = self._publication_blockers(
            claim=claim,
            revision=revision,
            edges=edge_records,
            latest_review=latest_review,
            is_current=is_current,
        )
        return ClaimRecord(
            claim=claim,
            revision=revision,
            edges=edge_records,
            latest_review=latest_review,
            is_current=is_current,
            revision_status=revision_status,
            publication_blockers=publication_blockers,
        )

    def _latest_revision(self, claim_id: UUID) -> ClaimRevision:
        revision = self.session.scalar(
            select(ClaimRevision)
            .where(ClaimRevision.claim_id == claim_id)
            .order_by(ClaimRevision.revision.desc())
            .limit(1)
        )
        if revision is None:
            raise RuntimeError("Claim has no revision")
        return revision

    def _evidence_revision(
        self,
        evidence_id: UUID,
        evidence_revision_id: UUID,
    ) -> EvidenceRevision:
        revision = self.session.get(EvidenceRevision, evidence_revision_id)
        if revision is None or revision.evidence_unit_id != evidence_id:
            raise NotFoundError("Evidence revision", evidence_revision_id)
        return revision

    def _latest_evidence_review(self, evidence_revision_id: UUID) -> EvidenceReview | None:
        return self.session.scalar(
            select(EvidenceReview)
            .where(EvidenceReview.evidence_revision_id == evidence_revision_id)
            .order_by(EvidenceReview.created_at.desc(), EvidenceReview.id.desc())
            .limit(1)
        )

    def _is_current_evidence_revision(self, revision: EvidenceRevision) -> bool:
        latest_id = self.session.scalar(
            select(EvidenceRevision.id)
            .where(EvidenceRevision.evidence_unit_id == revision.evidence_unit_id)
            .order_by(EvidenceRevision.revision.desc(), EvidenceRevision.id.desc())
            .limit(1)
        )
        return latest_id == revision.id

    def _mark_dependent_reviewed_claims_stale(self, evidence_revision_id: UUID) -> None:
        current_revision_number = (
            select(func.max(ClaimRevision.revision))
            .where(ClaimRevision.claim_id == Claim.id)
            .correlate(Claim)
            .scalar_subquery()
        )
        claims = self.session.scalars(
            select(Claim)
            .join(ClaimRevision, ClaimRevision.claim_id == Claim.id)
            .join(ClaimEvidenceEdge, ClaimEvidenceEdge.claim_revision_id == ClaimRevision.id)
            .where(
                Claim.status == ClaimStatus.REVIEWED.value,
                ClaimRevision.revision == current_revision_number,
                ClaimEvidenceEdge.evidence_revision_id == evidence_revision_id,
                ClaimEvidenceEdge.relation.in_(
                    (
                        ClaimEvidenceRelation.SUPPORTS.value,
                        ClaimEvidenceRelation.CONTRADICTS.value,
                    )
                ),
                ClaimEvidenceEdge.relation_confirmed.is_(True),
            )
            .distinct()
        ).all()
        for claim in claims:
            claim.status = ClaimStatus.STALE.value

    def _assert_formally_traceable(self, revision: EvidenceRevision) -> None:
        verification = revision.provenance.get("verification")
        required_checks = ("verified", "locator_replayable", "source_hash_match")
        if not isinstance(verification, dict) or not all(
            verification.get(check) is True for check in required_checks
        ):
            self._invalid(
                "Formal evidence must pass deterministic locator and source-integrity verification",
                evidence_revision_id=revision.id,
            )

    @staticmethod
    def _revision_status(review: ClaimReview | None) -> ClaimStatus:
        if review is None or review.decision == ReviewDecision.REQUEST_CHANGES.value:
            return ClaimStatus.PROPOSED
        if review.decision == ReviewDecision.ACCEPT.value:
            return ClaimStatus.REVIEWED
        return ClaimStatus.REJECTED

    def _publication_blockers(
        self,
        *,
        claim: Claim,
        revision: ClaimRevision,
        edges: tuple[ClaimEdgeRecord, ...],
        latest_review: ClaimReview | None,
        is_current: bool,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if not is_current:
            blockers.append("NOT_CURRENT_REVISION")
        if is_current and claim.status == ClaimStatus.STALE.value:
            blockers.append("CLAIM_STALE")
        if is_current and claim.status == ClaimStatus.INVALIDATED.value:
            blockers.append("CLAIM_INVALIDATED")
        if latest_review is None or latest_review.decision != ReviewDecision.ACCEPT.value:
            blockers.append("CLAIM_REVISION_NOT_ACCEPTED")
        if revision.counterevidence_status == "NOT_RUN":
            blockers.append("COUNTEREVIDENCE_NOT_RUN")
        formal_edges = [
            edge
            for edge in edges
            if edge.edge.relation
            in (
                ClaimEvidenceRelation.SUPPORTS.value,
                ClaimEvidenceRelation.CONTRADICTS.value,
            )
            and edge.edge.relation_confirmed
        ]
        if not any(
            edge.edge.relation == ClaimEvidenceRelation.SUPPORTS.value for edge in formal_edges
        ):
            blockers.append("NO_CONFIRMED_SUPPORT")
        if any(
            edge.latest_evidence_review is None
            or edge.latest_evidence_review.decision != ReviewDecision.ACCEPT.value
            for edge in formal_edges
        ):
            blockers.append("EVIDENCE_REVIEW_NOT_ACCEPTED")
        return tuple(blockers)

    @classmethod
    def _human_revision_tags(cls, values: list[str]) -> list[str]:
        reserved = {"synthetic-demo", "demo-extractor", "simulation-output"}
        tags: list[str] = []
        for raw in values:
            tag = raw.strip()
            if not tag:
                continue
            if len(tag) > 100:
                cls._invalid("Evidence tags must be 100 characters or fewer", tag=tag[:100])
            if tag.lower().replace("_", "-") in reserved:
                cls._invalid(
                    "Reserved synthetic/simulation tags cannot be attached to human evidence",
                    tag=tag,
                )
            if tag not in tags:
                tags.append(tag)
        if "human-authored" not in tags:
            tags.append("human-authored")
        return tags

    @staticmethod
    def _is_synthetic(revision: EvidenceRevision) -> bool:
        return (
            revision.provenance.get("synthetic_demo") is True
            or revision.provenance.get("simulation_output") is True
        )

    @staticmethod
    def _request_hash(operation: str, content: dict[str, object]) -> str:
        return canonical_json_hash({"operation": operation, "content": content})

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
            code="invalid_claim_evidence",
            message=message,
            status_code=422,
            details={key: str(value) for key, value in details.items()},
        )
