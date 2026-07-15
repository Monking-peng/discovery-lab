from __future__ import annotations

from discovery_lab.ingestion import CitationVerifier, DeterministicDemoExtractor, TextParser


def test_demo_extractor_is_deterministic_and_unmistakably_synthetic() -> None:
    content = b"Customer cannot find urgent tickets.\n\nEscalation takes twenty minutes."
    segments = TextParser().parse(source_revision_id="rev_1", content=content)
    extractor = DeterministicDemoExtractor()

    first = extractor.extract(segments)
    second = extractor.extract(segments)

    assert first == second
    assert first.synthetic_demo is True
    assert all(draft.synthetic_demo for draft in first.drafts)
    assert all("SYNTHETIC DEMO ONLY" in draft.observation for draft in first.drafts)


def test_citation_verifier_checks_replay_but_not_semantic_truth() -> None:
    content = b"Customer cannot find urgent tickets."
    segments = TextParser().parse(source_revision_id="rev_1", content=content)
    extraction = DeterministicDemoExtractor().extract(segments)

    result = CitationVerifier().verify(extraction, segments, content)

    assert result.all_verified
    assert result.checks[0].semantic_support_checked is False


def test_citation_verifier_rejects_changed_source_bytes() -> None:
    content = b"Customer cannot find urgent tickets."
    segments = TextParser().parse(source_revision_id="rev_1", content=content)
    extraction = DeterministicDemoExtractor().extract(segments)

    result = CitationVerifier().verify(extraction, segments, content + b" changed")

    assert not result.all_verified
    assert result.checks[0].source_hash_match is False
