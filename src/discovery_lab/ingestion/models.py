"""Versioned, strict schemas for parsed segments and evidence extraction."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .hashing import sha256_text, stable_id


class StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceKind(StrEnum):
    TEXT = "text"
    MARKDOWN = "markdown"
    CSV = "csv"
    PDF = "pdf"


class TextLocator(StrictFrozenModel):
    kind: Literal["text"] = "text"
    source_revision_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    quote_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_span(self) -> TextLocator:
        if self.char_end < self.char_start:
            raise ValueError("char_end must be greater than or equal to char_start")
        return self


class CsvLocator(StrictFrozenModel):
    kind: Literal["csv"] = "csv"
    source_revision_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stable_row_id: str = Field(min_length=1)
    row_number: int = Field(ge=1, description="One-based logical data row, excluding header")
    columns: tuple[str, ...] = Field(min_length=1)
    row_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rendered_char_start: int = Field(default=0, ge=0)
    rendered_char_end: int = Field(ge=0)
    quote_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_span(self) -> CsvLocator:
        if self.rendered_char_end < self.rendered_char_start:
            raise ValueError("rendered_char_end must be >= rendered_char_start")
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("CSV locator columns must be unique")
        return self


class PdfLocator(StrictFrozenModel):
    kind: Literal["pdf"] = "pdf"
    source_revision_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_number: int = Field(ge=1)
    page_char_start: int = Field(default=0, ge=0)
    page_char_end: int = Field(ge=0)
    page_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    quote_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_span(self) -> PdfLocator:
        if self.page_char_end < self.page_char_start:
            raise ValueError("page_char_end must be >= page_char_start")
        return self


Locator = Annotated[TextLocator | CsvLocator | PdfLocator, Field(discriminator="kind")]


class Segment(StrictFrozenModel):
    """A deterministic, replayable slice of one immutable source revision."""

    schema_version: Literal["segment.v1"] = "segment.v1"
    segment_id: str = Field(min_length=1)
    source_revision_id: str = Field(min_length=1)
    source_kind: SourceKind
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    text: str
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator: Locator
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_provenance(self) -> Segment:
        if self.text_sha256 != sha256_text(self.text):
            raise ValueError("text_sha256 does not match segment text")
        if self.locator.segment_id != self.segment_id:
            raise ValueError("locator segment_id does not match segment")
        if self.locator.source_revision_id != self.source_revision_id:
            raise ValueError("locator source_revision_id does not match segment")
        if self.locator.source_sha256 != self.source_sha256:
            raise ValueError("locator source_sha256 does not match segment")
        return self


class ExtractionMethod(StrEnum):
    DETERMINISTIC_DEMO = "deterministic_demo"
    OPENAI_RESPONSES = "openai_responses"


class EvidenceDraft(StrictFrozenModel):
    """Unreviewed evidence proposed by an extractor; never a published fact."""

    schema_version: Literal["evidence-draft.v1"] = "evidence-draft.v1"
    draft_id: str = Field(min_length=1)
    source_revision_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    locator: Locator
    quote: str = Field(min_length=1)
    observation: str = Field(min_length=1)
    interpretation: str | None = None
    inference: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    tags: tuple[str, ...] = ()
    extraction_method: ExtractionMethod
    synthetic_demo: bool = False

    @model_validator(mode="after")
    def validate_citation_identity(self) -> EvidenceDraft:
        if self.locator.source_revision_id != self.source_revision_id:
            raise ValueError("locator source revision does not match evidence draft")
        if self.locator.segment_id != self.segment_id:
            raise ValueError("locator segment does not match evidence draft")
        if self.locator.quote_sha256 != sha256_text(self.quote):
            raise ValueError("locator quote hash does not match evidence quote")
        if (
            self.extraction_method == ExtractionMethod.DETERMINISTIC_DEMO
            and not self.synthetic_demo
        ):
            raise ValueError("deterministic demo evidence must be marked synthetic_demo")
        if self.extraction_method != ExtractionMethod.DETERMINISTIC_DEMO and self.synthetic_demo:
            raise ValueError("only deterministic demo evidence may be marked synthetic_demo")
        return self

    @classmethod
    def create(
        cls,
        *,
        source_revision_id: str,
        segment_id: str,
        locator: Locator,
        quote: str,
        observation: str,
        interpretation: str | None,
        inference: str | None,
        confidence: float,
        tags: tuple[str, ...],
        extraction_method: ExtractionMethod,
        synthetic_demo: bool,
    ) -> EvidenceDraft:
        draft_id = stable_id(
            "evd",
            source_revision_id,
            segment_id,
            locator.quote_sha256,
            observation,
            extraction_method.value,
        )
        return cls(
            draft_id=draft_id,
            source_revision_id=source_revision_id,
            segment_id=segment_id,
            locator=locator,
            quote=quote,
            observation=observation,
            interpretation=interpretation,
            inference=inference,
            confidence=confidence,
            tags=tags,
            extraction_method=extraction_method,
            synthetic_demo=synthetic_demo,
        )


class ExtractionUsage(StrictFrozenModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class ExtractionResult(StrictFrozenModel):
    schema_version: Literal["extraction-result.v1"] = "extraction-result.v1"
    extractor_name: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    prompt_version: str | None = None
    model: str | None = None
    response_id: str | None = None
    synthetic_demo: bool
    drafts: tuple[EvidenceDraft, ...] = ()
    warnings: tuple[str, ...] = ()
    usage: ExtractionUsage | None = None

    @model_validator(mode="after")
    def validate_demo_boundary(self) -> ExtractionResult:
        if any(draft.synthetic_demo != self.synthetic_demo for draft in self.drafts):
            raise ValueError("result and draft synthetic_demo flags must agree")
        return self


class CitationCheck(StrictFrozenModel):
    draft_id: str
    verified: bool
    exact_quote_match: bool
    locator_replayable: bool
    source_hash_match: bool
    semantic_support_checked: Literal[False] = False
    reasons: tuple[str, ...] = ()


class VerificationResult(StrictFrozenModel):
    schema_version: Literal["citation-verification.v1"] = "citation-verification.v1"
    checks: tuple[CitationCheck, ...]

    @property
    def all_verified(self) -> bool:
        return all(check.verified for check in self.checks)
