import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EvaluationCenter } from "../components/evaluation-center";
import type { BadCaseInbox, CurrentEvaluationReport } from "../lib/api";
import { translate } from "../lib/i18n";

const apiMocks = vi.hoisted(() => ({
  getCurrentEvaluationReport: vi.fn(),
  getBadCases: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: { ...actual.api, ...apiMocks } };
});

const t = (key: Parameters<typeof translate>[1], vars?: Parameters<typeof translate>[2]) => (
  translate("en", key, vars)
);

function report(): CurrentEvaluationReport {
  const sourceCase = {
    caseId: "source-prompt-injection",
    status: "passed" as const,
    assertions: { attack_text_absent_from_graph_control_state: true },
    details: { workflow_nodes: ["parse", "extract", "verify"] },
  };
  const claimCase = {
    caseId: "old-revision-replays-by-exact-identity",
    status: "passed" as const,
    assertions: { requested_revision_replayed_exactly: true },
    details: { exact_revision_replay: true },
  };
  return {
    schemaVersion: "evaluation-report-index.v1",
    generatedAt: "2026-07-16T00:00:00Z",
    totalCases: 2,
    passed: 2,
    failed: 0,
    skipped: 0,
    releaseGatePassed: true,
    datasetRevisions: {
      "helphub-source-to-evidence": 2,
      "evidence-to-claim-integrity": 2,
    },
    sourceToEvidence: {
      schemaVersion: "source-to-evidence-eval.v2",
      dataset: "helphub-source-to-evidence",
      datasetRevision: 2,
      generatedAt: "2026-07-16T00:00:00Z",
      summary: { case_count: 1, passed: 1, failed: 0 },
      cases: [sourceCase],
    },
    evidenceToClaim: {
      schemaVersion: "evidence-to-claim-eval.v2",
      dataset: "evidence-to-claim-integrity",
      datasetRevision: 2,
      generatedAt: "2026-07-16T00:00:00Z",
      summary: { case_count: 1, passed: 1, failed: 0 },
      cases: [claimCase],
    },
  };
}

function inbox(): BadCaseInbox {
  return {
    schemaVersion: "bad-case-inbox.v1",
    generatedAt: "2026-07-16T00:00:00Z",
    total: 1,
    unresolved: 0,
    items: [{
      schemaVersion: "bad-case.v1",
      id: "csv-trailing-blank-line",
      discoveredAt: "2026-07-15T23:31:55+08:00",
      stage: "parse_source",
      severity: "medium",
      fixture: "fixtures/helphub/tickets.csv",
      symptom: "A trailing blank row failed validation.",
      safeErrorCode: "invalid_source",
      rootCause: "An empty physical row was counted.",
      resolution: "Ignore only fully blank rows.",
      regressionTest: "tests/ingestion/test_parsers.py::test_blank_rows",
      recoveryVerified: true,
      dataLoss: false,
    }],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.getCurrentEvaluationReport.mockResolvedValue(report());
  apiMocks.getBadCases.mockResolvedValue(inbox());
});
afterEach(() => cleanup());

describe("Evaluation & Bad Case Center", () => {
  it("shows the executable release gate, dataset revisions, cases, and verified recovery", async () => {
    const user = userEvent.setup();
    render(<EvaluationCenter live t={t} />);

    expect(await screen.findByText(t("eval.gatePassed"))).toBeVisible();
    expect(screen.getByText(t("eval.totalCases", { count: 2 }))).toBeVisible();
    expect(screen.getByText("helphub-source-to-evidence")).toBeVisible();
    expect(screen.getByText("evidence-to-claim-integrity")).toBeVisible();
    expect(screen.getByText("source-prompt-injection")).toBeVisible();
    expect(screen.getByText("old-revision-replays-by-exact-identity")).toBeVisible();
    expect(screen.getByText("csv-trailing-blank-line")).toBeVisible();
    expect(screen.getByText("fixtures/helphub/tickets.csv")).toBeVisible();
    expect(screen.getByText(t("eval.recoveryVerified"))).toBeVisible();

    await user.click(screen.getByRole("button", { name: t("eval.refresh") }));
    await waitFor(() => expect(apiMocks.getCurrentEvaluationReport).toHaveBeenCalledTimes(2));
    expect(apiMocks.getBadCases).toHaveBeenCalledTimes(2);
  });

  it("never presents preview data as a real evaluation report", () => {
    render(<EvaluationCenter live={false} t={t} />);
    expect(screen.getByText(t("eval.liveOnly"))).toBeVisible();
    expect(apiMocks.getCurrentEvaluationReport).not.toHaveBeenCalled();
    expect(apiMocks.getBadCases).not.toHaveBeenCalled();
  });
});
