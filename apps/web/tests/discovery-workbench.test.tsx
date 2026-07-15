import { cleanup, render, screen, waitFor } from "@testing-library/react";
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

const apiMocks = vi.hoisted(() => ({
  getStudies: vi.fn(),
  createStudy: vi.fn(),
  getEvidence: vi.fn(),
  getSources: vi.fn(),
  getRuns: vi.fn(),
  getEvidenceContext: vi.fn(),
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
}

async function renderLiveWorkbench() {
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
});
