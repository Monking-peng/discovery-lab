# Evaluation and Bad Case Loop

## Why this exists

DiscoveryLab does not treat “the model returned JSON” as a quality signal. Every workflow or prompt change must answer three separate questions:

1. Can the quote be replayed from the immutable source?
2. Did the workflow obey its control boundary when the source contained hostile instructions?
3. Did the product produce a useful, semantically supported finding?

The first vertical slice implements the first two as deterministic release gates. Semantic quality belongs to the next Claim/Review slice and is never silently inferred from citation validity.

## Executable gate

Run:

```powershell
.\scripts\eval.ps1
```

Inputs live in `evals/golden/source_to_evidence.json`. The runner executes the same parser, extractor, LangGraph and citation verifier used by the application, then writes a versioned report to `.cache/evals/source-to-evidence.json`.

Current metrics:

- `citation_integrity_rate`: verified quote, source hash and locator checks divided by all citation checks.
- `locator_replay_rate`: locators that deterministically resolve against original bytes divided by all checks.
- Case assertions for required quotes, CSV logical rows, cross-row account identity and prompt-injection isolation.
- Explicit `skipped` results for cases whose product layer is not implemented. A skipped case is never counted as passed.

The full repository check invokes this evaluation after tests. Any failed case returns a non-zero process exit code and blocks the handoff.

## Bad Case lifecycle

```text
production/demo failure
→ safe Run + failed Step recorded
→ minimal reproducible fixture
→ root-cause category
→ deterministic regression test
→ Golden case when it represents durable behavior
→ recovery verified against the original workflow
```

Each Bad Case record contains the symptom, safe public error code, failed stage, root cause, resolution, regression test and recovery status. The first real record is `evals/bad-cases/csv-trailing-blank-line.json`: a trailing blank spreadsheet row initially failed parsing, was preserved as a failed Run, then recovered after a narrowly scoped parser fix.

## Promotion rules

- Parser, prompt, model or context-budget changes alter the versioned ingestion profile and therefore the Run input hash.
- A new profile never reuses a previous successful Run result, but it can reuse immutable parsed segments only after exact drift checks.
- Hallucinated segments, fabricated quotes, duplicate draft identities and citation mismatches fail closed with zero Evidence rows persisted.
- Provider errors and credentials use safe error codes; provider response bodies, source text and secrets never enter API errors.
- Citation verification explicitly records `semantic_support_checked=false`. Human review and later semantic evaluators remain separate gates.
