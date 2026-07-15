import type { Evidence } from "../lib/api";

let nextEvidenceId = 1;

export function makeEvidence(overrides: Partial<Evidence> = {}): Evidence {
  const id = overrides.id ?? `evidence-${nextEvidenceId++}`;

  return {
    id,
    revisionId: `${id}-revision-1`,
    revision: 1,
    studyId: "study-1",
    kind: "pain",
    title: `Evidence ${id}`,
    quote: `Exact quote for ${id}`,
    observation: `Observation for ${id}`,
    interpretation: `Interpretation for ${id}`,
    sourceName: `${id}.md`,
    sourceId: `${id}-source`,
    sourceRevisionId: `${id}-source-revision-1`,
    sourceType: "text/markdown",
    locatorLabel: "characters 0-20",
    reviewStatus: "approved",
    confidence: 0.9,
    relationship: "supports",
    tags: ["risk", "workflow"],
    syntheticDemo: false,
    createdAt: "2026-07-15T00:00:00.000Z",
    ...overrides,
  };
}
