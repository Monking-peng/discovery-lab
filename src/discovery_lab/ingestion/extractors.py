"""Extractor port plus an explicitly synthetic deterministic demo adapter."""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from .models import EvidenceDraft, ExtractionMethod, ExtractionResult, Segment
from .parsers import narrow_locator


@runtime_checkable
class EvidenceExtractor(Protocol):
    def extract(self, segments: tuple[Segment, ...]) -> ExtractionResult: ...


class DeterministicDemoExtractor:
    """Create predictable fake proposals for UI demos, never production evidence.

    Every result and draft is marked ``synthetic_demo=True``. The generated
    observation intentionally makes no semantic claim beyond the cited text.
    """

    name = "deterministic-demo-extractor"
    version = "1.0.0"

    def __init__(self, *, max_evidence: int = 20, max_quote_chars: int = 320) -> None:
        if max_evidence < 0 or max_quote_chars < 1:
            raise ValueError("max_evidence must be >= 0 and max_quote_chars must be >= 1")
        self.max_evidence = max_evidence
        self.max_quote_chars = max_quote_chars

    def _select_quote(self, text: str) -> str:
        window = text[: self.max_quote_chars]
        if len(text) <= self.max_quote_chars:
            return text
        sentence_end = None
        for match in re.finditer(r"[.!?\u3002\uff01\uff1f](?:\s|$)", window):
            sentence_end = match.start() + 1
        if sentence_end:
            return window[:sentence_end]
        return window.rstrip() or window

    def extract(self, segments: tuple[Segment, ...]) -> ExtractionResult:
        drafts: list[EvidenceDraft] = []
        for segment in segments[: self.max_evidence]:
            if not segment.text:
                continue
            quote = self._select_quote(segment.text)
            locator = narrow_locator(segment, quote, 0)
            drafts.append(
                EvidenceDraft.create(
                    source_revision_id=segment.source_revision_id,
                    segment_id=segment.segment_id,
                    locator=locator,
                    quote=quote,
                    observation=(
                        "SYNTHETIC DEMO ONLY: this proposal records that the quoted "
                        "passage exists in the source; it is not an AI-derived finding."
                    ),
                    interpretation=None,
                    inference=None,
                    confidence=1.0,
                    tags=("synthetic-demo",),
                    extraction_method=ExtractionMethod.DETERMINISTIC_DEMO,
                    synthetic_demo=True,
                )
            )
        return ExtractionResult(
            extractor_name=self.name,
            extractor_version=self.version,
            synthetic_demo=True,
            drafts=tuple(drafts),
            warnings=("SYNTHETIC DEMO OUTPUT: do not publish or count as reviewed evidence.",),
        )
