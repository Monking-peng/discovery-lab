"use client";

import {
  AlertCircle,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  CircleDotDashed,
  GitBranch,
  History,
  Lightbulb,
  Link2,
  LoaderCircle,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import { useClaims } from "@/hooks/use-claims";
import { useOpportunities } from "@/hooks/use-opportunities";
import {
  CLAIM_RELATIONS,
  type Claim,
  type ClaimEvidenceRelation,
  type ClaimRevisionInput,
  type ClaimReviewDecision,
  type CounterevidenceStatus,
  type Evidence,
  type OpportunityDraft as SavedOpportunityDraft,
  type OpportunityDraftInput,
  type Study,
} from "@/lib/api";
import type { MessageKey, TranslationVars } from "@/lib/i18n";
import {
  deriveInsights,
  type ClaimDraft,
  type InsightGap,
  type InsightGapCode,
  type InsightRelation,
  type InsightStrengthLevel,
  type OpportunityDraft as OpportunityPreview,
} from "@/lib/insights";

export type ClaimsTranslator = (key: MessageKey, vars?: TranslationVars) => string;

export type ClaimsOpportunitiesViewProps = {
  evidence: readonly Evidence[];
  study?: Study | null;
  t: ClaimsTranslator;
  live?: boolean;
  onOpenEvidence: (evidence: Evidence) => void;
  onOpenEvidenceRevision?: (evidenceId: string, evidenceRevisionId: string) => void;
};

type EditableEdge = {
  relation: ClaimEvidenceRelation | "";
  rationale: string;
  confirmed: boolean;
};

const gapMessageKeys: Record<InsightGapCode, MessageKey> = {
  no_evidence: "gap.noEvidence",
  synthetic_evidence_excluded: "gap.syntheticExcluded",
  untraceable_evidence_excluded: "gap.untraceableExcluded",
  rejected_or_stale_evidence_excluded: "gap.rejectedExcluded",
  no_reviewed_evidence: "gap.noReviewed",
  insufficient_support: "gap.insufficientSupport",
  counterevidence_missing: "gap.counterMissing",
  single_source: "gap.singleSource",
  review_required: "gap.reviewRequired",
  low_confidence: "gap.lowConfidence",
  semantic_support_unverified: "gap.semanticUnverified",
  cohort_coverage_unavailable: "gap.cohortUnavailable",
};

const strengthMessageKeys: Record<InsightStrengthLevel, MessageKey> = {
  strong: "strength.strong",
  moderate: "strength.moderate",
  weak: "strength.weak",
  insufficient: "strength.insufficient",
};

const suggestedRelationMessageKeys: Record<InsightRelation, MessageKey> = {
  supports: "relation.supports",
  challenges: "relation.challenges",
  contextualizes: "relation.contextualizes",
};

const relationMessageKeys: Record<ClaimEvidenceRelation, MessageKey> = {
  supports: "relation.supports",
  contradicts: "relation.contradicts",
  contextualizes: "relation.contextualizes",
  insufficient_for: "relation.insufficientFor",
};

const nextStepMessageKeys: Record<OpportunityPreview["nextStep"], MessageKey> = {
  collect_supporting_evidence: "next.collectSupporting",
  seek_counterevidence: "next.seekCounter",
  review_evidence: "next.review",
  frame_hypothesis: "next.hypothesis",
};

const topicMessageKeys: Readonly<Record<string, MessageKey>> = {
  "risk-escalation": "topic.riskEscalation",
  "auto-reply": "topic.autoReply",
  "classification-routing": "topic.classificationRouting",
  "explainability-governance": "topic.explainabilityGovernance",
  onboarding: "topic.onboarding",
  retention: "topic.retention",
  "kind-pain": "kind.pain",
  "kind-need": "kind.need",
  "kind-behavior": "kind.behavior",
  "kind-constraint": "kind.constraint",
  "kind-counterevidence": "kind.counterevidence",
  "kind-signal": "kind.signal",
};

function topicLabel(t: ClaimsTranslator, topicKey: string, fallback = topicKey): string {
  const messageKey = topicMessageKeys[topicKey];
  return messageKey ? t(messageKey) : fallback;
}

function gapLabel(t: ClaimsTranslator, gap: InsightGap): string {
  return t(gapMessageKeys[gap.code], { count: gap.count ?? 0 });
}

function requestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function StrengthSummary({ claim, t }: { claim: ClaimDraft; t: ClaimsTranslator }) {
  const strengthLabel = t(strengthMessageKeys[claim.strength.level]);
  return (
    <div className="insights-strength-row">
      <span>{t("claims.score", { score: claim.strength.score, level: strengthLabel })}</span>
      <span className="insights-strength-bar" role="meter" aria-label={t("claims.strength")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={claim.strength.score}>
        <span className="insights-strength-fill" style={{ width: `${claim.strength.score}%` }} />
      </span>
    </div>
  );
}

function DraftInspector({
  claim,
  t,
  canPersist,
  saving,
  onOpenRevision,
  onSave,
}: {
  claim: ClaimDraft;
  t: ClaimsTranslator;
  canPersist: boolean;
  saving: boolean;
  onOpenRevision: (evidenceId: string, revisionId: string) => void;
  onSave: (input: ClaimRevisionInput) => Promise<void>;
}) {
  const [statement, setStatement] = useState(claim.statement);
  const [summary, setSummary] = useState("");
  const [claimRationale, setClaimRationale] = useState("");
  const [finalConfirmation, setFinalConfirmation] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [edges, setEdges] = useState<Record<string, EditableEdge>>(() => Object.fromEntries(
    claim.edges.map((edge) => [`${edge.evidenceId}:${edge.evidenceRevisionId}`, {
      relation: "",
      rationale: "",
      confirmed: false,
    }]),
  ));

  const complete = claim.edges.every((edge) => {
    const value = edges[`${edge.evidenceId}:${edge.evidenceRevisionId}`];
    return Boolean(value?.relation && value.rationale.trim() && value.confirmed);
  });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canPersist || !complete || !finalConfirmation || !statement.trim() || !claimRationale.trim()) return;
    setSubmitError("");
    try {
      const evidenceEdges = claim.edges.map((edge) => {
        const state = edges[`${edge.evidenceId}:${edge.evidenceRevisionId}`];
        // Fail closed: an unconfirmed heuristic support can only be contextual context.
        const relation = state.confirmed && state.relation ? state.relation : "contextualizes";
        return {
          evidenceId: edge.evidenceId,
          evidenceRevisionId: edge.evidenceRevisionId,
          relation,
          rationale: state.rationale.trim(),
          relevance: Math.max(0, Math.min(1, edge.confidence)),
          relationConfirmed: state.confirmed,
        };
      });
      const hasCounterevidence = evidenceEdges.some((edge) => edge.relation === "contradicts");
      await onSave({
        topicKey: claim.topicKey,
        statement: statement.trim(),
        summary: summary.trim() || null,
        rationale: claimRationale.trim(),
        confidence: claim.strength.score / 100,
        counterevidenceStatus: hasCounterevidence ? "FOUND" : "NOT_RUN",
        counterevidenceSummary: hasCounterevidence ? t("claims.counterFound") : null,
        provenance: {
          producer: "deterministic_client_projection",
          projection_version: "claims-preview-v2",
          requires_human_review: true,
        },
        evidenceEdges,
        clientRequestId: requestId(),
      });
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : t("general.unknownError"));
    }
  }

  return (
    <article className="insights-inspector" aria-labelledby="selected-claim-title">
      <header className="insights-inspector-head">
        <div><span>{t("claims.statement")}</span><h2 id="selected-claim-title">{claim.statement}</h2></div>
        <span className="insights-preview-badge">{t("claims.nonPersisted")}</span>
      </header>
      <StrengthSummary claim={claim} t={t} />
      <form className="claim-save-form" onSubmit={submit}>
        <label>{t("claims.statement")}<textarea value={statement} onChange={(event) => setStatement(event.target.value)} rows={3} required /></label>
        <label>{t("claims.summaryOptional")}<textarea value={summary} onChange={(event) => setSummary(event.target.value)} rows={2} /></label>
        <label>{t("claims.claimRationale")}<textarea value={claimRationale} onChange={(event) => setClaimRationale(event.target.value)} rows={2} required /></label>

        <section aria-labelledby="evidence-edges-title">
          <div className="insights-panel-heading"><h3 id="evidence-edges-title">{t("claims.evidenceEdges")}</h3><strong>{claim.edges.length}</strong></div>
          <ul className="insights-edge-list">
            {claim.edges.map((edge) => {
              const key = `${edge.evidenceId}:${edge.evidenceRevisionId}`;
              const state = edges[key];
              return (
                <li key={key} className="insights-evidence-edge">
                  <div className="insights-edge-top">
                    <span>{t("claims.suggestedRelation")}: {t(suggestedRelationMessageKeys[edge.relation])}</span>
                    <code>{edge.evidenceRevisionId}</code>
                  </div>
                  <strong>{edge.title}</strong>
                  <blockquote className="insights-edge-quote">{edge.quote}</blockquote>
                  <div className="insights-edge-meta"><span>{edge.sourceName}</span><span>{edge.locatorLabel}</span><code title={t("detail.evidenceRevision")}>{edge.evidenceRevisionId}</code><code title={t("detail.sourceRevision")}>{edge.sourceRevisionId}</code></div>
                  <div className="claim-edge-controls">
                    <label>{t("claims.relationRequired")}
                      <select required value={state.relation} onChange={(event) => setEdges((current) => ({ ...current, [key]: { ...current[key], relation: event.target.value as ClaimEvidenceRelation } }))}>
                        <option value="">{t("claims.chooseRelation")}</option>
                        {CLAIM_RELATIONS.map((relation) => <option key={relation} value={relation}>{t(relationMessageKeys[relation])}</option>)}
                      </select>
                    </label>
                    <label>{t("claims.edgeRationale")}<textarea required value={state.rationale} onChange={(event) => setEdges((current) => ({ ...current, [key]: { ...current[key], rationale: event.target.value } }))} rows={2} /></label>
                    <label className="claim-confirm-row"><input type="checkbox" checked={state.confirmed} onChange={(event) => setEdges((current) => ({ ...current, [key]: { ...current[key], confirmed: event.target.checked } }))} />{t("claims.confirmRelation")}</label>
                  </div>
                  <button type="button" className="insights-open-evidence" onClick={() => onOpenRevision(edge.evidenceId, edge.evidenceRevisionId)}>{t("claims.openEvidence")}<ArrowUpRight size={15} /></button>
                </li>
              );
            })}
          </ul>
        </section>
        <label className="claim-confirm-row claim-final-confirm"><input type="checkbox" checked={finalConfirmation} onChange={(event) => setFinalConfirmation(event.target.checked)} />{t("claims.confirmSave")}</label>
        {!canPersist ? <p className="claim-form-note">{t("claims.liveOnly")}</p> : null}
        {submitError ? <p className="form-error" role="alert">{submitError}</p> : null}
        <button className="primary-button" type="submit" disabled={!canPersist || !complete || !finalConfirmation || !statement.trim() || !claimRationale.trim() || saving}>
          {saving ? <LoaderCircle className="spin" size={14} /> : <Save size={14} />}{t("claims.saveForReview")}
        </button>
      </form>
    </article>
  );
}

function PersistedClaimInspector({
  claim,
  t,
  busy,
  onOpenRevision,
  onReview,
  onRevise,
  onReplay,
}: {
  claim: Claim;
  t: ClaimsTranslator;
  busy: boolean;
  onOpenRevision: (evidenceId: string, revisionId: string) => void;
  onReview: (decision: ClaimReviewDecision, reviewer: string, rationale: string) => Promise<void>;
  onRevise: (claim: Claim, input: ClaimRevisionInput) => Promise<Claim>;
  onReplay: (claimId: string, revisionId: string) => Promise<Claim>;
}) {
  const [reviewer, setReviewer] = useState("");
  const [reviewRationale, setReviewRationale] = useState("");
  const [actionError, setActionError] = useState("");
  const [editing, setEditing] = useState(false);
  const [revisionId, setRevisionId] = useState("");
  const [historical, setHistorical] = useState<Claim | null>(null);
  const inspected = historical ?? claim;

  async function review(decision: ClaimReviewDecision) {
    if (!reviewer.trim() || ((decision === "REJECT" || decision === "REQUEST_CHANGES") && !reviewRationale.trim())) return;
    setActionError("");
    try {
      await onReview(decision, reviewer.trim(), reviewRationale.trim());
      setReviewRationale("");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : t("general.unknownError"));
    }
  }

  async function replay(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!revisionId.trim()) return;
    setActionError("");
    try {
      setHistorical(await onReplay(claim.claimId, revisionId.trim()));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : t("general.unknownError"));
    }
  }

  return (
    <article className="insights-inspector persisted-claim-inspector" aria-labelledby="persisted-claim-title">
      <header className="insights-inspector-head">
        <div><span>{t("claims.persisted")}</span><h2 id="persisted-claim-title">{inspected.statement}</h2></div>
        <span className={`claim-status status-${inspected.revisionStatus.toLowerCase()}`}>{t(`claimStatus.${inspected.revisionStatus}` as MessageKey)}</span>
      </header>
      {historical ? <div className="claim-history-banner"><History size={14} />{t("claims.historicalSnapshot")}<button type="button" className="text-button" onClick={() => setHistorical(null)}>{t("claims.returnLatest")}</button></div> : null}
      <dl className="claim-revision-facts">
        <div><dt>{t("claims.revision")}</dt><dd>r{inspected.revision}</dd></div>
        <div><dt>{t("claims.revisionId")}</dt><dd><code>{inspected.claimRevisionId}</code></dd></div>
        <div><dt>{t("claims.contentHash")}</dt><dd><code>{inspected.contentHash}</code></dd></div>
        <div><dt>{t("claims.counterevidence")}</dt><dd>{t(`counter.${inspected.counterevidenceStatus}` as MessageKey)}</dd></div>
      </dl>
      <p className="claim-rationale"><strong>{t("claims.claimRationale")}</strong>{inspected.rationale}</p>
      {inspected.publicationBlockers.length > 0 ? <div className="claim-blockers" role="status"><AlertTriangle size={15} /><div><strong>{t("claims.publicationBlocked")}</strong><ul>{inspected.publicationBlockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul></div></div> : null}

      <section aria-labelledby="persisted-edges-title">
        <div className="insights-panel-heading"><h3 id="persisted-edges-title">{t("claims.evidenceEdges")}</h3><strong>{inspected.evidenceEdges.length}</strong></div>
        <ul className="insights-edge-list">
          {inspected.evidenceEdges.map((edge) => (
            <li key={edge.id} className="insights-evidence-edge">
              <div className="insights-edge-top"><span className={`insights-edge-relation relation-${edge.relation}`}><Link2 size={13} />{t(relationMessageKeys[edge.relation])}</span><span>{edge.relationConfirmed ? t("claims.relationConfirmed") : t("claims.relationUnconfirmed")}</span></div>
              <p>{edge.rationale}</p>
              <div className="insights-edge-meta"><code>{edge.evidenceRevisionId}</code><code>{edge.sourceRevisionId}</code></div>
              <button type="button" className="insights-open-evidence" onClick={() => onOpenRevision(edge.evidenceId, edge.evidenceRevisionId)}>{t("claims.openEvidence")}<ArrowUpRight size={15} /></button>
            </li>
          ))}
        </ul>
      </section>

      <section className="claim-history-section" aria-labelledby="claim-history-title">
        <div className="insights-panel-heading"><h3 id="claim-history-title">{t("claims.history")}</h3></div>
        <form onSubmit={replay}><label>{t("claims.replayRevision")}<input value={revisionId} onChange={(event) => setRevisionId(event.target.value)} placeholder={inspected.claimRevisionId} /></label><button type="submit" className="secondary-button" disabled={busy || !revisionId.trim()}><History size={14} />{t("claims.replay")}</button></form>
      </section>

      {!historical ? (
        <>
          <section className="claim-review-section" aria-labelledby="claim-review-title">
            <div className="insights-panel-heading"><h3 id="claim-review-title">{t("claims.humanReview")}</h3></div>
            {claim.latestReview ? <p className="claim-latest-review"><ShieldCheck size={14} />{t(`reviewDecision.${claim.latestReview.decision}` as MessageKey)} · {claim.latestReview.reviewer}{claim.latestReview.rationale ? ` · ${claim.latestReview.rationale}` : ""}</p> : null}
            <label>{t("claims.reviewer")}<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></label>
            <label>{t("claims.reviewRationale")}<textarea rows={2} value={reviewRationale} onChange={(event) => setReviewRationale(event.target.value)} /></label>
            <div className="claim-review-actions">
              <button type="button" className="primary-button" disabled={busy || !reviewer.trim()} onClick={() => void review("ACCEPT")}>{t("reviewDecision.ACCEPT")}</button>
              <button type="button" className="secondary-button" disabled={busy || !reviewer.trim() || !reviewRationale.trim()} onClick={() => void review("REQUEST_CHANGES")}>{t("reviewDecision.REQUEST_CHANGES")}</button>
              <button type="button" className="danger-button" disabled={busy || !reviewer.trim() || !reviewRationale.trim()} onClick={() => void review("REJECT")}>{t("reviewDecision.REJECT")}</button>
            </div>
          </section>
          <button type="button" className="secondary-button" onClick={() => setEditing((value) => !value)}>{editing ? t("claims.cancelRevision") : t("claims.newRevision")}</button>
          {editing ? <RevisionForm claim={claim} t={t} busy={busy} onRevise={onRevise} onDone={() => setEditing(false)} /> : null}
        </>
      ) : null}
      {actionError ? <p className="form-error" role="alert">{actionError}</p> : null}
    </article>
  );
}

function RevisionForm({ claim, t, busy, onRevise, onDone }: { claim: Claim; t: ClaimsTranslator; busy: boolean; onRevise: (claim: Claim, input: ClaimRevisionInput) => Promise<Claim>; onDone: () => void }) {
  const [statement, setStatement] = useState(claim.statement);
  const [summary, setSummary] = useState(claim.summary ?? "");
  const [rationale, setRationale] = useState(claim.rationale);
  const [confidence, setConfidence] = useState(Math.round(claim.confidence * 100));
  const [counterStatus, setCounterStatus] = useState<CounterevidenceStatus>(claim.counterevidenceStatus);
  const [counterSummary, setCounterSummary] = useState(claim.counterevidenceSummary ?? "");
  const [confirmed, setConfirmed] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!confirmed || !statement.trim() || !rationale.trim()) return;
    await onRevise(claim, {
      topicKey: claim.topicKey,
      statement: statement.trim(),
      summary: summary.trim() || null,
      rationale: rationale.trim(),
      confidence: confidence / 100,
      counterevidenceStatus: counterStatus,
      counterevidenceSummary: counterSummary.trim() || null,
      provenance: { ...claim.provenance, revised_in: "discovery_workbench" },
      evidenceEdges: claim.evidenceEdges.map((edge) => ({ evidenceId: edge.evidenceId, evidenceRevisionId: edge.evidenceRevisionId, relation: edge.relation, rationale: edge.rationale, relevance: edge.relevance, relationConfirmed: edge.relationConfirmed })),
      clientRequestId: requestId(),
    });
    onDone();
  }

  return (
    <form className="claim-save-form claim-revision-form" onSubmit={(event) => void submit(event)}>
      <h3>{t("claims.newRevision")}</h3>
      <label>{t("claims.statement")}<textarea rows={3} value={statement} onChange={(event) => setStatement(event.target.value)} required /></label>
      <label>{t("claims.summaryOptional")}<textarea rows={2} value={summary} onChange={(event) => setSummary(event.target.value)} /></label>
      <label>{t("claims.claimRationale")}<textarea rows={2} value={rationale} onChange={(event) => setRationale(event.target.value)} required /></label>
      <label>{t("claims.confidenceInput")}<input type="number" min={0} max={100} value={confidence} onChange={(event) => setConfidence(Number(event.target.value))} /></label>
      <label>{t("claims.counterevidence")}<select value={counterStatus} onChange={(event) => setCounterStatus(event.target.value as CounterevidenceStatus)}><option value="NOT_RUN">{t("counter.NOT_RUN")}</option><option value="SEARCHED_NONE_FOUND">{t("counter.SEARCHED_NONE_FOUND")}</option><option value="FOUND">{t("counter.FOUND")}</option></select></label>
      <label>{t("claims.counterSummary")}<textarea rows={2} value={counterSummary} onChange={(event) => setCounterSummary(event.target.value)} /></label>
      <label className="claim-confirm-row"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />{t("claims.confirmRevision")}</label>
      <button className="primary-button" type="submit" disabled={busy || !confirmed || !statement.trim() || !rationale.trim()}>{busy ? <LoaderCircle className="spin" size={14} /> : <Save size={14} />}{t("claims.createRevision")}</button>
    </form>
  );
}

function opportunityEligible(claim: Claim | null): claim is Claim {
  return Boolean(
    claim
    && claim.isCurrent
    && claim.status === "REVIEWED"
    && claim.revisionStatus === "REVIEWED",
  );
}

function noteLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter((item, index, items) => Boolean(item) && items.indexOf(item) === index);
}

function OpportunityAuthoringForm({
  claim,
  t,
  busy,
  onCreate,
}: {
  claim: Claim;
  t: ClaimsTranslator;
  busy: boolean;
  onCreate: (input: OpportunityDraftInput) => Promise<SavedOpportunityDraft>;
}) {
  const [title, setTitle] = useState("");
  const [problemStatement, setProblemStatement] = useState("");
  const [desiredOutcome, setDesiredOutcome] = useState("");
  const [nextStep, setNextStep] = useState("");
  const [rationale, setRationale] = useState("");
  const [confidence, setConfidence] = useState(50);
  const [assumptions, setAssumptions] = useState("");
  const [risks, setRisks] = useState("");
  const [clientRequestId, setClientRequestId] = useState(() => requestId());
  const [submitError, setSubmitError] = useState("");
  const [saved, setSaved] = useState(false);

  const complete = Boolean(
    title.trim()
    && problemStatement.trim()
    && desiredOutcome.trim()
    && nextStep.trim()
    && Number.isFinite(confidence)
    && confidence >= 0
    && confidence <= 100,
  );

  function edit<T>(setter: (value: T) => void, value: T) {
    if (saved) {
      setSaved(false);
      setClientRequestId(requestId());
    }
    setter(value);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!complete || busy) return;
    setSubmitError("");
    setSaved(false);
    try {
      await onCreate({
        claimId: claim.claimId,
        claimRevisionId: claim.claimRevisionId,
        title: title.trim(),
        problemStatement: problemStatement.trim(),
        desiredOutcome: desiredOutcome.trim(),
        nextStep: nextStep.trim(),
        rationale: rationale.trim() || null,
        confidence: confidence / 100,
        assumptions: noteLines(assumptions),
        risks: noteLines(risks),
        provenance: {
          authoring_mode: "human",
          surface: "claims_opportunities_workspace",
        },
        clientRequestId,
      });
      setSaved(true);
    } catch (error) {
      // Keep the same idempotency key so an ambiguous network failure can be retried safely.
      setSubmitError(error instanceof Error ? error.message : t("general.unknownError"));
    }
  }

  return (
    <form className="opportunity-author-form" onSubmit={submit} aria-labelledby="opportunity-author-title">
      <div className="insights-panel-heading">
        <div>
          <span>{t("opportunities.humanAuthored")}</span>
          <h3 id="opportunity-author-title">{t("opportunities.createTitle")}</h3>
        </div>
        <span className="claim-status status-reviewed">{t("claimStatus.REVIEWED")}</span>
      </div>
      <p className="opportunity-author-context">{t("opportunities.exactClaimHelp")}</p>
      <dl className="claim-revision-facts opportunity-lineage">
        <div><dt>{t("opportunities.claim")}</dt><dd>{claim.statement}</dd></div>
        <div><dt>{t("claims.revisionId")}</dt><dd><code>{claim.claimRevisionId}</code></dd></div>
      </dl>
      {claim.counterevidenceStatus === "NOT_RUN" ? (
        <div className="claim-blockers" role="status">
          <AlertTriangle size={15} />
          <div><strong>{t("opportunities.counterNotRun")}</strong><p>{t("opportunities.counterNotRunHelp")}</p></div>
        </div>
      ) : null}
      <label>{t("opportunities.title")}<input required value={title} onChange={(event) => edit(setTitle, event.target.value)} /></label>
      <label>{t("opportunities.problemStatement")}<textarea required rows={3} value={problemStatement} onChange={(event) => edit(setProblemStatement, event.target.value)} /></label>
      <label>{t("opportunities.desiredOutcome")}<textarea required rows={3} value={desiredOutcome} onChange={(event) => edit(setDesiredOutcome, event.target.value)} /></label>
      <label>{t("opportunities.nextStep")}<textarea required rows={2} value={nextStep} onChange={(event) => edit(setNextStep, event.target.value)} /></label>
      <label>{t("opportunities.rationale")}<textarea rows={2} value={rationale} onChange={(event) => edit(setRationale, event.target.value)} /></label>
      <label>{t("opportunities.confidence")}<input type="number" min={0} max={100} value={confidence} onChange={(event) => edit(setConfidence, Number(event.target.value))} /></label>
      <div className="opportunity-notes-grid">
        <label>{t("opportunities.assumptions")}<textarea rows={3} value={assumptions} onChange={(event) => edit(setAssumptions, event.target.value)} placeholder={t("opportunities.onePerLine")} /></label>
        <label>{t("opportunities.risks")}<textarea rows={3} value={risks} onChange={(event) => edit(setRisks, event.target.value)} placeholder={t("opportunities.onePerLine")} /></label>
      </div>
      <p className="claim-form-note">{t("opportunities.draftOnlyHelp")}</p>
      {saved ? <p className="form-success" role="status"><CheckCircle2 size={14} />{t("opportunities.saved")}</p> : null}
      {submitError ? <p className="form-error" role="alert">{submitError}</p> : null}
      <button className="primary-button" type="submit" disabled={busy || !complete || saved}>
        {busy ? <LoaderCircle className="spin" size={14} /> : <Save size={14} />}{t("opportunities.saveDraft")}
      </button>
    </form>
  );
}

function SavedOpportunityCard({ draft, t }: { draft: SavedOpportunityDraft; t: ClaimsTranslator }) {
  return (
    <article className="saved-opportunity-card">
      <header>
        <div><span>{t("opportunities.persisted")}</span><h3>{draft.title}</h3></div>
        <span className="opportunity-draft-status">{draft.status}</span>
      </header>
      <p className="saved-opportunity-claim"><strong>{t("opportunities.claim")}</strong>{draft.claimStatement}</p>
      <dl>
        <div><dt>{t("opportunities.problemStatement")}</dt><dd>{draft.problemStatement}</dd></div>
        <div><dt>{t("opportunities.desiredOutcome")}</dt><dd>{draft.desiredOutcome}</dd></div>
        <div><dt>{t("opportunities.nextStep")}</dt><dd>{draft.nextStep}</dd></div>
      </dl>
      <div className="saved-opportunity-meta">
        <span>{t("opportunities.confidenceValue", { value: Math.round(draft.confidence * 100) })}</span>
        <code title={t("claims.revisionId")}>{draft.claimRevisionId}</code>
      </div>
      <div className="opportunity-publish-state" role="status">
        <AlertTriangle size={14} />
        <div>
          <strong>{t("opportunities.notPublishable")}</strong>
          <ul>{draft.publicationBlockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
        </div>
      </div>
    </article>
  );
}

export function ClaimsOpportunitiesView({ evidence, study, t, live = false, onOpenEvidence, onOpenEvidenceRevision }: ClaimsOpportunitiesViewProps) {
  const insights = useMemo(() => deriveInsights(evidence), [evidence]);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const [selectedSavedId, setSelectedSavedId] = useState<string | null>(null);
  const claimsState = useClaims(study?.id ?? null, live);
  const opportunitiesState = useOpportunities(study?.id ?? null, live);
  const selectedDraft = insights.claims.find((claim) => claim.id === selectedDraftId) ?? insights.claims[0] ?? null;
  const selectedSaved = claimsState.claims.find((claim) => claim.claimId === selectedSavedId) ?? claimsState.claims[0] ?? null;
  const excludedCount = insights.excludedSyntheticCount + insights.excludedUntraceableCount + insights.excludedRejectedOrStaleCount;
  const evidenceByRevision = useMemo(() => new Map(evidence.filter((item) => item.revisionId).map((item) => [`${item.id}:${item.revisionId}`, item] as const)), [evidence]);

  function openRevision(evidenceId: string, revisionId: string) {
    if (onOpenEvidenceRevision) {
      onOpenEvidenceRevision(evidenceId, revisionId);
      return;
    }
    const exact = evidenceByRevision.get(`${evidenceId}:${revisionId}`);
    if (exact) onOpenEvidence(exact);
  }

  return (
    <section className="insights-view" aria-labelledby="claims-view-title">
      <header className="insights-hero">
        <div className="insights-hero-copy"><span className="insights-preview-badge"><Sparkles size={14} />{t("claims.previewBadge")}</span><h1 id="claims-view-title">{t("claims.heroTitle")}</h1><p>{t("claims.heroBody")}</p>{study ? <div className="insights-study-context"><strong>{study.title}</strong><span>{study.decisionQuestion}</span></div> : null}</div>
        <div className="insights-original-language"><ShieldCheck size={20} /><p>{t("claims.originalLanguage")}</p></div>
      </header>
      <dl className="insights-metrics"><div className="insights-metric"><dt>{t("claims.input")}</dt><dd>{insights.inputEvidenceCount}</dd></div><div className="insights-metric"><dt>{t("claims.eligible")}</dt><dd>{insights.eligibleEvidenceCount}</dd></div><div className="insights-metric"><dt>{t("claims.reviewed")}</dt><dd>{insights.reviewedEvidenceCount}</dd></div><div className="insights-metric"><dt>{t("claims.excluded")}</dt><dd>{excludedCount}</dd></div></dl>

      <section className="persisted-claims-section" aria-labelledby="saved-claims-title">
        <div className="insights-panel-heading"><div><span>{t("claims.versionedStore")}</span><h2 id="saved-claims-title">{t("claims.savedTitle")}</h2></div><div className="claim-heading-actions"><strong>{claimsState.claims.length}</strong>{live ? <button type="button" className="icon-button" aria-label={t("general.refresh")} onClick={() => void claimsState.reload()}><RefreshCw size={14} /></button> : null}</div></div>
        {!live ? <p className="claim-form-note">{t("claims.savedLiveOnly")}</p> : claimsState.loading ? <div className="list-loading" role="status"><LoaderCircle className="spin" size={17} />{t("claims.loadingSaved")}</div> : claimsState.error ? <div className="inline-error" role="alert"><AlertCircle size={16} /><div><strong>{t("claims.loadFailed")}</strong><span>{claimsState.error}</span></div><button className="text-button" onClick={() => void claimsState.reload()}>{t("general.retry")}</button></div> : claimsState.claims.length === 0 ? <p className="section-empty">{t("claims.noSaved")}</p> : (
          <div className="insights-grid"><div className="insights-claim-list">{claimsState.claims.map((claim) => <button type="button" key={claim.claimId} className={`insights-claim-card${selectedSaved?.claimId === claim.claimId ? " active" : ""}`} aria-pressed={selectedSaved?.claimId === claim.claimId} onClick={() => setSelectedSavedId(claim.claimId)}><span className="insights-claim-topic">{topicLabel(t, claim.topicKey)}</span><strong className="insights-claim-summary">{claim.statement}</strong><span>{t(`claimStatus.${claim.status}` as MessageKey)} · r{claim.revision}</span></button>)}</div>{selectedSaved ? <PersistedClaimInspector key={selectedSaved.claimRevisionId} claim={selectedSaved} t={t} busy={claimsState.pendingActions.size > 0} onOpenRevision={openRevision} onReview={async (decision, reviewer, rationale) => { await claimsState.reviewRevision(selectedSaved, { decision, reviewer, rationale: rationale || null, clientRequestId: requestId() }); }} onRevise={async (claim, input) => claimsState.createRevision(claim, input)} onReplay={claimsState.loadExactRevision} /> : null}</div>
        )}
      </section>

      <section className="persisted-opportunities-section" aria-labelledby="saved-opportunities-title">
        <div className="insights-panel-heading">
          <div><span>{t("opportunities.immutableStore")}</span><h2 id="saved-opportunities-title">{t("opportunities.savedTitle")}</h2></div>
          <div className="claim-heading-actions">
            <strong>{opportunitiesState.opportunities.length}</strong>
            {live ? <button type="button" className="icon-button" aria-label={t("opportunities.refresh")} onClick={() => void opportunitiesState.reload()}><RefreshCw size={14} /></button> : null}
          </div>
        </div>
        {!live ? <p className="claim-form-note">{t("opportunities.liveOnly")}</p> : opportunitiesState.loading ? (
          <div className="list-loading" role="status"><LoaderCircle className="spin" size={17} />{t("opportunities.loading")}</div>
        ) : opportunitiesState.error ? (
          <div className="inline-error" role="alert"><AlertCircle size={16} /><div><strong>{t("opportunities.loadFailed")}</strong><span>{opportunitiesState.error}</span></div><button className="text-button" onClick={() => void opportunitiesState.reload()}>{t("general.retry")}</button></div>
        ) : opportunitiesState.opportunities.length === 0 ? <p className="section-empty">{t("opportunities.empty")}</p> : (
          <div className="saved-opportunity-list">{opportunitiesState.opportunities.map((draft) => <SavedOpportunityCard key={draft.id} draft={draft} t={t} />)}</div>
        )}
        {live && selectedSaved ? opportunityEligible(selectedSaved) ? (
          <OpportunityAuthoringForm
            key={selectedSaved.claimRevisionId}
            claim={selectedSaved}
            t={t}
            busy={opportunitiesState.pendingActions.size > 0}
            onCreate={(input) => opportunitiesState.createOpportunity(selectedSaved, input)}
          />
        ) : (
          <div className="opportunity-ineligible" role="status"><CircleDotDashed size={16} /><div><strong>{t("opportunities.ineligible")}</strong><p>{t("opportunities.ineligibleHelp")}</p></div></div>
        ) : null}
      </section>

      {insights.gaps.length > 0 ? <ul className="insights-global-gaps" aria-label={t("claims.gaps")}>{insights.gaps.map((gap) => <li key={`${gap.code}:${gap.count ?? 0}`} className={`insights-gap severity-${gap.severity}`}>{gap.severity === "blocking" ? <AlertTriangle size={15} /> : gap.severity === "warning" ? <CircleDotDashed size={15} /> : <CheckCircle2 size={15} />}{gapLabel(t, gap)}</li>)}</ul> : null}
      {insights.claims.length === 0 ? <div className="insights-empty" role="status"><span className="insights-empty-icon"><GitBranch size={28} /></span><h2>{t("claims.emptyTitle")}</h2><p>{t("claims.emptyBody")}</p></div> : (
        <>
          <div className="insights-grid"><section className="insights-claim-panel" aria-labelledby="claim-drafts-title"><div className="insights-panel-heading"><div><span>{t("claims.nonPersisted")}</span><h2 id="claim-drafts-title">{t("claims.listTitle")}</h2></div><strong>{insights.claims.length}</strong></div><div className="insights-claim-list">{insights.claims.map((claim) => <button key={claim.id} type="button" className={`insights-claim-card${selectedDraft?.id === claim.id ? " active" : ""}`} aria-pressed={selectedDraft?.id === claim.id} onClick={() => setSelectedDraftId(claim.id)}><span className="insights-claim-topic">{topicLabel(t, claim.topicKey, claim.topicLabel)}</span><strong className="insights-claim-summary">{claim.statement}</strong><StrengthSummary claim={claim} t={t} /></button>)}</div></section>{selectedDraft ? <DraftInspector key={selectedDraft.id} claim={selectedDraft} t={t} canPersist={live && Boolean(study)} saving={claimsState.pendingActions.size > 0} onOpenRevision={openRevision} onSave={async (input) => { const created = await claimsState.createClaim(input); setSelectedSavedId(created.claimId); }} /> : null}</div>
          <section className="insights-opportunity-panel" aria-labelledby="opportunity-drafts-title"><div className="insights-panel-heading"><div><span>{t("opportunities.suggestedOnly")}</span><h2 id="opportunity-drafts-title">{t("opportunities.suggestedTitle")}</h2></div><strong>{insights.opportunities.length}</strong></div><p className="opportunity-preview-help">{t("opportunities.suggestedHelp")}</p><div className="insights-opportunity-list">{insights.opportunities.map((opportunity) => <article key={opportunity.id} className="insights-opportunity-card opportunity-preview-card"><div className="insights-opportunity-meta"><span><Lightbulb size={15} />{t("opportunities.suggestion")}</span><span className="insights-readiness">{t(opportunity.readiness === "ready_for_human_review" ? "claims.readyReview" : "claims.needsEvidence")}</span></div><span>{topicLabel(t, opportunity.topicKey, opportunity.focus)}</span><h3>{opportunity.problemStatement}</h3><div className="insights-next-step"><span>{t("claims.nextStep")}</span><strong>{t(nextStepMessageKeys[opportunity.nextStep])}</strong></div></article>)}</div></section>
        </>
      )}
    </section>
  );
}
