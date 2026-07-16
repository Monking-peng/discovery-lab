"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  ApiError,
  type ArtifactReviewInput,
  type Claim,
  type ClaimReview,
  type ClaimRevisionInput,
} from "@/lib/api";

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown claim API error";
}

export function useClaims(studyId: string | null, enabled = true) {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [claimsStudyId, setClaimsStudyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingActions, setPendingActions] = useState<ReadonlySet<string>>(new Set());
  const generation = useRef(0);
  const activeStudyId = useRef<string | null>(studyId);
  const actionLocks = useRef(new Set<string>());

  useEffect(() => {
    activeStudyId.current = studyId;
    generation.current += 1;
    actionLocks.current.clear();
    const timer = window.setTimeout(() => {
      setPendingActions(new Set());
      setError(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [studyId]);

  const reload = useCallback(async () => {
    if (!enabled || !studyId) {
      setClaims([]);
      setLoading(false);
      return;
    }
    const requestGeneration = ++generation.current;
    const requestedStudyId = studyId;
    setLoading(true);
    setError(null);
    try {
      const result = await api.getClaims(requestedStudyId);
      if (generation.current !== requestGeneration || activeStudyId.current !== requestedStudyId) return;
      if (result.items.some((claim) => claim.studyId !== requestedStudyId)) {
        throw new ApiError(
          "The claims response contains data from another study.",
          undefined,
          "cross_study_response",
        );
      }
      setClaims(result.items);
      setClaimsStudyId(requestedStudyId);
    } catch (loadError) {
      if (generation.current !== requestGeneration || activeStudyId.current !== requestedStudyId) return;
      setClaims([]);
      setClaimsStudyId(requestedStudyId);
      setError(messageOf(loadError));
    } finally {
      if (generation.current === requestGeneration && activeStudyId.current === requestedStudyId) {
        setLoading(false);
      }
    }
  }, [enabled, studyId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void reload(), 0);
    return () => window.clearTimeout(timer);
  }, [reload]);

  const runLocked = useCallback(async <T,>(key: string, action: () => Promise<T>): Promise<T> => {
    if (actionLocks.current.has(key)) {
      throw new ApiError("This action is already in progress.", 409, "duplicate_submission");
    }
    actionLocks.current.add(key);
    setPendingActions(new Set(actionLocks.current));
    setError(null);
    try {
      return await action();
    } catch (actionError) {
      setError(messageOf(actionError));
      throw actionError;
    } finally {
      actionLocks.current.delete(key);
      setPendingActions(new Set(actionLocks.current));
    }
  }, []);

  const createClaim = useCallback(async (input: ClaimRevisionInput): Promise<Claim> => {
    if (!studyId || activeStudyId.current !== studyId) {
      throw new ApiError("No active study is selected.", undefined, "study_required");
    }
    const requestedStudyId = studyId;
    return runLocked(`create:${input.clientRequestId}`, async () => {
      const claim = await api.createClaim(requestedStudyId, input);
      if (activeStudyId.current !== requestedStudyId || claim.studyId !== requestedStudyId) {
        throw new ApiError("Claim creation crossed the study boundary.", undefined, "cross_study_response");
      }
      setClaims((current) => [claim, ...current.filter((item) => item.claimId !== claim.claimId)]);
      setClaimsStudyId(requestedStudyId);
      return claim;
    });
  }, [runLocked, studyId]);

  const createRevision = useCallback(async (
    claim: Claim,
    input: ClaimRevisionInput,
  ): Promise<Claim> => {
    const requestedStudyId = studyId;
    if (!requestedStudyId || claim.studyId !== requestedStudyId || activeStudyId.current !== requestedStudyId) {
      throw new ApiError("The claim does not belong to the active study.", undefined, "cross_study_request");
    }
    return runLocked(`revision:${claim.claimId}:${input.clientRequestId}`, async () => {
      const revised = await api.createClaimRevision(claim.claimId, claim.claimRevisionId, input);
      if (activeStudyId.current !== requestedStudyId || revised.studyId !== requestedStudyId) {
        throw new ApiError("Claim revision crossed the study boundary.", undefined, "cross_study_response");
      }
      setClaims((current) => current.map((item) => item.claimId === revised.claimId ? revised : item));
      return revised;
    });
  }, [runLocked, studyId]);

  const reviewRevision = useCallback(async (
    claim: Claim,
    input: ArtifactReviewInput,
  ): Promise<ClaimReview> => runLocked(
    `review:${claim.claimRevisionId}:${input.clientRequestId}`,
    async () => {
      if (!studyId || claim.studyId !== studyId || activeStudyId.current !== studyId) {
        throw new ApiError("The claim does not belong to the active study.", undefined, "cross_study_request");
      }
      const review = await api.reviewClaimRevision(claim.claimRevisionId, input);
      await reload();
      return review;
    },
  ), [reload, runLocked, studyId]);

  const loadExactRevision = useCallback(async (
    claimId: string,
    claimRevisionId: string,
  ): Promise<Claim> => runLocked(`replay:${claimId}:${claimRevisionId}`, async () => {
    const requestedStudyId = studyId;
    if (!requestedStudyId || activeStudyId.current !== requestedStudyId) {
      throw new ApiError("No active study is selected.", undefined, "study_required");
    }
    const snapshot = await api.getClaim(claimId, claimRevisionId);
    if (activeStudyId.current !== requestedStudyId || snapshot.studyId !== requestedStudyId) {
      throw new ApiError("Claim replay crossed the study boundary.", undefined, "cross_study_response");
    }
    return snapshot;
  }), [runLocked, studyId]);

  return {
    claims: claimsStudyId === studyId ? claims : [],
    loading,
    error,
    pendingActions,
    reload,
    createClaim,
    createRevision,
    reviewRevision,
    loadExactRevision,
  };
}
