import type { Claim } from "../lib/api";

export function makeClaim(overrides: Partial<Claim> = {}): Claim {
  const revisionId = overrides.claimRevisionId ?? overrides.revisionId ?? "claim-revision-1";
  return {
    id: "claim-1",
    claimId: "claim-1",
    studyId: "study-1",
    status: "PROPOSED",
    revisionStatus: "PROPOSED",
    isCurrent: true,
    publicationBlockers: ["counterevidence_search_required"],
    revisionId,
    claimRevisionId: revisionId,
    revision: 1,
    topicKey: "onboarding",
    statement: "Users need a clearer onboarding path.",
    summary: null,
    rationale: "The claim groups traceable onboarding observations.",
    confidence: 0.72,
    counterevidenceStatus: "NOT_RUN",
    counterevidenceSummary: null,
    provenance: { producer: "test" },
    contentHash: "claim-content-hash",
    createdAt: "2026-07-16T00:00:00.000Z",
    evidenceEdges: [],
    latestReview: null,
    ...overrides,
  };
}
