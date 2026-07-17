import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../lib/api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const decision = {
  id: "decision-1",
  study_id: "study-1",
  experiment_id: "experiment-1",
  decision: "PROCEED",
  observed_result: "Missed escalation fell by 34%.",
  rationale: "The threshold was met.",
  decided_by: "lead@example.test",
  content_hash: "d".repeat(64),
  client_request_id: "decision-request-1",
  created_at: "2026-07-16T00:02:00Z",
};

const prd = {
  id: "prd-1",
  study_id: "study-1",
  decision_id: "decision-1",
  title: "Risk escalation pilot PRD",
  status: "DRAFT",
  publishable: false,
  sections: {
    problem: { body: "High-risk tickets are missed.", citation_refs: ["claim-revision:claim-r1"] },
  },
  citations: [{
    kind: "claim_revision",
    citation_id: "claim-revision:claim-r1",
    claim_id: "claim-1",
    revision_id: "claim-r1",
    revision: 1,
    statement: "High-risk tickets are missed.",
    summary: null,
    content_hash: "a".repeat(64),
    review_id: "claim-review-1",
    review_decision: "ACCEPT",
    review_reviewer: "lead@example.test",
    context_url: "/v1/claims/claim-1?claim_revision_id=claim-r1",
  }, {
    kind: "evidence_revision",
    citation_id: "evidence-revision:evidence-r1",
    evidence_id: "evidence-1",
    revision_id: "evidence-r1",
    source_id: "source-1",
    source_revision_id: "source-r1",
    evidence_review_id: "evidence-review-1",
    review_decision: "ACCEPT",
    review_reviewer: "researcher@example.test",
    evidence_content_hash: "b".repeat(64),
    source_content_hash: "c".repeat(64),
    source_name: "tickets.txt",
    quote: "A ticket missed escalation.",
    observation: "One high-risk miss was recorded.",
    locator: { kind: "text", char_start: 0, char_end: 31 },
    context_url: "/v1/evidence/evidence-1/context?evidence_revision_id=evidence-r1",
  }],
  publication_blockers: [
    "PRD_REQUIRES_FINAL_REVIEW",
    "EXTERNAL_PUBLICATION_NOT_IMPLEMENTED",
  ],
  content_hash: "e".repeat(64),
  client_request_id: "prd-request-1",
  created_at: "2026-07-16T00:03:00Z",
};

const bundle = {
  study_id: "study-1",
  total_experiments: 1,
  items: [{
    hypothesis: {
      id: "hypothesis-1",
      study_id: "study-1",
      run_id: "run-1",
      claim_id: "claim-1",
      claim_revision_id: "claim-r1",
      context_manifest_id: "manifest-1",
      status: "DRAFT",
      statement: "A bounded pilot will reduce misses.",
      expected_outcome: "30% reduction",
      falsification_criterion: "Stop if reduction is below 30%.",
      provenance: { source: "approved_agent_tool_call" },
      content_hash: "f".repeat(64),
      created_at: "2026-07-16T00:00:00Z",
    },
    experiment: {
      id: "experiment-1",
      study_id: "study-1",
      hypothesis_id: "hypothesis-1",
      tool_call_id: "tool-call-1",
      status: "DRAFT",
      title: "Human-confirmed escalation pilot",
      target_cohort: "enterprise agents",
      primary_metric: "missed escalation rate",
      success_threshold: "30% reduction",
      provenance: { arguments_hash: "0".repeat(64) },
      content_hash: "1".repeat(64),
      created_at: "2026-07-16T00:01:00Z",
    },
    decisions: [],
    prds: [],
  }],
};

afterEach(() => vi.unstubAllGlobals());

describe("strict Product Artifact API client", () => {
  it("normalizes the full chain and sends append-only decision and PRD requests", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(bundle))
      .mockResolvedValueOnce(jsonResponse(decision, 201))
      .mockResolvedValueOnce(jsonResponse(prd, 201));
    vi.stubGlobal("fetch", fetchMock);

    const loaded = await api.getProductArtifacts("study-1");
    expect(loaded.items[0].experiment.title).toBe("Human-confirmed escalation pilot");

    const createdDecision = await api.createProductDecision("experiment-1", {
      decision: "PROCEED",
      observedResult: "Missed escalation fell by 34%.",
      rationale: "The threshold was met.",
      decidedBy: "lead@example.test",
      clientRequestId: "decision-request-1",
    });
    expect(createdDecision.decision).toBe("PROCEED");

    const createdPrd = await api.createPrd("decision-1", {
      title: "Risk escalation pilot PRD",
      clientRequestId: "prd-request-1",
    });
    expect(createdPrd.publishable).toBe(false);
    expect(createdPrd.citations[1]).toMatchObject({
      kind: "evidence_revision",
      evidenceRevisionId: "evidence-r1",
      sourceRevisionId: "source-r1",
    });
    expect(JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body))).toEqual({
      decision: "PROCEED",
      observed_result: "Missed escalation fell by 34%.",
      rationale: "The threshold was met.",
      decided_by: "lead@example.test",
      client_request_id: "decision-request-1",
    });
  });

  it("fails closed if a PRD is marked publishable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ...prd, publishable: true })));
    await expect(api.getPrd("prd-1")).rejects.toMatchObject({
      code: "invalid_response",
      details: { field: "prd.publishable" },
    });
  });
});
