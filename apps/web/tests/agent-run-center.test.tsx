import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentRunCenter } from "../components/agent-run-center";
import type { AgentRun, Claim, Study, ToolRegistry } from "../lib/api";
import { translate } from "../lib/i18n";

const apiMocks = vi.hoisted(() => ({
  getAgentRuns: vi.fn(),
  getToolRegistry: vi.fn(),
  getClaims: vi.fn(),
  createAgentRun: vi.fn(),
  approveToolCall: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: { ...actual.api, ...apiMocks } };
});

const t = (key: Parameters<typeof translate>[1], vars?: Parameters<typeof translate>[2]) => (
  translate("en", key, vars)
);

const study: Study = {
  id: "study-1",
  title: "HelpHub",
  decisionQuestion: "Which workflow should improve?",
  status: "active",
  updatedAt: "2026-07-16T00:00:00Z",
  sourceCount: 2,
  evidenceCount: 6,
};

const claim: Claim = {
  id: "claim-1",
  claimId: "claim-1",
  studyId: "study-1",
  revisionId: "claim-revision-1",
  claimRevisionId: "claim-revision-1",
  statement: "High-risk enterprise tickets are missed before escalation.",
  status: "REVIEWED",
  revisionStatus: "REVIEWED",
  isCurrent: true,
  publicationBlockers: [],
  revision: 1,
  topicKey: "risk-escalation",
  summary: "Reviewed workflow problem.",
  rationale: "Exact reviewed evidence supports a bounded experiment.",
  confidence: 0.82,
  counterevidenceStatus: "SEARCHED_NONE_FOUND",
  counterevidenceSummary: "No direct contradiction.",
  provenance: { authoring_mode: "human" },
  contentHash: "f".repeat(64),
  createdAt: "2026-07-16T00:00:00Z",
  evidenceEdges: [],
  latestReview: null,
};

function registry(): ToolRegistry {
  return {
    schemaVersion: "tool-registry.v1",
    policyVersion: "tool-policy.v1",
    items: [{
      name: "retrieve_reviewed_evidence",
      version: "1.0.0",
      description: "Retrieve immutable context.",
      accessMode: "read",
      riskLevel: "low",
      requiresApproval: false,
      serverAllowlisted: true,
      mcpExposed: true,
      inputSchema: {},
      outputSchema: {},
    }, {
      name: "create_experiment_draft",
      version: "1.0.0",
      description: "Create a local experiment draft.",
      accessMode: "write",
      riskLevel: "medium",
      requiresApproval: true,
      serverAllowlisted: true,
      mcpExposed: false,
      inputSchema: {},
      outputSchema: {},
    }],
  };
}

function waitingRun(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: "run-1",
    studyId: "study-1",
    workflowName: "opportunity_discovery",
    workflowVersion: "1.0.0",
    status: "RUNNING",
    phase: "WAITING_HUMAN",
    goal: "Reduce missed escalation.",
    claimRevisionId: "claim-revision-1",
    claimStatement: claim.statement,
    contextManifest: {
      id: "manifest-1",
      query: "enterprise outage escalation SLA",
      purpose: "support",
      itemCount: 3,
      contentHash: "a".repeat(64),
      contextUrl: "/v1/context-manifests/manifest-1",
    },
    promptProfile: { source_content_handling: "untrusted_data_only" },
    plan: { steps: ["retrieve_reviewed_evidence", "request_exact_tool_approval"] },
    hypothesis: { statement: "A bounded pilot will improve detection.", falsifiable: true },
    outputSummary: { phase: "WAITING_HUMAN", execution_prevented: true },
    error: null,
    inputHash: "b".repeat(64),
    clientRequestId: "agent-request-1",
    startedAt: "2026-07-16T00:00:00Z",
    completedAt: null,
    createdAt: "2026-07-16T00:00:00Z",
    steps: [{
      id: "step-1",
      name: "approval_gate",
      ordinal: 3,
      status: "waiting_human",
      outputSummary: {},
      error: null,
      createdAt: "2026-07-16T00:00:00Z",
    }],
    toolCalls: [{
      id: "tool-call-read",
      runId: "run-1",
      runStepId: "step-0",
      toolName: "retrieve_reviewed_evidence",
      toolVersion: "1.0.0",
      accessMode: "read",
      riskLevel: "low",
      status: "SUCCEEDED",
      arguments: { query: "enterprise outage escalation SLA" },
      argumentsHash: "c".repeat(64),
      result: { context_manifest_id: "manifest-1", item_count: 3 },
      resultHash: "d".repeat(64),
      policySnapshot: { requires_approval: false },
      requiresApproval: false,
      startedAt: "2026-07-16T00:00:00Z",
      completedAt: "2026-07-16T00:00:00Z",
      createdAt: "2026-07-16T00:00:00Z",
      approval: null,
    }, {
      id: "tool-call-write",
      runId: "run-1",
      runStepId: "step-1",
      toolName: "create_experiment_draft",
      toolVersion: "1.0.0",
      accessMode: "write",
      riskLevel: "medium",
      status: "APPROVAL_REQUIRED",
      arguments: { title: "Pilot" },
      argumentsHash: "e".repeat(64),
      result: null,
      resultHash: null,
      policySnapshot: { approval_binding: "exact_arguments_sha256" },
      requiresApproval: true,
      startedAt: "2026-07-16T00:00:00Z",
      completedAt: null,
      createdAt: "2026-07-16T00:00:00Z",
      approval: null,
    }],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.getAgentRuns.mockResolvedValue({ items: [], total: 0 });
  apiMocks.getToolRegistry.mockResolvedValue(registry());
  apiMocks.getClaims.mockResolvedValue({ items: [claim], total: 1 });
  apiMocks.createAgentRun.mockResolvedValue(waitingRun());
  apiMocks.approveToolCall.mockResolvedValue(waitingRun({ status: "SUCCEEDED", phase: "COMPLETED" }));
});
afterEach(() => cleanup());

describe("Agent Run Center", () => {
  it("shows prompt/context engineering, tool policy, and exact approval before resume", async () => {
    const user = userEvent.setup();
    render(<AgentRunCenter live study={study} t={t} />);

    expect(await screen.findByText("retrieve_reviewed_evidence")).toBeVisible();
    await user.type(screen.getByLabelText(t("agent.goal")), "Reduce missed escalation.");
    await user.type(screen.getByLabelText(t("agent.query")), "enterprise outage escalation SLA");
    await user.type(screen.getByLabelText(t("agent.experimentTitle")), "Pilot");
    await user.type(screen.getByLabelText(t("agent.metric")), "missed escalation rate");
    await user.type(screen.getByLabelText(t("agent.threshold")), "30% reduction");
    await user.type(screen.getByLabelText(t("agent.cohort")), "enterprise agents");
    await user.click(screen.getByRole("button", { name: t("agent.start") }));

    await waitFor(() => expect(apiMocks.createAgentRun).toHaveBeenCalledWith(
      "study-1",
      expect.objectContaining({
        claimRevisionId: "claim-revision-1",
        retrieval: expect.objectContaining({ query: "enterprise outage escalation SLA" }),
        requestedAction: expect.objectContaining({ toolName: "create_experiment_draft" }),
      }),
    ));
    expect(screen.getByText(t("agent.waitingHuman"))).toBeVisible();
    expect(screen.getByText("untrusted_data_only")).toBeVisible();
    expect(screen.getByText("manifest-1")).toBeVisible();
    expect(screen.getAllByTitle("e".repeat(64))).toHaveLength(2);
    const writeCard = screen.getByText("APPROVAL_REQUIRED").closest("article");
    expect(writeCard).not.toBeNull();
    expect(within(writeCard as HTMLElement).queryByText(t("agent.toolExecuted"))).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(t("agent.reviewer")), "operator@example.test");
    await user.type(screen.getByLabelText(t("agent.approvalRationale")), "Approve exact pilot.");
    await user.click(screen.getByRole("button", { name: t("agent.approve") }));
    await waitFor(() => expect(apiMocks.approveToolCall).toHaveBeenCalledWith(
      "tool-call-write",
      expect.objectContaining({
        decision: "APPROVE",
        argumentsHash: "e".repeat(64),
      }),
    ));
  }, 20_000);

  it("is live-only and does not fabricate an Agent Run", () => {
    render(<AgentRunCenter live={false} study={study} t={t} />);
    expect(screen.getByText(t("agent.liveOnly"))).toBeVisible();
    expect(apiMocks.getAgentRuns).not.toHaveBeenCalled();
    expect(apiMocks.createAgentRun).not.toHaveBeenCalled();
  });
});
