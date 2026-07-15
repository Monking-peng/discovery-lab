"""Provenance-first ingestion primitives."""

from .blob_store import (
    BlobIntegrityError,
    BlobNotFoundError,
    BlobRef,
    BlobStore,
    LocalBlobStore,
)
from .extractors import DeterministicDemoExtractor, EvidenceExtractor
from .models import (
    CitationCheck,
    CsvLocator,
    EvidenceDraft,
    ExtractionMethod,
    ExtractionResult,
    PdfLocator,
    Segment,
    SourceKind,
    TextLocator,
    VerificationResult,
)
from .parsers import (
    CsvParser,
    LocatorReplayError,
    ParseError,
    PdfParser,
    TextParser,
    UnsupportedSourceError,
    narrow_locator,
    parse_source,
    parser_for,
    replay_locator,
)
from .verification import CitationVerifier

__all__ = [
    "BlobIntegrityError",
    "BlobNotFoundError",
    "BlobRef",
    "BlobStore",
    "CitationCheck",
    "CitationVerifier",
    "CsvLocator",
    "CsvParser",
    "DeterministicDemoExtractor",
    "EvidenceDraft",
    "EvidenceExtractor",
    "ExtractionMethod",
    "ExtractionResult",
    "LocalBlobStore",
    "LocatorReplayError",
    "ParseError",
    "PdfLocator",
    "PdfParser",
    "Segment",
    "SourceKind",
    "TextLocator",
    "TextParser",
    "UnsupportedSourceError",
    "VerificationResult",
    "narrow_locator",
    "parse_source",
    "parser_for",
    "replay_locator",
]
