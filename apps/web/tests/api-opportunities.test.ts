import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../lib/api";

function rawOpportunity(overrides: Record<string, unknown> = {}) {
  return {
    id: "opportunity-1",
    study_id: "study-1",
    claim_id: "claim-1",
    claim_revision_id: "claim-revision-7",
    status: "DRAFT",
    title: "Citation-first assisted triage",
    problem_statement: "Reviewers miss material signals when records are isolated.",
    desired_outcome: "Help a human reviewer recognize risk earlier.",
    next_step: "Test the workflow with five support specialists.",
    rationale: "The reviewed claim establishes a bounded workflow problem.",
    confidence: 0.74,
    assumptions: ["Reviewers can act on cited signals."],
    risks: ["Automation bias"],
    provenance: { authoring_mode: "human" },
    content_hash: "opportunity-hash",
    client_request_id: "opportunity-request-1",
    created_at: "2026-07-16T00:00:00Z",
    claim_statement: "Specialists need traceable risk context.",
    claim_context_url: "/v1/claims/claim-1?claim_revision_id=claim-revision-7",
    publishable: false,
    publication_blockers: ["OPPORTUNITY_DRAFT_NOT_PUBLISHED", "COUNTEREVIDENCE_NOT_RUN"],
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("strict Opportunity API client", () => {
  it("normalizes immutable draft lineage and explicit publication blockers", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      items: [rawOpportunity()], total: 1, limit: 100, offset: 0,
    })));

    const result = await api.getOpportunities("study-1");

    expect(result.items[0]).toMatchObject({
      id: "opportunity-1",
      studyId: "study-1",
      claimId: "claim-1",
      claimRevisionId: "claim-revision-7",
      status: "DRAFT",
      publishable: false,
      publicationBlockers: ["OPPORTUNITY_DRAFT_NOT_PUBLISHED", "COUNTEREVIDENCE_NOT_RUN"],
    });
  });

  it("serializes the exact Claim Revision and all human-authored fields", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(rawOpportunity(), 201));
    vi.stubGlobal("fetch", fetchMock);

    await api.createOpportunity("study-1", {
      claimId: "claim-1",
      claimRevisionId: "claim-revision-7",
      title: "Citation-first assisted triage",
      problemStatement: "Reviewers miss material signals when records are isolated.",
      desiredOutcome: "Help a human reviewer recognize risk earlier.",
      nextStep: "Test the workflow with five support specialists.",
      rationale: "The reviewed claim establishes a bounded workflow problem.",
      confidence: 0.74,
      assumptions: ["Reviewers can act on cited signals."],
      risks: ["Automation bias"],
      provenance: { authoring_mode: "human" },
      clientRequestId: "opportunity-request-1",
    });

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toEqual({
      claim_id: "claim-1",
      claim_revision_id: "claim-revision-7",
      title: "Citation-first assisted triage",
      problem_statement: "Reviewers miss material signals when records are isolated.",
      desired_outcome: "Help a human reviewer recognize risk earlier.",
      next_step: "Test the workflow with five support specialists.",
      rationale: "The reviewed claim establishes a bounded workflow problem.",
      confidence: 0.74,
      assumptions: ["Reviewers can act on cited signals."],
      risks: ["Automation bias"],
      provenance: { authoring_mode: "human" },
      client_request_id: "opportunity-request-1",
    });
  });

  it("fails closed if an Opportunity is reported as publishable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      items: [rawOpportunity({ publishable: true })], total: 1, limit: 100, offset: 0,
    })));

    await expect(api.getOpportunities("study-1")).rejects.toMatchObject({
      code: "invalid_response",
      details: { field: "opportunity.publishable" },
    });
  });
});
