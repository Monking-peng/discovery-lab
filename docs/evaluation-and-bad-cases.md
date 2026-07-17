# Evaluation and Bad Case Loop

## Release contract

Discovery Lab does not count “the model returned JSON” as quality. Its executable
release gate checks two different boundaries:

1. **Source → Evidence** re-runs the real parser, deterministic demo extractor,
   LangGraph workflow, and citation verifier against immutable fixtures.
2. **Evidence → Claim** applies the same domain vocabulary used by the product:
   append-only `ReviewDecision` values, exact Evidence Revision identity, and
   `CounterevidenceStatus` values `NOT_RUN`, `SEARCHED_NONE_FOUND`, and `FOUND`.

Run both datasets and strict Bad Case validation with:

```powershell
.\scripts\eval.ps1
```

Reports are written to `.cache/evals/`. The full repository check invokes the
same gate. Any failed assertion or malformed dataset returns a non-zero exit
code. There is no skipped-as-passed path: every declared v2 case has a concrete
evaluator, and the current datasets execute 26 cases (11 Source → Evidence and
15 Evidence → Claim).

## What is covered

The Source → Evidence dataset checks replayable text quotes, stable CSV row
locators, multi-row account identity, an unsupported universal claim, and prompt
injection isolation. Injection text must remain visible as untrusted source data
while staying absent from workflow control state and versioned policy.

The Evidence → Claim dataset checks:

- the latest review must be `ACCEPT`; missing, `REQUEST_CHANGES`, and `REJECT`
  are not acceptance;
- at least one human-confirmed support edge is required;
- synthetic, cross-study, stale, mismatched, citation-invalid,
  locator-invalid, and source-hash-invalid Evidence fails closed;
- multiple independent blockers remain visible instead of collapsing into one;
- `NOT_RUN` means “not evaluated” and always remains a publication blocker;
- an old Evidence Revision replays by exact identity and is never silently
  replaced by the latest revision.

Golden inputs are strict Pydantic contracts with forbidden extra fields and
unique case identifiers. Dataset revisions are included in every report.

## Read-only observability API

`discovery_lab.api.evaluation_routes` exposes two GET-only routes:

- `GET /v1/evaluation/reports/current` executes the repository-owned Golden
  datasets and returns summary counts, every case result, and dataset revisions.
- `GET /v1/evaluation/bad-cases` returns the strict Bad Case Inbox.

Neither endpoint accepts a filesystem path. Evaluation files are resolved from
the application repository root only. The release gate passes only when
`failed == 0`, `skipped == 0`, and `passed == total_cases`.

## Bad Case lifecycle

```text
production/demo failure
→ safe Run + failed Step recorded
→ minimal reproducible fixture
→ strict Bad Case record
→ root-cause category
→ deterministic regression test
→ Golden case when behavior is durable
→ recovery verified against the original workflow
```

Every `evals/bad-cases/*.json` file must match `bad-case.v1`. Extra fields,
unknown stages, path traversal, naive timestamps, duplicate identifiers,
missing fixtures, or missing regression-test files invalidate the whole Inbox.
The API never returns a partially validated list. The first real record,
`csv-trailing-blank-line.json`, documents a spreadsheet export whose trailing
blank row originally broke strict parsing and is now protected by a regression
test.

## Promotion rules

- Parser, prompt, model, or context-budget changes alter the versioned runtime
  profile and therefore the Run input hash.
- A new profile never reuses a previous successful Run result without exact
  drift checks.
- Fabricated quotes, duplicate draft identities, source-hash drift, and locator
  mismatches fail closed with zero Evidence rows persisted.
- Provider errors use safe public codes; raw provider bodies, source text, and
  secrets never enter API errors.
- Citation verification records `semantic_support_checked=false`. Human review
  and Claim policy remain separate gates.
