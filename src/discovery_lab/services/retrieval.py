from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from discovery_lab.api.errors import ConflictError, NotFoundError
from discovery_lab.db.models import (
    ContextManifest,
    ContextManifestItem,
    EvidenceReview,
    EvidenceRevision,
    EvidenceSearchProjection,
    EvidenceUnit,
    Segment,
    Source,
    SourceRevision,
    Study,
)
from discovery_lab.domain.enums import RetrievalPurpose, ReviewDecision
from discovery_lab.domain.retrieval_schemas import (
    ContextManifestItemRead,
    ContextManifestRead,
    EvidenceReviewSnapshotRead,
    EvidenceSnapshotRead,
    RetrievalCreate,
)
from discovery_lab.services.evidence_integrity import (
    evidence_content_hash,
    parse_locator,
    relative_quote_span,
)
from discovery_lab.services.hashing import canonical_json_hash, sha256_text

PROFILE_NAME = "reviewed-evidence-hybrid"
PROFILE_VERSION = "1.0.0"
LEXICAL_ALGORITHM = "bm25-local-v1"
VECTOR_ALGORITHM = "deterministic-feature-hashing-cosine-v1"
VECTOR_ALGORITHM_DESCRIPTION = (
    "A deterministic local token feature hash, not a trained semantic embedding model."
)
FUSION_ALGORITHM = "weighted-reciprocal-rank-fusion-v1"
QUERY_HANDLING = "untrusted_data_only"
VECTOR_DIMENSIONS = 256
RRF_K = 60
MIN_LOCAL_VECTOR_RELEVANCE = 0.35

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+(?:[-_][a-zA-Z0-9]+)*|[\u3400-\u9fff]")


@dataclass(frozen=True, slots=True)
class EligibleEvidence:
    evidence_unit: EvidenceUnit
    revision: EvidenceRevision
    segment: Segment
    source_revision: SourceRevision
    source: Source
    review: EvidenceReview
    projection_text: str
    lexical_terms: tuple[str, ...]
    embedding: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class RankedEvidence:
    candidate: EligibleEvidence
    lexical_score: float
    vector_score: float
    lexical_rank: int
    vector_rank: int
    hybrid_score: float


class RetrievalService:
    """Create replayable retrieval manifests over formal Evidence Revisions only.

    Query and evidence strings are always treated as untrusted data. This service
    has no model, agent, tool-call, templating, or dynamic-SQL execution path.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_context_manifest(
        self,
        study_id: UUID,
        payload: RetrievalCreate,
    ) -> ContextManifest:
        if self.session.get(Study, study_id) is None:
            raise NotFoundError("study", study_id)

        request_hash = canonical_json_hash(
            {
                "operation": "create_context_manifest",
                "study_id": str(study_id),
                "payload": payload.model_dump(mode="json"),
            }
        )
        existing = self._manifest_by_request_id(payload.client_request_id)
        if existing is not None:
            self._assert_idempotent(existing.request_hash, request_hash)
            return existing

        candidates = self._eligible_evidence(study_id)
        self._rebuild_projections(study_id, candidates)
        ranked = self._rank(payload.query, candidates)[: payload.limit]
        now = datetime.now(UTC)

        frozen_items = [self._frozen_item_payload(record) for record in ranked]
        manifest_content = {
            "schema_version": "context-manifest.v1",
            "study_id": str(study_id),
            "query": payload.query,
            "purpose": payload.purpose.value,
            "result_limit": payload.limit,
            "profile_name": PROFILE_NAME,
            "profile_version": PROFILE_VERSION,
            "lexical_algorithm": LEXICAL_ALGORITHM,
            "vector_algorithm": VECTOR_ALGORITHM,
            "fusion_algorithm": FUSION_ALGORITHM,
            "query_handling": QUERY_HANDLING,
            "items": frozen_items,
        }
        manifest = ContextManifest(
            study_id=study_id,
            query=payload.query,
            purpose=payload.purpose.value,
            result_limit=payload.limit,
            profile_name=PROFILE_NAME,
            profile_version=PROFILE_VERSION,
            lexical_algorithm=LEXICAL_ALGORITHM,
            vector_algorithm=VECTOR_ALGORITHM,
            fusion_algorithm=FUSION_ALGORITHM,
            query_handling=QUERY_HANDLING,
            content_hash=canonical_json_hash(manifest_content),
            client_request_id=payload.client_request_id,
            request_hash=request_hash,
            created_at=now,
        )
        for ordinal, (record, item_payload) in enumerate(
            zip(ranked, frozen_items, strict=True), start=1
        ):
            candidate = record.candidate
            manifest.items.append(
                ContextManifestItem(
                    ordinal=ordinal,
                    evidence_unit_id=candidate.evidence_unit.id,
                    evidence_revision_id=candidate.revision.id,
                    source_id=candidate.source.id,
                    source_revision_id=candidate.source_revision.id,
                    evidence_review_id=candidate.review.id,
                    evidence_content_hash=candidate.revision.content_hash,
                    source_content_hash=candidate.source_revision.content_hash,
                    context_url=item_payload["context_url"],
                    source_name=candidate.source.display_name,
                    evidence_snapshot=item_payload["evidence"],
                    review_snapshot=item_payload["review"],
                    lexical_score=record.lexical_score,
                    vector_score=record.vector_score,
                    hybrid_score=record.hybrid_score,
                    lexical_rank=record.lexical_rank,
                    vector_rank=record.vector_rank,
                    created_at=now,
                )
            )
        self.session.add(manifest)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            concurrent = self._manifest_by_request_id(payload.client_request_id)
            if concurrent is None:
                raise
            self._assert_idempotent(concurrent.request_hash, request_hash)
            return concurrent
        return self.get_context_manifest(manifest.id)

    def get_context_manifest(self, manifest_id: UUID) -> ContextManifest:
        manifest = self.session.scalar(
            select(ContextManifest)
            .options(selectinload(ContextManifest.items))
            .where(ContextManifest.id == manifest_id)
        )
        if manifest is None:
            raise NotFoundError("context_manifest", manifest_id)
        return manifest

    def _manifest_by_request_id(self, client_request_id: str) -> ContextManifest | None:
        return self.session.scalar(
            select(ContextManifest)
            .options(selectinload(ContextManifest.items))
            .where(ContextManifest.client_request_id == client_request_id)
        )

    def _eligible_evidence(self, study_id: UUID) -> list[EligibleEvidence]:
        latest_revision = (
            select(func.max(EvidenceRevision.revision))
            .where(EvidenceRevision.evidence_unit_id == EvidenceUnit.id)
            .correlate(EvidenceUnit)
            .scalar_subquery()
        )
        rows = self.session.execute(
            select(EvidenceUnit, EvidenceRevision, Segment, SourceRevision, Source)
            .join(
                EvidenceRevision,
                EvidenceRevision.evidence_unit_id == EvidenceUnit.id,
            )
            .join(Segment, Segment.id == EvidenceRevision.segment_id)
            .join(SourceRevision, SourceRevision.id == EvidenceRevision.source_revision_id)
            .join(Source, Source.id == SourceRevision.source_id)
            .where(
                EvidenceUnit.study_id == study_id,
                EvidenceRevision.revision == latest_revision,
            )
            .order_by(EvidenceRevision.id)
        ).all()

        eligible: list[EligibleEvidence] = []
        for evidence_unit, revision, segment, source_revision, source in rows:
            review = self._latest_review(revision.id)
            if review is None or review.decision != ReviewDecision.ACCEPT.value:
                continue
            if review.evidence_unit_id != evidence_unit.id or not review.reviewer.strip():
                continue
            if self._is_synthetic_or_simulated(revision):
                continue
            if not self._traceability_replays(revision, segment, source_revision):
                continue
            projection_text = self._projection_text(revision)
            terms = tuple(self._tokenize(projection_text))
            eligible.append(
                EligibleEvidence(
                    evidence_unit=evidence_unit,
                    revision=revision,
                    segment=segment,
                    source_revision=source_revision,
                    source=source,
                    review=review,
                    projection_text=projection_text,
                    lexical_terms=terms,
                    embedding=tuple(self._feature_hash_vector(terms)),
                )
            )
        return eligible

    def _rebuild_projections(
        self,
        study_id: UUID,
        candidates: list[EligibleEvidence],
    ) -> None:
        eligible_ids = [candidate.revision.id for candidate in candidates]
        stale_delete = delete(EvidenceSearchProjection).where(
            EvidenceSearchProjection.study_id == study_id
        )
        if eligible_ids:
            stale_delete = stale_delete.where(
                EvidenceSearchProjection.evidence_revision_id.not_in(eligible_ids)
            )
        self.session.execute(stale_delete)

        existing = {
            projection.evidence_revision_id: projection
            for projection in self.session.scalars(
                select(EvidenceSearchProjection).where(
                    EvidenceSearchProjection.study_id == study_id
                )
            )
        }
        now = datetime.now(UTC)
        for candidate in candidates:
            projection = existing.get(candidate.revision.id)
            if projection is None:
                self.session.add(
                    EvidenceSearchProjection(
                        study_id=study_id,
                        evidence_revision_id=candidate.revision.id,
                        projection_text=candidate.projection_text,
                        lexical_terms=list(candidate.lexical_terms),
                        embedding=list(candidate.embedding),
                        algorithm_name=VECTOR_ALGORITHM,
                        algorithm_version=PROFILE_VERSION,
                        evidence_content_hash=candidate.revision.content_hash,
                        updated_at=now,
                    )
                )
                continue
            if (
                projection.evidence_content_hash != candidate.revision.content_hash
                or projection.algorithm_name != VECTOR_ALGORITHM
                or projection.algorithm_version != PROFILE_VERSION
            ):
                projection.projection_text = candidate.projection_text
                projection.lexical_terms = list(candidate.lexical_terms)
                projection.embedding = list(candidate.embedding)
                projection.algorithm_name = VECTOR_ALGORITHM
                projection.algorithm_version = PROFILE_VERSION
                projection.evidence_content_hash = candidate.revision.content_hash
                projection.updated_at = now
        self.session.flush()

    def _rank(
        self,
        query: str,
        candidates: list[EligibleEvidence],
    ) -> list[RankedEvidence]:
        if not candidates:
            return []
        query_terms = tuple(self._tokenize(query))
        query_embedding = self._feature_hash_vector(query_terms)
        lexical_scores = self._bm25_scores(query_terms, candidates)
        vector_scores = self._vector_scores(query_embedding, candidates)
        # Feature hashing is not a semantic model. Fail closed instead of letting
        # RRF assign a positive rank-only score to unrelated documents.
        candidates = [
            candidate
            for candidate in candidates
            if lexical_scores[candidate.revision.id] > 0
            or vector_scores[candidate.revision.id] >= MIN_LOCAL_VECTOR_RELEVANCE
        ]
        if not candidates:
            return []

        lexical_order = sorted(
            candidates,
            key=lambda item: (-lexical_scores[item.revision.id], str(item.revision.id)),
        )
        vector_order = sorted(
            candidates,
            key=lambda item: (-vector_scores[item.revision.id], str(item.revision.id)),
        )
        lexical_ranks = {item.revision.id: rank for rank, item in enumerate(lexical_order, 1)}
        vector_ranks = {item.revision.id: rank for rank, item in enumerate(vector_order, 1)}

        records = []
        for candidate in candidates:
            lexical_rank = lexical_ranks[candidate.revision.id]
            vector_rank = vector_ranks[candidate.revision.id]
            hybrid_score = (0.7 / (RRF_K + lexical_rank)) + (0.3 / (RRF_K + vector_rank))
            records.append(
                RankedEvidence(
                    candidate=candidate,
                    lexical_score=round(lexical_scores[candidate.revision.id], 12),
                    vector_score=round(vector_scores[candidate.revision.id], 12),
                    lexical_rank=lexical_rank,
                    vector_rank=vector_rank,
                    hybrid_score=round(hybrid_score, 12),
                )
            )
        return sorted(
            records,
            key=lambda item: (
                -item.hybrid_score,
                -item.lexical_score,
                str(item.candidate.revision.id),
            ),
        )

    def _vector_scores(
        self,
        query_embedding: list[float],
        candidates: list[EligibleEvidence],
    ) -> dict[UUID, float]:
        if self.session.get_bind().dialect.name == "postgresql":
            return self._postgres_vector_scores(query_embedding, candidates)
        return {
            candidate.revision.id: self._dot(query_embedding, candidate.embedding)
            for candidate in candidates
        }

    def _postgres_vector_scores(
        self,
        query_embedding: list[float],
        candidates: list[EligibleEvidence],
    ) -> dict[UUID, float]:
        # This is the production pgvector path. Values are bound parameters;
        # untrusted query text never becomes SQL.
        vector_literal = "[" + ",".join(f"{value:.12f}" for value in query_embedding) + "]"
        rows = self.session.execute(
            text(
                "SELECT evidence_revision_id, "
                "1 - (embedding <=> CAST(:query_vector AS vector)) AS vector_score "
                "FROM evidence_search_projections "
                "WHERE study_id = :study_id AND algorithm_version = :algorithm_version"
            ),
            {
                "query_vector": vector_literal,
                "study_id": candidates[0].evidence_unit.study_id,
                "algorithm_version": PROFILE_VERSION,
            },
        ).all()
        scores = {
            UUID(str(row.evidence_revision_id)): max(-1.0, min(1.0, float(row.vector_score)))
            for row in rows
        }
        return {candidate.revision.id: scores[candidate.revision.id] for candidate in candidates}

    @staticmethod
    def _bm25_scores(
        query_terms: tuple[str, ...],
        candidates: list[EligibleEvidence],
    ) -> dict[UUID, float]:
        document_count = len(candidates)
        average_length = (
            sum(len(candidate.lexical_terms) for candidate in candidates) / document_count
        ) or 1.0
        document_frequency: Counter[str] = Counter()
        for candidate in candidates:
            document_frequency.update(set(candidate.lexical_terms))

        k1 = 1.5
        b = 0.75
        query_frequency = Counter(query_terms)
        scores: dict[UUID, float] = {}
        for candidate in candidates:
            term_frequency = Counter(candidate.lexical_terms)
            document_length = max(1, len(candidate.lexical_terms))
            score = 0.0
            for term, query_count in query_frequency.items():
                frequency = term_frequency[term]
                if frequency == 0:
                    continue
                inverse_document_frequency = math.log(
                    1
                    + (document_count - document_frequency[term] + 0.5)
                    / (document_frequency[term] + 0.5)
                )
                denominator = frequency + k1 * (1 - b + b * document_length / average_length)
                score += (
                    query_count * inverse_document_frequency * (frequency * (k1 + 1) / denominator)
                )
            scores[candidate.revision.id] = score
        return scores

    @classmethod
    def _feature_hash_vector(cls, terms: tuple[str, ...]) -> list[float]:
        features = list(terms)
        features.extend(f"bigram:{left}|{right}" for left, right in pairwise(terms))
        if not features:
            features = ["empty-input"]
        vector = [0.0] * VECTOR_DIMENSIONS
        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % VECTOR_DIMENSIONS
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector]

    @staticmethod
    def _dot(left: list[float], right: tuple[float, ...]) -> float:
        return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=True))))

    @staticmethod
    def _tokenize(value: str) -> list[str]:
        tokens = [match.group(0).lower() for match in _TOKEN_PATTERN.finditer(value)]
        if not tokens and value:
            return [f"raw:{sha256_text(value)[:16]}"]
        return tokens

    @staticmethod
    def _projection_text(revision: EvidenceRevision) -> str:
        return "\n".join(
            value
            for value in (
                revision.quote,
                revision.observation,
                revision.interpretation,
                revision.inference,
            )
            if value
        )

    @staticmethod
    def _is_synthetic_or_simulated(revision: EvidenceRevision) -> bool:
        return (
            revision.provenance.get("synthetic_demo") is True
            or revision.provenance.get("simulation_output") is True
        )

    @staticmethod
    def _traceability_replays(
        revision: EvidenceRevision,
        segment: Segment,
        source_revision: SourceRevision,
    ) -> bool:
        verification = revision.provenance.get("verification")
        if not isinstance(verification, dict) or not all(
            verification.get(key) is True
            for key in (
                "verified",
                "exact_quote_match",
                "locator_replayable",
                "source_hash_match",
            )
        ):
            return False
        if revision.source_revision_id != segment.source_revision_id:
            return False
        if segment.content_hash != sha256_text(segment.text):
            return False
        try:
            segment_locator = parse_locator(segment.locator)
            evidence_locator = parse_locator(revision.locator)
        except ValueError:
            return False
        relative_span = relative_quote_span(segment_locator, evidence_locator)
        stable_segment_id = segment.provenance.get("stable_segment_id")
        if (
            relative_span is None
            or not isinstance(stable_segment_id, str)
            or evidence_locator.segment_id != stable_segment_id
            or evidence_locator.source_revision_id != str(source_revision.id)
            or evidence_locator.source_sha256 != source_revision.content_hash
            or evidence_locator.quote_sha256 != sha256_text(revision.quote)
        ):
            return False
        quote_start, quote_end = relative_span
        if not (0 <= quote_start <= quote_end <= len(segment.text)):
            return False
        if segment.text[quote_start:quote_end] != revision.quote:
            return False
        confidence = revision.provenance.get("confidence")
        tags = revision.provenance.get("tags")
        extraction_method = revision.provenance.get("extraction_method")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not isinstance(tags, list)
            or not all(isinstance(tag, str) for tag in tags)
            or not isinstance(extraction_method, str)
        ):
            return False
        expected_hash = evidence_content_hash(
            quote=revision.quote,
            observation=revision.observation,
            interpretation=revision.interpretation,
            inference=revision.inference,
            evidence_type=revision.evidence_type,
            locator=revision.locator,
            confidence=float(confidence),
            tags=tags,
            synthetic_demo=False,
            extraction_method=extraction_method,
        )
        return expected_hash == revision.content_hash

    @staticmethod
    def _latest_review_for_snapshot(review: EvidenceReview) -> dict[str, Any]:
        return {
            "decision": review.decision,
            "reviewer": review.reviewer,
            "rationale": review.rationale,
            "created_at": review.created_at.isoformat(),
        }

    @classmethod
    def _frozen_item_payload(cls, record: RankedEvidence) -> dict[str, Any]:
        candidate = record.candidate
        return {
            "evidence_id": str(candidate.evidence_unit.id),
            "evidence_revision_id": str(candidate.revision.id),
            "source_id": str(candidate.source.id),
            "source_revision_id": str(candidate.source_revision.id),
            "evidence_review_id": str(candidate.review.id),
            "evidence_content_hash": candidate.revision.content_hash,
            "source_content_hash": candidate.source_revision.content_hash,
            "context_url": (
                f"/v1/evidence/{candidate.evidence_unit.id}/context"
                f"?evidence_revision_id={candidate.revision.id}"
            ),
            "source_name": candidate.source.display_name,
            "evidence": {
                "evidence_type": candidate.revision.evidence_type,
                "quote": candidate.revision.quote,
                "observation": candidate.revision.observation,
                "interpretation": candidate.revision.interpretation,
                "inference": candidate.revision.inference,
                "locator": candidate.revision.locator,
            },
            "review": cls._latest_review_for_snapshot(candidate.review),
            "lexical_score": record.lexical_score,
            "vector_score": record.vector_score,
            "hybrid_score": record.hybrid_score,
            "lexical_rank": record.lexical_rank,
            "vector_rank": record.vector_rank,
        }

    def _latest_review(self, evidence_revision_id: UUID) -> EvidenceReview | None:
        return self.session.scalar(
            select(EvidenceReview)
            .where(EvidenceReview.evidence_revision_id == evidence_revision_id)
            .order_by(EvidenceReview.created_at.desc(), EvidenceReview.id.desc())
            .limit(1)
        )

    @staticmethod
    def _assert_idempotent(stored_hash: str, request_hash: str) -> None:
        if stored_hash != request_hash:
            raise ConflictError(
                "client_request_id was already used with a different request",
                details={"reason": "idempotency_key_reuse"},
            )


def context_manifest_response(manifest: ContextManifest) -> ContextManifestRead:
    created_at = manifest.created_at
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        created_at = created_at.replace(tzinfo=UTC)
    return ContextManifestRead(
        id=manifest.id,
        context_manifest_id=manifest.id,
        study_id=manifest.study_id,
        query=manifest.query,
        purpose=RetrievalPurpose(manifest.purpose),
        result_limit=manifest.result_limit,
        profile_name=manifest.profile_name,
        profile_version=manifest.profile_version,
        lexical_algorithm=manifest.lexical_algorithm,
        vector_algorithm=manifest.vector_algorithm,
        vector_algorithm_description=VECTOR_ALGORITHM_DESCRIPTION,
        fusion_algorithm=manifest.fusion_algorithm,
        query_handling=manifest.query_handling,
        content_hash=manifest.content_hash,
        client_request_id=manifest.client_request_id,
        created_at=created_at,
        items=[
            ContextManifestItemRead(
                id=item.id,
                rank=item.ordinal,
                evidence_id=item.evidence_unit_id,
                evidence_revision_id=item.evidence_revision_id,
                source_id=item.source_id,
                source_revision_id=item.source_revision_id,
                evidence_review_id=item.evidence_review_id,
                evidence_content_hash=item.evidence_content_hash,
                source_content_hash=item.source_content_hash,
                context_url=item.context_url,
                source_name=item.source_name,
                evidence=EvidenceSnapshotRead.model_validate(item.evidence_snapshot),
                review=EvidenceReviewSnapshotRead.model_validate(item.review_snapshot),
                lexical_score=item.lexical_score,
                vector_score=item.vector_score,
                hybrid_score=item.hybrid_score,
                lexical_rank=item.lexical_rank,
                vector_rank=item.vector_rank,
            )
            for item in manifest.items
        ],
    )
