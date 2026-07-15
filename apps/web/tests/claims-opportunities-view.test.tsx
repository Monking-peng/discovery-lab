import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ClaimsOpportunitiesView, type ClaimsTranslator } from "../components/claims-opportunities-view";
import { translate, type Locale } from "../lib/i18n";
import { makeEvidence } from "./evidence-fixture";

function translator(locale: Locale): ClaimsTranslator {
  return (key, vars) => translate(locale, key, vars);
}

afterEach(cleanup);

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

    rerender(
      <ClaimsOpportunitiesView
        evidence={[evidence]}
        t={translator("zh-CN")}
        onOpenEvidence={vi.fn()}
      />,
    );

    expect(screen.getByText(originalQuote)).toHaveTextContent(originalQuote);
    expect(screen.getByRole("button", { name: "打开证据" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Open evidence" })).not.toBeInTheDocument();
  });
});
