"""Deterministic citation integrity checks (not semantic truth judgments)."""

from __future__ import annotations

from .hashing import sha256_bytes
from .models import CitationCheck, ExtractionResult, Segment, VerificationResult
from .parsers import LocatorReplayError, replay_locator


class CitationVerifier:
    """Verify exact quote provenance without pretending to assess semantics."""

    def verify(
        self,
        extraction: ExtractionResult,
        segments: tuple[Segment, ...],
        source_bytes: bytes,
    ) -> VerificationResult:
        by_id = {segment.segment_id: segment for segment in segments}
        checks: list[CitationCheck] = []
        source_hash = sha256_bytes(source_bytes)

        for draft in extraction.drafts:
            reasons: list[str] = []
            segment = by_id.get(draft.segment_id)
            source_hash_match = source_hash == draft.locator.source_sha256
            if not source_hash_match:
                reasons.append("source_hash_mismatch")

            exact_quote_match = False
            locator_replayable = False
            if segment is None:
                reasons.append("unknown_segment")
            elif segment.source_revision_id != draft.source_revision_id:
                reasons.append("source_revision_mismatch")
            elif segment.source_sha256 != draft.locator.source_sha256:
                reasons.append("segment_source_hash_mismatch")
            else:
                try:
                    replayed = replay_locator(draft.locator, source_bytes)
                except LocatorReplayError:
                    reasons.append("locator_not_replayable")
                else:
                    locator_replayable = True
                    exact_quote_match = replayed == draft.quote
                    if not exact_quote_match:
                        reasons.append("quote_mismatch")

            verified = (
                segment is not None
                and source_hash_match
                and locator_replayable
                and exact_quote_match
                and not reasons
            )
            checks.append(
                CitationCheck(
                    draft_id=draft.draft_id,
                    verified=verified,
                    exact_quote_match=exact_quote_match,
                    locator_replayable=locator_replayable,
                    source_hash_match=source_hash_match,
                    reasons=tuple(reasons),
                )
            )
        return VerificationResult(checks=tuple(checks))
