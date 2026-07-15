import { describe, expect, it } from "vitest";

import { deriveInsights } from "../lib/insights";
import { makeEvidence } from "./evidence-fixture";

describe("deriveInsights", () => {
  it("returns an explicit, non-persisted empty preview", () => {
    const result = deriveInsights([]);

    expect(result).toMatchObject({
      persisted: false,
      generatedBy: "deterministic-client-projection",
      inputEvidenceCount: 0,
      eligibleEvidenceCount: 0,
      reviewedEvidenceCount: 0,
      claims: [],
      opportunities: [],
    });
    expect(result.gaps).toEqual([{ code: "no_evidence", severity: "blocking" }]);
  });

  it("never turns synthetic demo evidence into a claim", () => {
    const synthetic = makeEvidence({
      id: "synthetic-1",
      revisionId: "synthetic-1-rev-1",
      syntheticDemo: true,
    });

    const result = deriveInsights([synthetic]);

    expect(result.inputEvidenceCount).toBe(1);
    expect(result.eligibleEvidenceCount).toBe(0);
    expect(result.excludedSyntheticCount).toBe(1);
    expect(result.claims).toEqual([]);
    expect(result.opportunities).toEqual([]);
    expect(result.gaps).toContainEqual({
      code: "synthetic_evidence_excluded",
      severity: "info",
      count: 1,
    });
  });

  it("excludes rejected, stale, and untraceable evidence with separate counts", () => {
    const rejected = makeEvidence({ id: "rejected", reviewStatus: "rejected" });
    const stale = makeEvidence({ id: "stale", reviewStatus: "stale" });
    const missingEvidenceRevision = makeEvidence({
      id: "missing-evidence-revision",
      revisionId: undefined,
    });
    const missingSourceRevision = makeEvidence({
      id: "missing-source-revision",
      sourceRevisionId: undefined,
    });
    const missingQuote = makeEvidence({ id: "missing-quote", quote: "   " });

    const result = deriveInsights([
      rejected,
      stale,
      missingEvidenceRevision,
      missingSourceRevision,
      missingQuote,
    ]);

    expect(result).toMatchObject({
      inputEvidenceCount: 5,
      eligibleEvidenceCount: 0,
      excludedSyntheticCount: 0,
      excludedRejectedOrStaleCount: 2,
      excludedUntraceableCount: 3,
      reviewedEvidenceCount: 0,
      claims: [],
    });
    expect(result.gaps).toEqual(
      expect.arrayContaining([
        { code: "untraceable_evidence_excluded", severity: "blocking", count: 3 },
        { code: "rejected_or_stale_evidence_excluded", severity: "info", count: 2 },
      ]),
    );
  });

  it("binds revisions without treating Evidence metadata as a Claim relationship", () => {
    const support = makeEvidence({
      id: "risk-support",
      revisionId: "risk-support-rev-4",
      sourceId: "interview-a",
      sourceRevisionId: "interview-a-rev-2",
      title: "Risk escalation is too late",
      quote: "The team learns about churn risk only after the SLA is breached.",
      interpretation: "Teams need earlier risk escalation.",
      confidence: 0.92,
      reviewStatus: "approved",
      relationship: "supports",
      tags: ["risk escalation"],
    });
    const challenge = makeEvidence({
      id: "risk-challenge",
      revisionId: "risk-challenge-rev-3",
      sourceId: "interview-b",
      sourceRevisionId: "interview-b-rev-8",
      kind: "counterevidence",
      title: "Risk escalation can create noise",
      quote: "More alerts would make prioritization harder for our team.",
      interpretation: "Risk alerts can increase triage noise.",
      confidence: 0.8,
      reviewStatus: "reviewed",
      relationship: "challenges",
      tags: ["risk escalation"],
    });

    const result = deriveInsights([challenge, support]);
    const claim = result.claims[0];

    expect(result.eligibleEvidenceCount).toBe(2);
    expect(result.reviewedEvidenceCount).toBe(2);
    expect(result.claims).toHaveLength(1);
    expect(claim.persisted).toBe(false);
    expect(claim.statement).toBe("Teams need earlier risk escalation.");
    expect(claim.basisEvidenceId).toBe("risk-support");
    expect(claim.edges).toEqual([
      expect.objectContaining({
        evidenceId: "risk-support",
        evidenceRevisionId: "risk-support-rev-4",
        sourceId: "interview-a",
        sourceRevisionId: "interview-a-rev-2",
        quote: support.quote,
        relation: "supports",
        relationOrigin: "derived-anchor",
      }),
      expect.objectContaining({
        evidenceId: "risk-challenge",
        evidenceRevisionId: "risk-challenge-rev-3",
        sourceId: "interview-b",
        sourceRevisionId: "interview-b-rev-8",
        quote: challenge.quote,
        relation: "contextualizes",
        relationOrigin: "unverified-context",
      }),
    ]);
    expect(claim.strength).toMatchObject({
      evidenceCount: 2,
      supportingCount: 1,
      challengingCount: 0,
      contextualCount: 1,
      distinctSourceCount: 2,
      reviewedCount: 2,
    });
    expect(claim.gaps).toEqual(
      expect.arrayContaining([
        { code: "semantic_support_unverified", severity: "warning" },
        { code: "cohort_coverage_unavailable", severity: "info" },
        { code: "insufficient_support", severity: "blocking", count: 1 },
        { code: "counterevidence_missing", severity: "warning" },
      ]),
    );
    expect(result.opportunities).toEqual([
      expect.objectContaining({
        persisted: false,
        claimId: claim.id,
        problemStatement: claim.statement,
        evidenceCount: 2,
        readiness: "needs_evidence",
        nextStep: "collect_supporting_evidence",
      }),
    ]);
  });

  it("is deterministic across runs and input ordering without mutating evidence", () => {
    const first = makeEvidence({
      id: "routing-a",
      title: "Classification and routing",
      tags: ["routing"],
      confidence: 0.75,
    });
    const second = makeEvidence({
      id: "routing-b",
      title: "Routing still requires human context",
      tags: ["routing"],
      confidence: 0.81,
      reviewStatus: "pending",
      relationship: "neutral",
    });
    const before = structuredClone([first, second]);

    const forward = deriveInsights([first, second]);
    const repeated = deriveInsights([first, second]);
    const reversed = deriveInsights([second, first]);

    expect(repeated).toEqual(forward);
    expect(reversed).toEqual(forward);
    expect([first, second]).toEqual(before);
    expect(forward.claims[0].id).toMatch(/^claim-preview-classification-routing-/);
    expect(forward.opportunities[0].id).toMatch(
      /^opportunity-preview-classification-routing-/,
    );
  });

  it("flags eligible but entirely unreviewed evidence", () => {
    const pending = makeEvidence({
      id: "pending",
      reviewStatus: "pending",
      tags: ["onboarding"],
    });

    const result = deriveInsights([pending]);

    expect(result.eligibleEvidenceCount).toBe(1);
    expect(result.reviewedEvidenceCount).toBe(0);
    expect(result.gaps).toEqual(
      expect.arrayContaining([
        { code: "no_reviewed_evidence", severity: "warning" },
        { code: "cohort_coverage_unavailable", severity: "info" },
      ]),
    );
    expect(result.claims[0].gaps).toContainEqual({
      code: "review_required",
      severity: "warning",
      count: 1,
    });
  });
});
