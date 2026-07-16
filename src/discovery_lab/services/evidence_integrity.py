from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from discovery_lab.ingestion.models import CsvLocator, Locator, PdfLocator, TextLocator
from discovery_lab.services.hashing import canonical_json_hash

LOCATOR_ADAPTER: TypeAdapter[Locator] = TypeAdapter(Locator)


def parse_locator(value: dict[str, Any]) -> Locator:
    """Validate persisted locator JSON against the shared discriminated schema."""

    return LOCATOR_ADAPTER.validate_python(value)


def relative_quote_span(
    segment_locator: Locator,
    evidence_locator: Locator,
) -> tuple[int, int] | None:
    """Map a narrowed Evidence locator to offsets inside its parent Segment."""

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


def evidence_content_payload(
    *,
    quote: str,
    observation: str | None,
    interpretation: str | None,
    inference: str | None,
    evidence_type: str,
    locator: dict[str, Any],
    confidence: float,
    tags: list[str],
    synthetic_demo: bool,
    extraction_method: str,
) -> dict[str, Any]:
    """Return the canonical, user-visible evidence payload covered by its hash."""

    return {
        "schema_version": "evidence-revision-content.v1",
        "quote": quote,
        "observation": observation,
        "interpretation": interpretation,
        "inference": inference,
        "evidence_type": evidence_type,
        "locator": locator,
        "confidence": confidence,
        "tags": tags,
        "synthetic_demo": synthetic_demo,
        "extraction_method": extraction_method,
    }


def evidence_content_hash(**payload: Any) -> str:
    return canonical_json_hash(evidence_content_payload(**payload))
