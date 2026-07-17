import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../lib/api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function rawRun(overrides: Record<string, unknown> = {}) {
  return {
    id: "run-1",
    study_id: "study-1",
    workflow_name: "opportunity_discovery",
    workflow_version: "1.0.0",
    status: "RUNNING",
    phase: "WAITING_HUMAN",
    goal: "Reduce missed escalation.",
    claim_revision_id: "claim-revision-1",
    claim_statement: "High-risk tickets are missed.",
    context_manifest: {
      id: "manifest-1",
      query: "enterprise outage escalation SLA",
      purpose: "support",
      item_count: 3,
      content_hash: "a".repeat(64),
      context_url: "/v1/context-manifests/manifest-1",
    },
    prompt_profile: { source_content_handling: "untrusted_data_only" },
    plan: { steps: ["retrieve_reviewed_evidence"] },
    hypothesis: { statement: "A bounded pilot will improve detection.", falsifiable: true },
    output_summary: { phase: "WAITING_HUMAN", execution_prevented: true },
    error: null,
    input_hash: "b".repeat(64),
    client_request_id: "agent-request-1",
    started_at: "2026-07-16T00:00:00Z",
    completed_at: null,
    created_at: "2026-07-16T00:00:00Z",
    steps: [{
      id: "step-1",
      name: "approval_gate",
      ordinal: 3,
      status: "WAITING_HUMAN",
      input_snapshot: {},
      input_hash: "c".repeat(64),
      output_summary: {},
      error: null,
      started_at: "2026-07-16T00:00:00Z",
      completed_at: null,
      created_at: "2026-07-16T00:00:00Z",
    }],
    tool_calls: [{
      id: "tool-call-1",
      run_id: "run-1",
      run_step_id: "step-1",
      tool_name: "create_experiment_draft",
      tool_version: "1.0.0",
      access_mode: "write",
      risk_level: "medium",
      status: "APPROVAL_REQUIRED",
      arguments: { title: "Pilot" },
      arguments_hash: "d".repeat(64),
      result: null,
      result_hash: null,
      policy_snapshot: { approval_binding: "exact_arguments_sha256" },
      requires_approval: true,
      started_at: "2026-07-16T00:00:00Z",
      completed_at: null,
      created_at: "2026-07-16T00:00:00Z",
      approval: null,
    }],
    ...overrides,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("strict Agent Harness API client", () => {
  it("normalizes exact tool arguments and sends approval with the immutable hash", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(rawRun(), 201))
      .mockResolvedValueOnce(jsonResponse(rawRun({
        status: "SUCCEEDED",
        phase: "COMPLETED",
        tool_calls: [{
          ...rawRun().tool_calls[0],
          status: "SUCCEEDED",
          result: { artifact_type: "experiment_draft", external_system_written: false },
          result_hash: "e".repeat(64),
          approval: {
            id: "approval-1",
            decision: "APPROVE",
            arguments_hash: "d".repeat(64),
            reviewer: "operator@example.test",
            rationale: "Approve exact pilot.",
            client_request_id: "approval-request-1",
            created_at: "2026-07-16T00:01:00Z",
          },
        }],
      }), 201));
    vi.stubGlobal("fetch", fetchMock);

    const created = await api.createAgentRun("study-1", {
      goal: "Reduce missed escalation.",
      claimRevisionId: "claim-revision-1",
      retrieval: { query: "enterprise outage escalation SLA", purpose: "support", limit: 5 },
      requestedAction: {
        toolName: "create_experiment_draft",
        arguments: {
          title: "Pilot",
          primaryMetric: "missed escalation rate",
          successThreshold: "30% reduction",
          targetCohort: "enterprise agents",
        },
      },
      clientRequestId: "agent-request-1",
    });
    expect(created.toolCalls[0]).toMatchObject({
      argumentsHash: "d".repeat(64),
      status: "APPROVAL_REQUIRED",
      requiresApproval: true,
    });

    const approved = await api.approveToolCall("tool-call-1", {
      decision: "APPROVE",
      argumentsHash: "d".repeat(64),
      reviewer: "operator@example.test",
      rationale: "Approve exact pilot.",
      clientRequestId: "approval-request-1",
    });
    expect(approved.phase).toBe("COMPLETED");
    const approvalRequest = fetchMock.mock.calls[1][1] as RequestInit;
    expect(JSON.parse(String(approvalRequest.body))).toEqual({
      decision: "APPROVE",
      arguments_hash: "d".repeat(64),
      reviewer: "operator@example.test",
      rationale: "Approve exact pilot.",
      client_request_id: "approval-request-1",
    });
  });

  it("fails closed when a write result claims an external system was modified", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(rawRun({
      status: "SUCCEEDED",
      phase: "COMPLETED",
      tool_calls: [{
        ...rawRun().tool_calls[0],
        status: "SUCCEEDED",
        result: { artifact_type: "experiment_draft", external_system_written: true },
        result_hash: "e".repeat(64),
      }],
    }))));

    await expect(api.getAgentRun("run-1")).rejects.toMatchObject({
      code: "invalid_response",
      details: { field: "agent_run.tool_calls[0].result.external_system_written" },
    });
  });
});
