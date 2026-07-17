"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  ApiError,
  type Claim,
  type OpportunityDraft,
  type OpportunityDraftInput,
} from "@/lib/api";

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown opportunity API error";
}

export function useOpportunities(studyId: string | null, enabled = true) {
  const [opportunities, setOpportunities] = useState<OpportunityDraft[]>([]);
  const [opportunitiesStudyId, setOpportunitiesStudyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingActions, setPendingActions] = useState<ReadonlySet<string>>(new Set());
  const generation = useRef(0);
  const studyGeneration = useRef(0);
  const activeStudyId = useRef<string | null>(studyId);
  const actionLocks = useRef(new Set<string>());

  useEffect(() => {
    activeStudyId.current = studyId;
    generation.current += 1;
    studyGeneration.current += 1;
    actionLocks.current.clear();
    const timer = window.setTimeout(() => {
      setPendingActions(new Set());
      setError(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [studyId]);

  const reload = useCallback(async () => {
    if (!enabled || !studyId) {
      setOpportunities([]);
      setLoading(false);
      return;
    }
    const requestGeneration = ++generation.current;
    const requestedStudyId = studyId;
    setLoading(true);
    setError(null);
    try {
      const result = await api.getOpportunities(requestedStudyId);
      if (
        generation.current !== requestGeneration
        || activeStudyId.current !== requestedStudyId
      ) return;
      if (result.items.some((draft) => draft.studyId !== requestedStudyId)) {
        throw new ApiError(
          "The opportunities response contains data from another study.",
          undefined,
          "cross_study_response",
        );
      }
      setOpportunities(result.items);
      setOpportunitiesStudyId(requestedStudyId);
    } catch (loadError) {
      if (
        generation.current !== requestGeneration
        || activeStudyId.current !== requestedStudyId
      ) return;
      setOpportunities([]);
      setOpportunitiesStudyId(requestedStudyId);
      setError(messageOf(loadError));
    } finally {
      if (
        generation.current === requestGeneration
        && activeStudyId.current === requestedStudyId
      ) setLoading(false);
    }
  }, [enabled, studyId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void reload(), 0);
    return () => window.clearTimeout(timer);
  }, [reload]);

  const createOpportunity = useCallback(async (
    claim: Claim,
    input: OpportunityDraftInput,
  ): Promise<OpportunityDraft> => {
    const requestedStudyId = studyId;
    const requestedStudyGeneration = studyGeneration.current;
    if (
      !requestedStudyId
      || activeStudyId.current !== requestedStudyId
      || claim.studyId !== requestedStudyId
      || input.claimId !== claim.claimId
      || input.claimRevisionId !== claim.claimRevisionId
    ) {
      throw new ApiError(
        "The opportunity does not belong to the active Claim Revision and Study.",
        undefined,
        "cross_study_request",
      );
    }
    if (
      !claim.isCurrent
      || claim.status !== "REVIEWED"
      || claim.revisionStatus !== "REVIEWED"
    ) {
      throw new ApiError(
        "Opportunity authoring requires the current reviewed, non-stale Claim Revision.",
        422,
        "invalid_opportunity_claim",
      );
    }

    const actionKey = `create:${input.clientRequestId}`;
    if (actionLocks.current.has(actionKey)) {
      throw new ApiError("This action is already in progress.", 409, "duplicate_submission");
    }
    actionLocks.current.add(actionKey);
    setPendingActions(new Set(actionLocks.current));
    setError(null);
    try {
      const draft = await api.createOpportunity(requestedStudyId, input);
      if (
        activeStudyId.current !== requestedStudyId
        || studyGeneration.current !== requestedStudyGeneration
        || draft.studyId !== requestedStudyId
        || draft.claimId !== claim.claimId
        || draft.claimRevisionId !== claim.claimRevisionId
      ) {
        throw new ApiError(
          "Opportunity creation crossed the Claim Revision or Study boundary.",
          undefined,
          "cross_study_response",
        );
      }
      setOpportunities((current) => [
        draft,
        ...current.filter((item) => item.id !== draft.id),
      ]);
      setOpportunitiesStudyId(requestedStudyId);
      return draft;
    } catch (actionError) {
      if (
        activeStudyId.current === requestedStudyId
        && studyGeneration.current === requestedStudyGeneration
      ) setError(messageOf(actionError));
      throw actionError;
    } finally {
      if (studyGeneration.current === requestedStudyGeneration) {
        actionLocks.current.delete(actionKey);
        setPendingActions(new Set(actionLocks.current));
      }
    }
  }, [studyId]);

  return {
    opportunities: opportunitiesStudyId === studyId ? opportunities : [],
    loading,
    error,
    pendingActions,
    reload,
    createOpportunity,
  };
}
