"""Deterministic parsers and replay helpers for MVP source formats."""

from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import PurePath
from typing import Protocol

from .hashing import canonical_json_bytes, sha256_bytes, sha256_text, stable_id
from .models import CsvLocator, Locator, PdfLocator, Segment, SourceKind, TextLocator


class ParseError(ValueError):
    pass


class UnsupportedSourceError(ParseError):
    pass


class LocatorReplayError(ValueError):
    pass


class SourceParser(Protocol):
    def parse(self, *, source_revision_id: str, content: bytes) -> tuple[Segment, ...]: ...


def _decode_utf8(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ParseError("MVP text and CSV sources must be UTF-8 encoded") from exc


def _trimmed_span(value: str, base: int) -> tuple[int, int, str] | None:
    left = 0
    right = len(value)
    while left < right and value[left].isspace():
        left += 1
    while right > left and value[right - 1].isspace():
        right -= 1
    if left == right:
        return None
    return base + left, base + right, value[left:right]


class TextParser:
    """Parse text/Markdown into exact character-offset blocks."""

    _BLOCK_SEPARATOR = re.compile(r"(?:\r?\n[ \t]*){2,}")

    def __init__(self, source_kind: SourceKind = SourceKind.TEXT) -> None:
        if source_kind not in (SourceKind.TEXT, SourceKind.MARKDOWN):
            raise ValueError("TextParser supports only text and markdown")
        self.source_kind = source_kind

    def parse(self, *, source_revision_id: str, content: bytes) -> tuple[Segment, ...]:
        text = _decode_utf8(content)
        source_hash = sha256_bytes(content)
        spans: list[tuple[int, int, str]] = []
        cursor = 0
        for match in self._BLOCK_SEPARATOR.finditer(text):
            span = _trimmed_span(text[cursor : match.start()], cursor)
            if span is not None:
                spans.append(span)
            cursor = match.end()
        final = _trimmed_span(text[cursor:], cursor)
        if final is not None:
            spans.append(final)

        segments: list[Segment] = []
        for index, (start, end, block) in enumerate(spans, start=1):
            segment_id = stable_id("seg", source_revision_id, source_hash, str(start), str(end))
            locator = TextLocator(
                source_revision_id=source_revision_id,
                segment_id=segment_id,
                source_sha256=source_hash,
                char_start=start,
                char_end=end,
                quote_sha256=sha256_text(block),
            )
            segments.append(
                Segment(
                    segment_id=segment_id,
                    source_revision_id=source_revision_id,
                    source_kind=self.source_kind,
                    source_sha256=source_hash,
                    text=block,
                    text_sha256=sha256_text(block),
                    locator=locator,
                    metadata={"block_number": index},
                )
            )
        return tuple(segments)


def _render_csv_row(headers: Sequence[str], row: Sequence[str]) -> str:
    # JSON is unambiguous and remains data even if a cell contains prompt-like text.
    return json.dumps(
        dict(zip(headers, row, strict=True)),
        ensure_ascii=False,
        separators=(",", ":"),
    )


class CsvParser:
    def parse(self, *, source_revision_id: str, content: bytes) -> tuple[Segment, ...]:
        text = _decode_utf8(content)
        source_hash = sha256_bytes(content)
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        try:
            headers = next(reader)
        except StopIteration:
            return ()
        except csv.Error as exc:
            raise ParseError(f"invalid CSV header: {exc}") from exc

        headers = [header.strip() for header in headers]
        if not headers or any(not header for header in headers):
            raise ParseError("CSV requires non-empty column names")
        if len(headers) != len(set(headers)):
            raise ParseError("CSV requires unique column names for reliable provenance")

        duplicate_counts: defaultdict[str, int] = defaultdict(int)
        segments: list[Segment] = []
        try:
            row_number = 0
            for row in reader:
                # Spreadsheet exports commonly leave blank physical rows. They carry no
                # evidence, so omit them without weakening strict column validation.
                if not row or all(not cell.strip() for cell in row):
                    continue
                row_number += 1
                if len(row) != len(headers):
                    raise ParseError(
                        f"CSV row {row_number} has {len(row)} cells; expected {len(headers)}"
                    )
                row_payload = dict(zip(headers, row, strict=True))
                row_hash = sha256_bytes(canonical_json_bytes(row_payload))
                stable_row_id = f"row_{row_hash[:24]}"
                duplicate_ordinal = duplicate_counts[stable_row_id]
                duplicate_counts[stable_row_id] += 1
                rendered = _render_csv_row(headers, row)
                segment_id = stable_id(
                    "seg",
                    source_revision_id,
                    stable_row_id,
                    str(duplicate_ordinal),
                )
                locator = CsvLocator(
                    source_revision_id=source_revision_id,
                    segment_id=segment_id,
                    source_sha256=source_hash,
                    stable_row_id=stable_row_id,
                    row_number=row_number,
                    columns=tuple(headers),
                    row_sha256=row_hash,
                    rendered_char_start=0,
                    rendered_char_end=len(rendered),
                    quote_sha256=sha256_text(rendered),
                )
                segments.append(
                    Segment(
                        segment_id=segment_id,
                        source_revision_id=source_revision_id,
                        source_kind=SourceKind.CSV,
                        source_sha256=source_hash,
                        text=rendered,
                        text_sha256=sha256_text(rendered),
                        locator=locator,
                        metadata={
                            "row_number": row_number,
                            "stable_row_id": stable_row_id,
                            "duplicate_ordinal": duplicate_ordinal,
                        },
                    )
                )
        except csv.Error as exc:
            raise ParseError(f"invalid CSV: {exc}") from exc
        return tuple(segments)


class PdfParser:
    """Extract one replayable text segment per non-empty PDF page with PyMuPDF."""

    def parse(self, *, source_revision_id: str, content: bytes) -> tuple[Segment, ...]:
        try:
            import fitz  # type: ignore[import-untyped]  # PyMuPDF imports as fitz
        except ImportError as exc:  # pragma: no cover - dependency error is environment-specific
            raise UnsupportedSourceError("PDF parsing requires the PyMuPDF package") from exc

        source_hash = sha256_bytes(content)
        segments: list[Segment] = []
        try:
            document = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:
            raise ParseError("invalid or unreadable PDF") from exc
        try:
            for page_index, page in enumerate(document):
                page_text = page.get_text("text", sort=True)
                span = _trimmed_span(page_text, 0)
                if span is None:
                    continue
                start, end, quote = span
                page_hash = sha256_text(page_text)
                page_number = page_index + 1
                segment_id = stable_id(
                    "seg", source_revision_id, source_hash, "page", str(page_number)
                )
                locator = PdfLocator(
                    source_revision_id=source_revision_id,
                    segment_id=segment_id,
                    source_sha256=source_hash,
                    page_number=page_number,
                    page_char_start=start,
                    page_char_end=end,
                    page_sha256=page_hash,
                    quote_sha256=sha256_text(quote),
                )
                segments.append(
                    Segment(
                        segment_id=segment_id,
                        source_revision_id=source_revision_id,
                        source_kind=SourceKind.PDF,
                        source_sha256=source_hash,
                        text=quote,
                        text_sha256=sha256_text(quote),
                        locator=locator,
                        metadata={"page_number": page_number},
                    )
                )
        finally:
            document.close()
        return tuple(segments)


def parser_for(*, media_type: str | None = None, filename: str | None = None) -> SourceParser:
    media = (media_type or "").split(";", 1)[0].strip().lower()
    suffix = PurePath(filename or "").suffix.lower()
    if media == "application/pdf" or suffix == ".pdf":
        return PdfParser()
    if media in ("text/csv", "application/csv") or suffix == ".csv":
        return CsvParser()
    if media in ("text/markdown", "text/x-markdown") or suffix in (".md", ".markdown"):
        return TextParser(SourceKind.MARKDOWN)
    if media.startswith("text/") or suffix in (".txt", ""):
        return TextParser(SourceKind.TEXT)
    raise UnsupportedSourceError(
        f"unsupported source type: media_type={media_type!r}, file={filename!r}"
    )


def parse_source(
    *,
    source_revision_id: str,
    content: bytes,
    media_type: str | None = None,
    filename: str | None = None,
) -> tuple[Segment, ...]:
    return parser_for(media_type=media_type, filename=filename).parse(
        source_revision_id=source_revision_id,
        content=content,
    )


def narrow_locator(segment: Segment, quote: str, quote_start: int) -> Locator:
    """Create a smaller locator, accepting only an exact claimed span."""

    if quote_start < 0 or segment.text[quote_start : quote_start + len(quote)] != quote:
        raise LocatorReplayError("quote and quote_start do not identify an exact segment span")
    quote_hash = sha256_text(quote)
    locator = segment.locator
    if isinstance(locator, TextLocator):
        return locator.model_copy(
            update={
                "char_start": locator.char_start + quote_start,
                "char_end": locator.char_start + quote_start + len(quote),
                "quote_sha256": quote_hash,
            }
        )
    if isinstance(locator, CsvLocator):
        return locator.model_copy(
            update={
                "rendered_char_start": quote_start,
                "rendered_char_end": quote_start + len(quote),
                "quote_sha256": quote_hash,
            }
        )
    if isinstance(locator, PdfLocator):
        return locator.model_copy(
            update={
                "page_char_start": locator.page_char_start + quote_start,
                "page_char_end": locator.page_char_start + quote_start + len(quote),
                "quote_sha256": quote_hash,
            }
        )
    raise TypeError(f"unknown locator type: {type(locator)!r}")


def replay_locator(locator: Locator, source_bytes: bytes) -> str:
    """Resolve a locator against original bytes and verify every stored hash."""

    if sha256_bytes(source_bytes) != locator.source_sha256:
        raise LocatorReplayError("source content hash mismatch")

    if isinstance(locator, TextLocator):
        text = _decode_utf8(source_bytes)
        quote = text[locator.char_start : locator.char_end]
    elif isinstance(locator, CsvLocator):
        segments = CsvParser().parse(
            source_revision_id=locator.source_revision_id,
            content=source_bytes,
        )
        matches = [segment for segment in segments if segment.segment_id == locator.segment_id]
        if len(matches) != 1:
            raise LocatorReplayError("CSV stable row could not be resolved uniquely")
        segment = matches[0]
        parsed = segment.locator
        if not isinstance(parsed, CsvLocator) or parsed.row_sha256 != locator.row_sha256:
            raise LocatorReplayError("CSV row hash mismatch")
        if parsed.stable_row_id != locator.stable_row_id or parsed.columns != locator.columns:
            raise LocatorReplayError("CSV row identity or columns mismatch")
        quote = segment.text[locator.rendered_char_start : locator.rendered_char_end]
    elif isinstance(locator, PdfLocator):
        segments = PdfParser().parse(
            source_revision_id=locator.source_revision_id,
            content=source_bytes,
        )
        matches = [segment for segment in segments if segment.segment_id == locator.segment_id]
        if len(matches) != 1:
            raise LocatorReplayError("PDF page segment could not be resolved uniquely")
        segment = matches[0]
        parsed = segment.locator
        if not isinstance(parsed, PdfLocator) or parsed.page_sha256 != locator.page_sha256:
            raise LocatorReplayError("PDF page hash mismatch")
        relative_start = locator.page_char_start - parsed.page_char_start
        relative_end = locator.page_char_end - parsed.page_char_start
        quote = segment.text[relative_start:relative_end]
    else:  # pragma: no cover - discriminated schema makes this unreachable
        raise TypeError(f"unknown locator type: {type(locator)!r}")

    if sha256_text(quote) != locator.quote_sha256:
        raise LocatorReplayError("replayed quote hash mismatch")
    return quote
