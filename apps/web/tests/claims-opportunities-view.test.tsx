import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ClaimsOpportunitiesView, type ClaimsTranslator } from "../components/claims-opportunities-view";
import { translate, type Locale } from "../lib/i18n";
import { makeEvidence } from "./evidence-fixture";
import { makeClaim } from "./claim-fixture";

const apiMocks = vi.hoisted(() => ({
  getClaims: vi.fn(),
  createClaim: vi.fn(),
  createClaimRevision: vi.fn(),
  reviewClaimRevision: vi.fn(),
  getClaim: vi.fn(),
  getOpportunities: vi.fn(),
  createOpportunity: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: { ...actual.api, ...apiMocks } };
});

function translator(locale: Locale): ClaimsTranslator {
  return (key, vars) => translate(locale, key, vars);
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.getClaims.mockResolvedValue({ items: [], total: 0 });
  apiMocks.getOpportunities.mockResolvedValue({ items: [], total: 0 });
});

describe("ClaimsOpportunitiesView", () => {
  it("shows the honest empty state instead of creating a claim from synthetic-only evidence", () => {
    const synthetic = makeEvidence({
      id: "synthetic-only",
      revisionId: "synthetic-only-rev-1",
      syntheticDemo: true,
      quote: "This sample quote must not become a claim.",
    });

    render(
      <ClaimsOpportunitiesView
        evidence={[synthetic]}
        t={translator("en")}
        onOpenEvidence={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "No claim can be formed yet" })).toBeVisible();
    expect(screen.getByText("1 synthetic item(s) excluded")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Claim drafts" })).not.toBeInTheDocument();
    expect(screen.queryByText(synthetic.quote)).not.toBeInTheDocument();
  });

  it("renders the original quote and opens the exact evidence revision from an edge", async () => {
    const user = userEvent.setup();
    const onOpenEvidence = vi.fn();
    const evidence = makeEvidence({
      id: "traceable-evidence",
      revisionId: "evidence-revision-7",
      sourceId: "interview-source",
      sourceRevisionId: "source-revision-3",
      title: "Classification and routing needs context",
      interpretation: "Human context is needed for accurate routing.",
      quote: "Keep this exact source sentence — 不要翻译这条原文。",
      tags: ["routing"],
    });

    render(
      <ClaimsOpportunitiesView
        evidence={[evidence]}
        t={translator("en")}
        onOpenEvidence={onOpenEvidence}
      />,
    );

    expect(screen.getByText(evidence.quote)).toBeVisible();
    expect(screen.getByTitle("Evidence rev.")).toHaveTextContent("evidence-revision-7");
    expect(screen.getByTitle("Source rev.")).toHaveTextContent("source-revision-3");

    await user.click(screen.getByRole("button", { name: "Open evidence" }));

    expect(onOpenEvidence).toHaveBeenCalledTimes(1);
    expect(onOpenEvidence).toHaveBeenCalledWith(evidence);
    expect(onOpenEvidence.mock.calls[0][0].revisionId).toBe("evidence-revision-7");
  });

  it("translates product chrome without translating or replacing source quotes", () => {
    const originalQuote = "The analyst said: keep the original wording intact.";
    const evidence = makeEvidence({
      id: "language-safe-evidence",
      revisionId: "language-safe-evidence-rev-2",
      sourceRevisionId: "language-safe-source-rev-5",
      title: "Onboarding evidence",
      quote: originalQuote,
      tags: ["onboarding"],
    });
    const { rerender } = render(
      <ClaimsOpportunitiesView
        evidence={[evidence]}
        t={translator("en")}
        onOpenEvidence={vi.fn()}
      />,
    );

    expect(screen.getByText(originalQuote)).toHaveTextContent(originalQuote);
    expect(screen.getByRole("button", { name: "Open evidence" })).toBeVisible();
    expect(screen.getAllByText("Onboarding")).toHaveLength(2);

    rerender(
      <ClaimsOpportunitiesView
        evidence={[evidence]}
        t={translator("zh-CN")}
        onOpenEvidence={vi.fn()}
      />,
    );

    expect(screen.getByText(originalQuote)).toHaveTextContent(originalQuote);
    expect(screen.getByRole("button", { name: "打开证据" })).toBeVisible();
    expect(screen.getAllByText("上手引导")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Open evidence" })).not.toBeInTheDocument();
  });

  it("requires a human relation, rationale and explicit confirmations before persisting", async () => {
    const user = userEvent.setup();
    const evidence = makeEvidence({
      id: "reviewed-evidence",
      revisionId: "reviewed-evidence-revision-4",
      sourceRevisionId: "reviewed-source-revision-2",
      reviewStatus: "approved",
      relationship: "supports",
      syntheticDemo: false,
      tags: ["onboarding"],
    });
    const study = {
      id: evidence.studyId,
      title: "Onboarding study",
      decisionQuestion: "Where is onboarding unclear?",
      status: "active" as const,
      updatedAt: "2026-07-16T00:00:00Z",
      sourceCount: 1,
      evidenceCount: 1,
    };
    apiMocks.createClaim.mockResolvedValue(makeClaim({ studyId: study.id }));

    render(
      <ClaimsOpportunitiesView
        evidence={[evidence]}
        study={study}
        live
        t={translator("en")}
        onOpenEvidence={vi.fn()}
      />,
    );

    const save = await screen.findByRole("button", { name: "Save for review" });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("Claim rationale"), "This groups one exact, reviewed quote for human review.");
    await user.selectOptions(screen.getByLabelText("Human-selected relation"), "contextualizes");
    await user.type(
      screen.getByLabelText("Why does this exact evidence revision have this relation?"),
      "The quote establishes the relevant onboarding context.",
    );
    await user.click(screen.getByRole("checkbox", { name: /explicitly confirm this semantic relation/i }));
    await user.click(screen.getByRole("checkbox", { name: /every edge is tied to the displayed immutable revision/i }));
    expect(save).toBeEnabled();
    await user.click(save);

    expect(apiMocks.createClaim).toHaveBeenCalledTimes(1);
    expect(apiMocks.createClaim.mock.calls[0][1]).toMatchObject({
      topicKey: "onboarding",
      rationale: "This groups one exact, reviewed quote for human review.",
      evidenceEdges: [{
        evidenceRevisionId: "reviewed-evidence-revision-4",
        relation: "contextualizes",
        relationConfirmed: true,
        rationale: "The quote establishes the relevant onboarding context.",
      }],
    });
  });

  it("lists persisted drafts separately and authors against the exact reviewed Claim Revision", async () => {
    const study = {
      id: "study-opportunity",
      title: "Risk workflow study",
      decisionQuestion: "Where do reviewers miss risk?",
      status: "active" as const,
      updatedAt: "2026-07-16T00:00:00Z",
      sourceCount: 1,
      evidenceCount: 1,
    };
    const claim = makeClaim({
      id: "claim-reviewed",
      claimId: "claim-reviewed",
      studyId: study.id,
      claimRevisionId: "claim-revision-reviewed-7",
      revisionId: "claim-revision-reviewed-7",
      status: "REVIEWED",
      revisionStatus: "REVIEWED",
      isCurrent: true,
      statement: "Reviewers need exact citations before escalating risk.",
      counterevidenceStatus: "NOT_RUN",
    });
    const savedDraft = {
      id: "opportunity-saved-1",
      studyId: study.id,
      claimId: claim.claimId,
      claimRevisionId: claim.claimRevisionId,
      status: "DRAFT" as const,
      title: "Citation-first assisted triage",
      problemStatement: "Reviewers miss material signals when records are isolated.",
      desiredOutcome: "Help reviewers recognize risk earlier.",
      nextStep: "Test with five support specialists.",
      rationale: "The exact reviewed claim bounds the problem.",
      confidence: 0.74,
      assumptions: ["Reviewers can act on citations."],
      risks: ["Automation bias"],
      provenance: { authoring_mode: "human" },
      contentHash: "opportunity-hash",
      clientRequestId: "saved-request",
      createdAt: "2026-07-16T00:00:00Z",
      claimStatement: claim.statement,
      claimContextUrl: `/v1/claims/${claim.claimId}?claim_revision_id=${claim.claimRevisionId}`,
      publishable: false as const,
      publicationBlockers: ["OPPORTUNITY_DRAFT_NOT_PUBLISHED", "COUNTEREVIDENCE_NOT_RUN"],
    };
    apiMocks.getClaims.mockResolvedValue({ items: [claim], total: 1 });
    apiMocks.getOpportunities.mockResolvedValue({ items: [savedDraft], total: 1 });
    apiMocks.createOpportunity.mockResolvedValue({ ...savedDraft, id: "opportunity-new-2" });

    render(
      <ClaimsOpportunitiesView
        evidence={[]}
        study={study}
        live
        t={translator("en")}
        onOpenEvidence={vi.fn()}
      />,
    );

    expect(await screen.findByRole("heading", { name: savedDraft.title })).toBeVisible();
    expect(screen.getByText("DRAFT")).toBeVisible();
    expect(screen.getByText("Not publishable")).toBeVisible();
    expect(screen.getByText("COUNTEREVIDENCE_NOT_RUN")).toBeVisible();
    expect(screen.getByText("Counterevidence search has not run")).toBeVisible();

    fireEvent.change(screen.getByLabelText("Opportunity title"), { target: { value: "Human escalation workspace" } });
    fireEvent.change(screen.getByLabelText("Problem statement"), { target: { value: "Reviewers cannot inspect risk context quickly." } });
    fireEvent.change(screen.getByLabelText("Desired outcome"), { target: { value: "Reduce missed escalations without hiding citations." } });
    fireEvent.change(screen.getByLabelText("Next validation step"), { target: { value: "Shadow five reviewers for one week." } });
    fireEvent.change(screen.getByLabelText("Assumptions"), { target: { value: "Reviewers trust exact citations.\nReviewers trust exact citations." } });
    fireEvent.change(screen.getByLabelText("Risks"), { target: { value: "Automation bias" } });
    fireEvent.click(screen.getByRole("button", { name: "Save opportunity draft" }));

    await vi.waitFor(() => expect(apiMocks.createOpportunity).toHaveBeenCalledTimes(1));
    expect(apiMocks.createOpportunity.mock.calls[0][1]).toMatchObject({
      claimId: claim.claimId,
      claimRevisionId: "claim-revision-reviewed-7",
      title: "Human escalation workspace",
      assumptions: ["Reviewers trust exact citations."],
      risks: ["Automation bias"],
      provenance: {
        authoring_mode: "human",
        surface: "claims_opportunities_workspace",
      },
    });
  });

  it("does not expose the authoring form for a proposed or stale claim", async () => {
    const study = {
      id: "study-ineligible",
      title: "Ineligible claim study",
      decisionQuestion: "What can we responsibly test?",
      status: "active" as const,
      updatedAt: "2026-07-16T00:00:00Z",
      sourceCount: 0,
      evidenceCount: 0,
    };
    apiMocks.getClaims.mockResolvedValue({
      items: [makeClaim({ studyId: study.id, status: "PROPOSED", revisionStatus: "PROPOSED" })],
      total: 1,
    });

    render(
      <ClaimsOpportunitiesView
        evidence={[]}
        study={study}
        live
        t={translator("en")}
        onOpenEvidence={vi.fn()}
      />,
    );

    expect(await screen.findByText("This claim cannot author an opportunity")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Create an opportunity draft" })).not.toBeInTheDocument();
  });

  it("drops a late Opportunity response after the active Study changes", async () => {
    const oldDraft = [{
      id: "old-opportunity",
      studyId: "study-old",
      claimId: "claim-old",
      claimRevisionId: "claim-revision-old",
      status: "DRAFT" as const,
      title: "Late old-study opportunity",
      problemStatement: "Old problem",
      desiredOutcome: "Old outcome",
      nextStep: "Old next step",
      rationale: null,
      confidence: 0.5,
      assumptions: [],
      risks: [],
      provenance: {},
      contentHash: "old-hash",
      clientRequestId: "old-request",
      createdAt: "2026-07-16T00:00:00Z",
      claimStatement: "Old claim",
      claimContextUrl: "/v1/claims/claim-old?claim_revision_id=claim-revision-old",
      publishable: false as const,
      publicationBlockers: ["OPPORTUNITY_DRAFT_NOT_PUBLISHED"],
    }];
    let resolveFirst: ((value: { items: typeof oldDraft; total: number }) => void) | undefined;
    apiMocks.getOpportunities.mockImplementation((studyId: string) => {
      if (studyId === "study-old") {
        return new Promise<{ items: typeof oldDraft; total: number }>((resolve) => { resolveFirst = resolve; });
      }
      return Promise.resolve({ items: [], total: 0 });
    });
    const oldStudy = { id: "study-old", title: "Old", decisionQuestion: "Old?", status: "active" as const, updatedAt: "2026-07-16T00:00:00Z", sourceCount: 0, evidenceCount: 0 };
    const newStudy = { ...oldStudy, id: "study-new", title: "New", decisionQuestion: "New?" };
    const view = render(<ClaimsOpportunitiesView evidence={[]} study={oldStudy} live t={translator("en")} onOpenEvidence={vi.fn()} />);

    await vi.waitFor(() => expect(apiMocks.getOpportunities).toHaveBeenCalledWith("study-old"));
    view.rerender(<ClaimsOpportunitiesView evidence={[]} study={newStudy} live t={translator("en")} onOpenEvidence={vi.fn()} />);
    await vi.waitFor(() => expect(apiMocks.getOpportunities).toHaveBeenCalledWith("study-new"));
    resolveFirst?.({ items: oldDraft, total: 1 });
    fireEvent.click(screen.getByRole("button", { name: "Refresh saved opportunities" }));
    await vi.waitFor(() => expect(screen.getByText("No opportunity draft has been saved for this study yet.")).toBeVisible());
    expect(screen.queryByText("Late old-study opportunity")).not.toBeInTheDocument();
  });
});
