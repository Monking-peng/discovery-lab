# Vertical Slice 02 — Reviewed Evidence to Claim

## Outcome

A reviewer can take one exact Evidence Revision through an append-only content review, create a versioned Claim whose evidence relationships were explicitly confirmed by a human, review that exact Claim Revision, and replay every pinned source location without silently switching to a newer revision.

This slice is complete only when the database, API, product UI, migration, deterministic evaluation, and browser workflow enforce the same promotion rules. A client-only Claim projection is still useful as a proposal, but it is not a domain fact.

## Trust boundaries

The product keeps four actions separate:

1. A deterministic client projection may group eligible evidence into a Claim proposal.
2. A human may author or review an exact Evidence Revision.
3. A human must explicitly confirm each Claim–Evidence relationship and explain it.
4. A Claim Review judges content; it is not an Approval to publish or call an external tool.

An inferred anchor must never become `supports` merely because a heuristic ranked it first. Until a reviewer confirms the relationship, it remains `contextualizes` (or `insufficient_for`).

## Immutable record chain

```text
Source Revision
→ Segment + Locator
→ Evidence Revision
→ Evidence Review
→ Claim Revision
→ Claim Evidence Edge
→ Claim Review
```

- `EvidenceReview` and `ClaimReview` are append-only and bind one exact revision.
- Editing Claim content creates a new `ClaimRevision`; it never overwrites the prior statement, edge set, or review.
- A `ClaimEvidenceEdge` stores both the stable Evidence identity and the exact Evidence Revision identity. Source identity is resolved and returned by the server, not trusted from a client payload.
- Opening an edge requests its pinned Evidence Revision. The current/latest Evidence list is never used as a substitute.

## Promotion rules

### Evidence

- A provider or deterministic extractor produces a `PROPOSED` Evidence Revision.
- Synthetic demo output cannot receive an `ACCEPT` review.
- A human-authored revision keeps the original immutable quote, locator, segment, and Source Revision; authored interpretation fields create a new Evidence Revision.
- The API derives visible review state from the latest append-only Evidence Review. It does not mutate the Evidence Revision.

### Claim

- A proposed Claim contains at least one exact Evidence Revision edge.
- Pending evidence may only be `contextualizes` or `insufficient_for`.
- `supports` and `contradicts` require an accepted, non-synthetic, replayable Evidence Revision and an explicitly confirmed relationship.
- Every edge requires a rationale.
- A Claim Review can return `ACCEPT`, `REQUEST_CHANGES`, or `REJECT`.
- `ACCEPT` requires at least one confirmed, accepted `supports` edge.
- `counterevidence_status=NOT_RUN` remains an explicit publication blocker. It is never interpreted as “no counterevidence exists.”
- If a reviewed supporting or contradicting Evidence Revision is later rejected or sent back for changes, dependent reviewed Claims become `STALE`; their immutable history remains replayable.

## Concurrency and idempotency

- Create/review requests carry `client_request_id`. Repeating the same request returns the same result; reusing the key for different content fails with a conflict.
- Creating Claim revision `n + 1` requires `base_revision_id` to still be the current revision. A stale editor receives a revision conflict instead of overwriting newer work.
- Cross-Study Evidence IDs, mismatched Evidence/Revision pairs, and any invalid edge fail the entire transaction with zero partial Claim rows.

## API contract

```text
POST /v1/evidence/{evidence_id}/reviews
GET  /v1/studies/{study_id}/claims
POST /v1/studies/{study_id}/claims
GET  /v1/claims/{claim_id}?claim_revision_id={exact_revision_id}
POST /v1/claims/{claim_id}/revisions
POST /v1/claim-revisions/{claim_revision_id}/reviews
```

An evidence-edge response includes:

```text
evidence_id
evidence_revision_id
source_id
source_revision_id
relation
relation_confirmed
rationale
context_url
latest_evidence_review
```

## UI acceptance

- “Saved claims” and “Draft proposals” are visually distinct.
- Saving a proposal requires a relationship choice, rationale, and explicit confirmation per edge.
- Synthetic, rejected, stale, or untraceable Evidence cannot enter the save payload.
- The inspector shows Claim ID, Claim Revision ID, status, counterevidence status, exact Evidence Revision IDs, exact Source Revision IDs, and review history.
- Evidence and Claim review actions bind the exact revision shown on screen and disable duplicate submission.
- A conflict preserves the user’s unsaved work and asks them to refresh or create a new revision.
- English / 简体中文 switching translates product chrome only. Quotes and source material retain their original language.

## Executable release gate

`scripts/eval.ps1` runs both Source→Evidence and Evidence→Claim datasets. The second gate covers:

- accepted support eligibility;
- pending and synthetic support rejection;
- cross-Study and Evidence Revision mismatch rejection;
- explicit counterevidence-not-run publication blocking;
- exact historical Evidence Revision replay.

The API test gate additionally covers append-only reviews, idempotency, transaction rollback, revision conflicts, stale propagation, and old-revision replay after newer revisions exist.

## Intentional next boundary

This slice creates trustworthy Claim facts. Hybrid retrieval, Analyst/Skeptic workflow, persisted Opportunity/Hypothesis, Decision/PRD publication, external write Approval, and tenant-aware MCP remain separate vertical slices and must not be represented as complete until their real data paths and gates exist.
