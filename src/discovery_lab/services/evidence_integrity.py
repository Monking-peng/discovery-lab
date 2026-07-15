from __future__ import annotations

from typing import Any

from discovery_lab.services.hashing import canonical_json_hash


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
