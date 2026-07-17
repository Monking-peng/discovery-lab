import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../lib/api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function suite(dataset: string, caseId: string) {
  return {
    schema_version: `${dataset}.v2`,
    dataset,
    dataset_revision: 2,
    generated_at: "2026-07-16T00:00:00Z",
    summary: { case_count: 1, passed: 1, failed: 0, replay_rate: 1 },
    cases: [{
      case_id: caseId,
      status: "passed",
      assertions: { exact_revision_replayed: true },
      details: { revision_id: "revision-1" },
    }],
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("strict Evaluation API client", () => {
  it("normalizes the release gate, exact cases, and bad-case regression links", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        schema_version: "evaluation-report-index.v1",
        generated_at: "2026-07-16T00:00:00Z",
        total_cases: 2,
        passed: 2,
        failed: 0,
        skipped: 0,
        release_gate_passed: true,
        dataset_revisions: {
          "helphub-source-to-evidence": 2,
          "evidence-to-claim-integrity": 2,
        },
        source_to_evidence: suite("helphub-source-to-evidence", "source-case"),
        evidence_to_claim: suite("evidence-to-claim-integrity", "claim-case"),
      }))
      .mockResolvedValueOnce(jsonResponse({
        schema_version: "bad-case-inbox.v1",
        generated_at: "2026-07-16T00:00:00Z",
        total: 1,
        unresolved: 0,
        items: [{
          schema_version: "bad-case.v1",
          id: "csv-trailing-blank-line",
          discovered_at: "2026-07-15T23:31:55+08:00",
          stage: "parse_source",
          severity: "medium",
          fixture: "fixtures/helphub/tickets.csv",
          symptom: "A trailing blank row failed validation.",
          safe_error_code: "invalid_source",
          root_cause: "An empty physical row was counted.",
          resolution: "Ignore only fully blank rows.",
          regression_test: "tests/ingestion/test_parsers.py::test_blank_rows",
          recovery_verified: true,
          data_loss: false,
        }],
      }));
    vi.stubGlobal("fetch", fetchMock);

    const report = await api.getCurrentEvaluationReport();
    const inbox = await api.getBadCases();

    expect(report).toMatchObject({
      totalCases: 2,
      passed: 2,
      releaseGatePassed: true,
      sourceToEvidence: {
        dataset: "helphub-source-to-evidence",
        cases: [{ caseId: "source-case", status: "passed" }],
      },
    });
    expect(inbox.items[0]).toMatchObject({
      id: "csv-trailing-blank-line",
      fixture: "fixtures/helphub/tickets.csv",
      regressionTest: "tests/ingestion/test_parsers.py::test_blank_rows",
      recoveryVerified: true,
    });
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      expect.stringContaining("/v1/evaluation/reports/current"),
      expect.stringContaining("/v1/evaluation/bad-cases"),
    ]);
  });

  it("fails closed when aggregate counts disagree with the executable cases", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      schema_version: "evaluation-report-index.v1",
      generated_at: "2026-07-16T00:00:00Z",
      total_cases: 99,
      passed: 2,
      failed: 0,
      skipped: 0,
      release_gate_passed: true,
      dataset_revisions: {
        "helphub-source-to-evidence": 2,
        "evidence-to-claim-integrity": 2,
      },
      source_to_evidence: suite("helphub-source-to-evidence", "source-case"),
      evidence_to_claim: suite("evidence-to-claim-integrity", "claim-case"),
    })));

    await expect(api.getCurrentEvaluationReport()).rejects.toMatchObject({
      code: "invalid_response",
      details: { field: "evaluation_report.total_cases" },
    });
  });
});
