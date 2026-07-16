import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useOpportunities } from "../hooks/use-opportunities";
import type { Claim, OpportunityDraftInput } from "../lib/api";
import { makeClaim } from "./claim-fixture";

const apiMocks = vi.hoisted(() => ({
  getOpportunities: vi.fn(),
  createOpportunity: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: { ...actual.api, ...apiMocks } };
});

function inputFor(claim: Claim): OpportunityDraftInput {
  return {
    claimId: claim.claimId,
    claimRevisionId: claim.claimRevisionId,
    title: "Bounded opportunity",
    problemStatement: "A reviewed workflow problem.",
    desiredOutcome: "A measurable human outcome.",
    nextStep: "Run a bounded validation.",
    rationale: null,
    confidence: 0.5,
    assumptions: [],
    risks: [],
    provenance: { authoring_mode: "human" },
    clientRequestId: "stable-opportunity-request",
  };
}

function Harness({ studyId, claim }: { studyId: string; claim: Claim }) {
  const state = useOpportunities(studyId, true);
  return (
    <div>
      <output data-testid="opportunity-error">{state.error ?? ""}</output>
      <button
        type="button"
        onClick={() => void state.createOpportunity(claim, inputFor(claim)).catch(() => undefined)}
      >
        Create
      </button>
    </div>
  );
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.getOpportunities.mockResolvedValue({ items: [], total: 0 });
});

describe("useOpportunities Study isolation", () => {
  it("does not leak a late create rejection into the next Study", async () => {
    const user = userEvent.setup();
    let rejectOld: ((error: Error) => void) | undefined;
    apiMocks.createOpportunity.mockImplementation(() => new Promise((_, reject) => {
      rejectOld = reject;
    }));
    const oldClaim = makeClaim({
      studyId: "study-old",
      status: "REVIEWED",
      revisionStatus: "REVIEWED",
      isCurrent: true,
    });
    const newClaim = makeClaim({
      claimId: "claim-new",
      id: "claim-new",
      studyId: "study-new",
      status: "REVIEWED",
      revisionStatus: "REVIEWED",
      isCurrent: true,
    });
    const view = render(<Harness studyId="study-old" claim={oldClaim} />);
    await user.click(screen.getByRole("button", { name: "Create" }));
    await vi.waitFor(() => expect(apiMocks.createOpportunity).toHaveBeenCalledTimes(1));

    view.rerender(<Harness studyId="study-new" claim={newClaim} />);
    rejectOld?.(new Error("Late failure from study-old"));

    await vi.waitFor(() => expect(apiMocks.getOpportunities).toHaveBeenCalledWith("study-new"));
    expect(screen.getByTestId("opportunity-error")).toHaveTextContent("");
    expect(screen.queryByText("Late failure from study-old")).not.toBeInTheDocument();
  });
});
