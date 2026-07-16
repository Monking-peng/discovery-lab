import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DiscoveryWorkbench } from "../components/discovery-workbench";
import type { EvidenceContext, SourceItem, Study } from "../lib/api";
import {
  LOCALE_STORAGE_KEY,
  translate,
  type Locale,
} from "../lib/i18n";
import { makeEvidence } from "./evidence-fixture";
import { makeClaim } from "./claim-fixture";

const apiMocks = vi.hoisted(() => ({
  getStudies: vi.fn(),
  createStudy: vi.fn(),
  getEvidence: vi.fn(),
  getSources: vi.fn(),
  getRuns: vi.fn(),
  getEvidenceContext: vi.fn(),
  reviewEvidence: vi.fn(),
  authorEvidenceRevision: vi.fn(),
  getClaims: vi.fn(),
  uploadSource: vi.fn(),
  processSource: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: apiMocks };
});

const study: Study = {
  id: "study-integration",
  revisionId: "study-integration-revision-1",
  title: "Support routing study",
  decisionQuestion: "Where should the team add human review?",
  status: "active",
  updatedAt: "2026-07-15T00:00:00.000Z",
  sourceCount: 1,
  evidenceCount: 1,
};

const evidence = makeEvidence({
  id: "evidence-integration",
  revisionId: "evidence-integration-revision-7",
  studyId: study.id,
  title: "Classification and routing needs context",
  quote: "The model needs customer context before it routes a high-risk request.",
  observation: "High-risk routing fails when account context is missing.",
  interpretation: "Human review is valuable for high-risk routing.",
  sourceId: "source-integration",
  sourceRevisionId: "source-integration-revision-3",
  sourceName: "routing-interview.md",
  locatorLabel: "paragraph 8",
  tags: ["routing", "risk"],
  syntheticDemo: false,
  reviewStatus: "approved",
  relationship: "supports",
});

const context: EvidenceContext = {
  evidenceId: evidence.id,
  evidenceRevisionId: evidence.revisionId,
  sourceRevisionId: evidence.sourceRevisionId,
  sourceName: evidence.sourceName,
  locatorLabel: evidence.locatorLabel,
  before: "The team reviewed recent escalations.",
  highlight: evidence.quote,
  after: "They added a manual review queue.",
  integrity: {
    quoteMatchesSegment: true,
    segmentHashMatches: true,
    evidenceHashMatches: true,
  },
};

function message(locale: Locale, key: Parameters<typeof translate>[1]) {
  return translate(locale, key);
}

function primeLiveApi() {
  apiMocks.getStudies.mockResolvedValue([study]);
  apiMocks.getEvidence.mockResolvedValue([evidence]);
  apiMocks.getSources.mockResolvedValue({ items: [] as SourceItem[], total: 0 });
  apiMocks.getRuns.mockResolvedValue({ items: [], total: 0 });
  apiMocks.getEvidenceContext.mockResolvedValue(context);
  apiMocks.reviewEvidence.mockResolvedValue({
    id: "evidence-review-1",
    evidenceId: evidence.id,
    evidenceRevisionId: evidence.revisionId,
    decision: "ACCEPT",
    reviewer: "Research lead",
    rationale: "Verified against the source.",
    clientRequestId: "request-1",
    createdAt: "2026-07-16T00:00:00.000Z",
  });
  apiMocks.authorEvidenceRevision.mockResolvedValue({
    evidenceId: evidence.id,
    evidenceRevisionId: "evidence-integration-revision-8",
    parentRevisionId: evidence.revisionId,
  });
  apiMocks.getClaims.mockResolvedValue({ items: [], total: 0 });
}

async function renderLiveWorkbench() {
  if (!window.location.hash) window.history.replaceState(null, "", "/#evidence");
  render(<DiscoveryWorkbench />);
  await screen.findByRole("button", { name: message("en", "nav.evidence") });
  await waitFor(() => expect(apiMocks.getEvidence).toHaveBeenCalledWith(study.id));
}

beforeEach(() => {
  vi.clearAllMocks();
  primeLiveApi();
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
  document.documentElement.lang = "en";
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
});

describe("DiscoveryWorkbench navigation and locale integration", () => {
  it("lands on a focused product overview before exposing the dense workbench", async () => {
    render(<DiscoveryWorkbench />);

    expect(await screen.findByRole("heading", {
      name: "From raw research to a decision you can defend.",
    })).toBeVisible();
    expect(screen.getByRole("button", { name: "Overview" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("heading", { name: "How to use Discovery Lab" })).toBeVisible();
    expect(screen.getAllByTestId("overview-step")).toHaveLength(5);
    expect(screen.getAllByRole("button", { name: "Explore evidence" })[0]).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Open final PRD" })[0]).toBeVisible();
  });

  it("opens the most substantial study instead of a newer empty smoke-test study", async () => {
    const emptySmokeStudy: Study = {
      ...study,
      id: "study-empty-smoke",
      revisionId: "study-empty-smoke-revision-1",
      title: "Vector smoke test",
      sourceCount: 0,
      evidenceCount: 0,
      updatedAt: "2026-07-16T00:00:00.000Z",
    };
    const completeDemoStudy: Study = {
      ...study,
      id: "study-complete-demo",
      revisionId: "study-complete-demo-revision-1",
      title: "HelpHub complete product chain",
      sourceCount: 2,
      evidenceCount: 31,
      updatedAt: "2026-07-15T00:00:00.000Z",
    };
    apiMocks.getStudies.mockResolvedValue([emptySmokeStudy, completeDemoStudy]);

    render(<DiscoveryWorkbench />);

    await waitFor(() => expect(apiMocks.getEvidence).toHaveBeenCalledWith(completeDemoStudy.id));
    expect(screen.getByRole("button", { name: /HelpHub complete product chain/ }))
      .toHaveAttribute("aria-pressed", "true");
  });

  it("opens Claims & Opportunities from #claims and exposes the active page to assistive technology", async () => {
    window.history.replaceState(null, "", "/#claims");

    await renderLiveWorkbench();

    const claimsNavigation = await screen.findByRole("button", {
      name: message("en", "nav.claims"),
    });
    expect(claimsNavigation).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: message("en", "claims.heroTitle") })).toBeVisible();
    expect(window.location.hash).toBe("#claims");
  });

  it("makes Claims navigation clickable and updates aria-current without reloading", async () => {
    const user = userEvent.setup();
    await renderLiveWorkbench();

    const evidenceNavigation = screen.getByRole("button", {
      name: message("en", "nav.evidence"),
    });
    const claimsNavigation = screen.getByRole("button", {
      name: message("en", "nav.claims"),
    });
    expect(evidenceNavigation).toHaveAttribute("aria-current", "page");
    expect(claimsNavigation).not.toHaveAttribute("aria-current");

    await user.click(claimsNavigation);

    expect(claimsNavigation).toHaveAttribute("aria-current", "page");
    expect(evidenceNavigation).not.toHaveAttribute("aria-current");
    expect(window.location.hash).toBe("#claims");
    expect(screen.getByRole("heading", { name: message("en", "claims.heroTitle") })).toBeVisible();
  });

  it("progressively reveals evidence review and source trace instead of showing everything at once", async () => {
    const user = userEvent.setup();
    await renderLiveWorkbench();
    const detail = screen.getByRole("complementary", { name: message("en", "detail.region") });

    expect(within(detail).getByRole("tab", { name: "Summary" })).toHaveAttribute("aria-selected", "true");
    expect(within(detail).getByText(`“${evidence.quote}”`)).toBeVisible();
    expect(within(detail).queryByLabelText(message("en", "evidenceReview.reviewer"))).not.toBeInTheDocument();
    expect(within(detail).queryByRole("heading", { name: message("en", "context.title") })).not.toBeInTheDocument();

    await user.click(within(detail).getByRole("tab", { name: "Review" }));
    expect(within(detail).getByLabelText(message("en", "evidenceReview.reviewer"))).toBeVisible();
    expect(within(detail).queryByText(`“${evidence.quote}”`)).not.toBeInTheDocument();

    await user.click(within(detail).getByRole("tab", { name: "Source & trace" }));
    expect(within(detail).getByRole("heading", { name: message("en", "context.title") })).toBeVisible();
    expect(within(detail).getByText(context.highlight)).toBeVisible();
  });

  it("initializes from the saved locale, switches language, and persists the new choice", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh-CN");
    render(<DiscoveryWorkbench />);

    const chineseClaimsNavigation = await screen.findByRole("button", {
      name: message("zh-CN", "nav.claims"),
    });
    expect(chineseClaimsNavigation).toBeVisible();
    await waitFor(() => expect(document.documentElement.lang).toBe("zh-CN"));
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("zh-CN");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "EN" }));

    expect(await screen.findByRole("button", { name: message("en", "nav.claims") })).toBeVisible();
    expect(document.documentElement.lang).toBe("en");
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("en");
  });

  it("returns from a claim edge to Evidence Explorer and requests the exact evidence revision", async () => {
    const user = userEvent.setup();
    await renderLiveWorkbench();
    await waitFor(() => {
      expect(apiMocks.getEvidenceContext).toHaveBeenCalledWith(evidence.id, evidence.revisionId);
    });
    apiMocks.getEvidenceContext.mockClear();

    await user.click(screen.getByRole("button", { name: message("en", "nav.claims") }));
    await user.click(await screen.findByRole("button", { name: message("en", "claims.openEvidence") }));

    await waitFor(() => {
      expect(apiMocks.getEvidenceContext).toHaveBeenCalledTimes(1);
      expect(apiMocks.getEvidenceContext).toHaveBeenCalledWith(
        evidence.id,
        "evidence-integration-revision-7",
      );
    });
    expect(screen.getByRole("button", { name: message("en", "nav.evidence") }))
      .toHaveAttribute("aria-current", "page");
    expect(window.location.hash).toBe("#evidence");
  });

  it("fails closed when the API returns a different immutable revision", async () => {
    apiMocks.getEvidenceContext.mockResolvedValue({
      ...context,
      evidenceRevisionId: "different-evidence-revision",
    });

    await renderLiveWorkbench();

    expect(await screen.findByText(message("en", "context.revisionMismatch"))).toBeVisible();
    expect(screen.queryByLabelText(message("en", "integrity.aria"))).not.toBeInTheDocument();
  });

  it("replays an old evidence revision in detail without replacing the latest synthesis input", async () => {
    const user = userEvent.setup();
    const oldEvidence = makeEvidence({
      ...evidence,
      revisionId: "evidence-integration-revision-2",
      revision: 2,
      quote: "This is the older immutable wording.",
      observation: "This observation belongs only to revision two.",
    });
    apiMocks.getClaims.mockResolvedValue({
      items: [makeClaim({
        studyId: study.id,
        statement: "Saved claim with an old evidence edge.",
        evidenceEdges: [{
          id: "edge-old",
          evidenceId: oldEvidence.id,
          evidenceRevisionId: oldEvidence.revisionId!,
          sourceId: oldEvidence.sourceId,
          sourceRevisionId: oldEvidence.sourceRevisionId!,
          relation: "contextualizes",
          rationale: "Revision two supplies historical context.",
          relevance: 0.7,
          relationConfirmed: true,
          contextUrl: "/context/old",
          latestEvidenceReview: null,
        }],
      })],
      total: 1,
    });
    await renderLiveWorkbench();
    await user.click(screen.getByRole("button", { name: message("en", "nav.claims") }));
    expect((await screen.findAllByText("Saved claim with an old evidence edge.")).length).toBeGreaterThan(0);

    apiMocks.getEvidenceContext.mockResolvedValueOnce({
      ...context,
      evidenceRevisionId: oldEvidence.revisionId,
      sourceRevisionId: oldEvidence.sourceRevisionId,
      highlight: oldEvidence.quote,
      evidenceSnapshot: oldEvidence,
    });
    const savedSection = screen.getByRole("heading", { name: "Saved claims" }).closest("section");
    expect(savedSection).not.toBeNull();
    await user.click(within(savedSection!).getByRole("button", { name: "Open evidence" }));
    expect(await screen.findByText(`“${oldEvidence.quote}”`)).toBeVisible();

    await user.click(screen.getByRole("button", { name: message("en", "nav.claims") }));
    expect(screen.getByText(evidence.quote)).toBeVisible();
    expect(screen.queryByText(oldEvidence.quote)).not.toBeInTheDocument();
  });

  it("posts a human review against the exact evidence revision and refreshes that snapshot", async () => {
    const user = userEvent.setup();
    const pendingEvidence = makeEvidence({ ...evidence, reviewStatus: "pending" });
    apiMocks.getEvidence.mockResolvedValue([pendingEvidence]);
    apiMocks.getEvidenceContext.mockResolvedValue({ ...context, evidenceSnapshot: pendingEvidence });

    await renderLiveWorkbench();
    await waitFor(() => expect(apiMocks.getEvidenceContext).toHaveBeenCalledWith(
      pendingEvidence.id,
      pendingEvidence.revisionId,
    ));
    apiMocks.getEvidenceContext.mockClear();
    apiMocks.getEvidenceContext.mockResolvedValueOnce({
      ...context,
      evidenceSnapshot: { ...pendingEvidence, reviewStatus: "approved" },
    });

    await user.click(screen.getByRole("tab", { name: "Review" }));

    fireEvent.change(screen.getByLabelText(message("en", "evidenceReview.reviewer")), {
      target: { value: "Research lead" },
    });
    fireEvent.change(screen.getByLabelText(message("en", "evidenceReview.rationale")), {
      target: { value: "Verified against the exact source passage." },
    });
    await user.click(screen.getByRole("button", { name: message("en", "evidenceReview.accept") }));

    await waitFor(() => expect(apiMocks.reviewEvidence).toHaveBeenCalledWith(
      pendingEvidence.id,
      pendingEvidence.revisionId,
      expect.objectContaining({
        decision: "ACCEPT",
        reviewer: "Research lead",
        rationale: "Verified against the exact source passage.",
        clientRequestId: expect.any(String),
      }),
    ));
    await waitFor(() => expect(apiMocks.getEvidenceContext).toHaveBeenCalledWith(
      pendingEvidence.id,
      pendingEvidence.revisionId,
    ));
    expect(await screen.findByText(message("en", "evidenceReview.reviewSaved"))).toBeVisible();
  });

  it("blocks synthetic acceptance and opens the locked human-authoring workflow", async () => {
    const user = userEvent.setup();
    const syntheticEvidence = makeEvidence({
      ...evidence,
      reviewStatus: "pending",
      syntheticDemo: true,
      humanAuthored: false,
      tags: ["synthetic-demo", "routing"],
    });
    apiMocks.getEvidence.mockResolvedValue([syntheticEvidence]);
    apiMocks.getEvidenceContext.mockResolvedValue({
      ...context,
      evidenceSnapshot: syntheticEvidence,
    });

    await renderLiveWorkbench();

    await user.click(screen.getByRole("tab", { name: "Review" }));

    expect(screen.getByRole("button", { name: message("en", "evidenceReview.accept") })).toBeDisabled();
    expect(screen.getByText(message("en", "evidenceReview.syntheticBlocked"))).toBeVisible();
    expect(screen.getByRole("heading", { name: message("en", "evidenceReview.authorTitle") })).toBeVisible();
    expect(screen.getByLabelText(message("en", "evidenceReview.quoteLocked"))).toHaveTextContent(
      syntheticEvidence.quote,
    );
    expect(screen.getByLabelText(message("en", "evidenceReview.tags"))).toHaveValue("routing");
    expect(apiMocks.reviewEvidence).not.toHaveBeenCalled();
  });

  it("authors from base_revision_id without sending the quote and reloads the new exact context", async () => {
    const user = userEvent.setup();
    const syntheticEvidence = makeEvidence({
      ...evidence,
      reviewStatus: "pending",
      syntheticDemo: true,
      humanAuthored: false,
    });
    const authoredEvidence = makeEvidence({
      ...syntheticEvidence,
      revisionId: "evidence-integration-revision-8",
      revision: 8,
      observation: "A researcher-authored observation.",
      interpretation: "A researcher-authored interpretation.",
      inference: "A falsifiable researcher-authored inference.",
      tags: ["routing", "human-reviewed"],
      syntheticDemo: false,
      humanAuthored: true,
      parentRevisionId: syntheticEvidence.revisionId,
    });
    apiMocks.getEvidence.mockResolvedValue([syntheticEvidence]);
    apiMocks.getEvidenceContext.mockResolvedValue({
      ...context,
      evidenceSnapshot: syntheticEvidence,
    });
    apiMocks.authorEvidenceRevision.mockResolvedValue({
      evidenceId: syntheticEvidence.id,
      evidenceRevisionId: authoredEvidence.revisionId,
      parentRevisionId: syntheticEvidence.revisionId,
    });

    await renderLiveWorkbench();
    await waitFor(() => expect(apiMocks.getEvidenceContext).toHaveBeenCalledWith(
      syntheticEvidence.id,
      syntheticEvidence.revisionId,
    ));
    apiMocks.getEvidenceContext.mockClear();
    apiMocks.getEvidenceContext.mockResolvedValueOnce({
      ...context,
      evidenceRevisionId: authoredEvidence.revisionId,
      highlight: authoredEvidence.quote,
      evidenceSnapshot: authoredEvidence,
    });

    await user.click(screen.getByRole("tab", { name: "Review" }));

    fireEvent.change(screen.getByLabelText(message("en", "evidenceReview.observation")), {
      target: { value: authoredEvidence.observation },
    });
    fireEvent.change(screen.getByLabelText(message("en", "evidenceReview.interpretation")), {
      target: { value: authoredEvidence.interpretation },
    });
    fireEvent.change(screen.getByLabelText(message("en", "evidenceReview.inference")), {
      target: { value: authoredEvidence.inference },
    });
    fireEvent.change(screen.getByLabelText(message("en", "evidenceReview.tags")), {
      target: { value: "routing, human-reviewed" },
    });
    fireEvent.change(screen.getByLabelText(message("en", "evidenceReview.editor")), {
      target: { value: "Research lead" },
    });
    fireEvent.change(screen.getByLabelText(message("en", "evidenceReview.editRationale")), {
      target: { value: "Replace a synthetic interpretation with accountable human analysis." },
    });
    await user.click(screen.getByRole("button", { name: message("en", "evidenceReview.createRevision") }));

    await waitFor(() => expect(apiMocks.authorEvidenceRevision).toHaveBeenCalledWith(
      syntheticEvidence.id,
      expect.objectContaining({
        baseRevisionId: syntheticEvidence.revisionId,
        observation: authoredEvidence.observation,
        interpretation: authoredEvidence.interpretation,
        inference: authoredEvidence.inference,
        tags: ["routing", "human-reviewed"],
        editor: "Research lead",
        clientRequestId: expect.any(String),
      }),
    ));
    const authorPayload = apiMocks.authorEvidenceRevision.mock.calls[0]?.[1];
    expect(authorPayload).not.toHaveProperty("quote");
    await waitFor(() => expect(apiMocks.getEvidenceContext).toHaveBeenCalledWith(
      syntheticEvidence.id,
      authoredEvidence.revisionId,
    ));
    expect(screen.getByText(message("en", "evidenceReview.humanAuthored"))).toBeVisible();
    await user.click(screen.getByRole("tab", { name: message("en", "detail.tab.summary") }));
    expect(await screen.findByText(authoredEvidence.observation)).toBeVisible();
  });
});
