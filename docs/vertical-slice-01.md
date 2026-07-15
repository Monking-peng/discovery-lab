# Vertical Slice 01 — Source to Evidence

## Outcome

A reviewer can create a Study, upload a supported source, process it, inspect proposed evidence, and prove that every quote resolves to the exact immutable source location.

This slice is complete only when the real UI, API, PostgreSQL, blob storage, parser, extractor, verifier, and tests work together. A static mock is not completion.

## Supported inputs

| Type | Locator contract |
| --- | --- |
| TXT / Markdown | source revision + UTF-8 start/end offsets + quote hash |
| CSV | source revision + stable row ID + selected columns + row hash |
| PDF | source revision + one-based page number + quote + page text hash |

The original file is stored at a content-addressed path. Uploading identical bytes creates a new logical source only when requested, but it never duplicates or mutates the blob.

## API contract

```text
GET  /health
POST /v1/studies
GET  /v1/studies
POST /v1/studies/{study_id}/sources
GET  /v1/studies/{study_id}/sources
GET  /v1/studies/{study_id}/runs
POST /v1/sources/{source_id}:process
GET  /v1/studies/{study_id}/evidence
GET  /v1/evidence/{evidence_id}/context
```

Uploads return a Source and immutable Source Revision before processing begins. Processing creates a Run and Step Attempts. Evidence responses keep these fields separate:

```text
quote          exact source material
observation    what is directly observable
interpretation optional product meaning
inference      optional claim that still requires validation
```

## Extraction modes

- `demo`: deterministic, offline, and visibly labelled `synthetic_demo`; it exists so the repository runs without a paid key.
- `openai`: Responses API with a strict structured-output schema. The provider and model live in a versioned model profile and environment configuration, never inside source text.

No output from either mode is approved evidence. Every result starts as `proposed` and retains producer, prompt/schema version, run step, source revision, and locator.

## Workflow boundary

The first graph is intentionally small:

```text
register immutable source
→ parse to segments and locators
→ extract evidence drafts
→ verify quote and locator deterministically
→ persist proposed revisions
→ wait for review
```

LangGraph stores only small typed state and execution-scoped artifact references. After all citations pass, the application transactionally persists typed segments, evidence revisions, verification checks and artifact hashes to PostgreSQL; execution-scoped `memory://` references are never presented as durable artifacts. Source text is untrusted data and cannot alter the graph, prompt policy, or tool permissions.

## UI acceptance

- Upload accepts drag/drop and keyboard file selection.
- Processing and error states are visible per source.
- Evidence list distinguishes quote, observation, and interpretation.
- Selecting evidence shows source name, revision, hash, producer, review state, and locator.
- Context view highlights or identifies the exact TXT range, CSV row, or PDF page.
- Built-in preview data is labelled `Demo preview` and never presented as a live API result.
- Run timeline shows deterministic versus model steps without exposing hidden chain-of-thought.

## Test gate

- Content hashes are stable and blob writes are idempotent.
- All Golden locator fixtures resolve exactly.
- Malformed and unsupported files fail safely.
- Prompt-injection text remains ordinary segment content.
- Cross-study source/evidence lookup is rejected at the application boundary.
- Invalid or hallucinated quote locations cannot be persisted as verified evidence.
- API and UI tests pass with no model API key.
