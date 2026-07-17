import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProductDecisionCenter } from "../components/product-decision-center";
import type { PrdArtifact, ProductArtifactBundle, ProductDecision, Study } from "../lib/api";
import { translate } from "../lib/i18n";

const apiMocks = vi.hoisted(() => ({
  getProductArtifacts: vi.fn(),
  createProductDecision: vi.fn(),
  createPrd: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: { ...actual.api, ...apiMocks } };
});

const t = (key: Parameters<typeof translate>[1], vars?: Parameters<typeof translate>[2]) => (
  translate("en", key, vars)
);
const study: Study = {
  id: "study-1", title: "HelpHub", decisionQuestion: "Improve escalation?", status: "active",
  updatedAt: "2026-07-16T00:00:00Z", sourceCount: 1, evidenceCount: 1,
};
const decision: ProductDecision = {
  id: "decision-1", studyId: "study-1", experimentId: "experiment-1", decision: "PROCEED",
  observedResult: "Missed escalation fell by 34%.", rationale: "Threshold met.",
  decidedBy: "lead@example.test", contentHash: "d".repeat(64),
  clientRequestId: "decision-request-1", createdAt: "2026-07-16T00:02:00Z",
};
const prd: PrdArtifact = {
  id: "prd-1", studyId: "study-1", decisionId: "decision-1", title: "Escalation PRD",
  status: "DRAFT", publishable: false,
  sections: { problem: { body: "High-risk tickets are missed.", citationRefs: ["claim-revision:claim-r1"] } },
  citations: [{ kind: "claim_revision", citationId: "claim-revision:claim-r1", claimId: "claim-1",
    claimRevisionId: "claim-r1", revision: 1, statement: "High-risk tickets are missed.", summary: null,
    contentHash: "a".repeat(64), reviewId: "review-1", reviewDecision: "ACCEPT",
    reviewReviewer: "lead@example.test", contextUrl: "/v1/claims/claim-1?claim_revision_id=claim-r1" }],
  publicationBlockers: ["PRD_REQUIRES_FINAL_REVIEW", "EXTERNAL_PUBLICATION_NOT_IMPLEMENTED"],
  contentHash: "e".repeat(64), clientRequestId: "prd-request-1", createdAt: "2026-07-16T00:03:00Z",
};
const bundle: ProductArtifactBundle = {
  studyId: "study-1", totalExperiments: 1, items: [{
    hypothesis: {
      id: "hypothesis-1", studyId: "study-1", runId: "run-1", claimId: "claim-1",
      claimRevisionId: "claim-r1", contextManifestId: "manifest-1", status: "DRAFT",
      statement: "A bounded pilot will reduce misses.", expectedOutcome: "30% reduction",
      falsificationCriterion: "Stop below 30%.", provenance: {}, contentHash: "f".repeat(64),
      createdAt: "2026-07-16T00:00:00Z",
    },
    experiment: {
      id: "experiment-1", studyId: "study-1", hypothesisId: "hypothesis-1", toolCallId: "tool-1",
      status: "DRAFT", title: "Human-confirmed escalation pilot", targetCohort: "enterprise agents",
      primaryMetric: "missed escalation rate", successThreshold: "30% reduction", provenance: {},
      contentHash: "1".repeat(64), createdAt: "2026-07-16T00:01:00Z",
    }, decisions: [], prds: [],
  }],
};

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.getProductArtifacts.mockResolvedValue(bundle);
  apiMocks.createProductDecision.mockResolvedValue(decision);
  apiMocks.createPrd.mockResolvedValue(prd);
});
afterEach(() => cleanup());

describe("Decision & PRD Center", () => {
  it("turns an approved experiment into a human decision and exactly cited draft PRD", async () => {
    const user = userEvent.setup();
    render(<ProductDecisionCenter live study={study} t={t} />);

    expect(await screen.findByText("Human-confirmed escalation pilot")).toBeVisible();
    await user.type(screen.getByLabelText(t("product.observedResult")), "Missed escalation fell by 34%.");
    await user.type(screen.getByLabelText(t("product.decisionRationale")), "Threshold met.");
    await user.type(screen.getByLabelText(t("product.decidedBy")), "lead@example.test");
    await user.click(screen.getByRole("button", { name: t("product.saveDecision") }));
    await waitFor(() => expect(apiMocks.createProductDecision).toHaveBeenCalled());

    await user.clear(screen.getByLabelText(t("product.prdTitle")));
    await user.type(screen.getByLabelText(t("product.prdTitle")), "Escalation PRD");
    await user.click(screen.getByRole("button", { name: t("product.generatePrd") }));
    await waitFor(() => expect(apiMocks.createPrd).toHaveBeenCalledWith(
      "decision-1",
      expect.objectContaining({ title: "Escalation PRD" }),
    ));
    expect((await screen.findAllByText("High-risk tickets are missed.")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("claim-r1").length).toBeGreaterThan(0);
    expect(screen.getByText(t("product.notPublishable"))).toBeVisible();
  }, 10_000);

  it("is live-only and never fabricates a product decision", () => {
    render(<ProductDecisionCenter live={false} study={study} t={t} />);
    expect(screen.getByText(t("product.liveOnly"))).toBeVisible();
    expect(apiMocks.getProductArtifacts).not.toHaveBeenCalled();
  });
});
