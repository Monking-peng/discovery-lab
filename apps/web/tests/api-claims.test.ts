import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "../lib/api";

function rawClaim() {
  return {
    id: "claim-1",
    claim_id: "claim-1",
    study_id: "study-1",
    status: "PROPOSED",
    revision_status: "PROPOSED",
    is_current: true,
    publication_blockers: ["counterevidence_search_required"],
    revision_id: "claim-revision-1",
    claim_revision_id: "claim-revision-1",
    revision: 1,
    topic_key: "onboarding",
    statement: "Users need a clearer onboarding path.",
    summary: null,
    rationale: "Two exact evidence revisions describe the same friction.",
    confidence: 0.74,
    counterevidence_status: "NOT_RUN",
    counterevidence_summary: null,
    provenance: { producer: "test" },
    content_hash: "claim-hash",
    created_at: "2026-07-16T00:00:00Z",
    evidence_edges: [{
      id: "edge-1",
      evidence_id: "evidence-1",
      evidence_revision_id: "evidence-revision-3",
      source_id: "source-1",
      source_revision_id: "source-revision-2",
      relation: "contextualizes",
      rationale: "The quote establishes the workflow context.",
      relevance: 0.8,
      relation_confirmed: true,
      context_url: "/v1/evidence/evidence-1/context?evidence_revision_id=evidence-revision-3",
      latest_evidence_review: null,
    }],
    latest_review: null,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("strict Claim API client", () => {
  it("normalizes exact revisions, relation confirmation and publication blockers", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      items: [rawClaim()], total: 1, limit: 100, offset: 0,
    })));

    const result = await api.getClaims("study-1");

    expect(result.items[0]).toMatchObject({
      claimRevisionId: "claim-revision-1",
      revisionStatus: "PROPOSED",
      isCurrent: true,
      publicationBlockers: ["counterevidence_search_required"],
      topicKey: "onboarding",
    });
    expect(result.items[0].evidenceEdges[0]).toMatchObject({
      evidenceRevisionId: "evidence-revision-3",
      sourceRevisionId: "source-revision-2",
      relation: "contextualizes",
      relationConfirmed: true,
    });
  });

  it("fails closed when an evidence edge omits relation confirmation", async () => {
    const claim = rawClaim();
    delete (claim.evidence_edges[0] as Partial<(typeof claim.evidence_edges)[number]>).relation_confirmed;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      items: [claim], total: 1, limit: 100, offset: 0,
    })));

    await expect(api.getClaims("study-1")).rejects.toMatchObject({
      code: "invalid_response",
    });
  });

  it("serializes human relation confirmation and parses structured API conflicts", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(rawClaim(), 201))
      .mockResolvedValueOnce(jsonResponse({
        error: {
          code: "revision_conflict",
          message: "The base revision is no longer current.",
          details: { current_revision_id: "claim-revision-2" },
        },
        detail: "Conflict",
      }, 409));
    vi.stubGlobal("fetch", fetchMock);

    await api.createClaim("study-1", {
      topicKey: "onboarding",
      statement: "Users need a clearer onboarding path.",
      summary: null,
      rationale: "The exact quotes establish repeated friction.",
      confidence: 0.74,
      counterevidenceStatus: "NOT_RUN",
      counterevidenceSummary: null,
      provenance: {},
      evidenceEdges: [{
        evidenceId: "evidence-1",
        evidenceRevisionId: "evidence-revision-3",
        relation: "contextualizes",
        rationale: "This quote supplies workflow context.",
        relevance: 0.8,
        relationConfirmed: true,
      }],
      clientRequestId: "request-1",
    });
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({
      topic_key: "onboarding",
      rationale: "The exact quotes establish repeated friction.",
      evidence_edges: [{
        evidence_revision_id: "evidence-revision-3",
        relation_confirmed: true,
      }],
    });

    let conflict: unknown;
    try {
      await api.getClaims("study-1");
    } catch (error) {
      conflict = error;
    }
    expect(conflict).toBeInstanceOf(ApiError);
    expect(conflict).toMatchObject({
      status: 409,
      code: "revision_conflict",
      details: { current_revision_id: "claim-revision-2" },
    });
  });
});
