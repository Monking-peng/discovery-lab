"use client";

import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  CircleDotDashed,
  GitBranch,
  Lightbulb,
  Link2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useMemo, useState } from "react";

import type { Evidence, Study } from "@/lib/api";
import type { MessageKey, TranslationVars } from "@/lib/i18n";
import {
  deriveInsights,
  type ClaimDraft,
  type InsightGap,
  type InsightGapCode,
  type InsightRelation,
  type InsightStrengthLevel,
  type OpportunityDraft,
} from "@/lib/insights";

export type ClaimsTranslator = (key: MessageKey, vars?: TranslationVars) => string;

export type ClaimsOpportunitiesViewProps = {
  evidence: readonly Evidence[];
  study?: Study | null;
  t: ClaimsTranslator;
  onOpenEvidence: (evidence: Evidence) => void;
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

const relationMessageKeys: Record<InsightRelation, MessageKey> = {
  supports: "relation.supports",
  challenges: "relation.challenges",
  contextualizes: "relation.contextualizes",
};

const reviewMessageKeys: Record<Evidence["reviewStatus"], MessageKey> = {
  approved: "review.approved",
  reviewed: "review.reviewed",
  pending: "review.pending",
  rejected: "review.rejected",
  stale: "review.stale",
};

const nextStepMessageKeys: Record<OpportunityDraft["nextStep"], MessageKey> = {
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

function topicLabel(t: ClaimsTranslator, topicKey: string, fallback: string): string {
  const messageKey = topicMessageKeys[topicKey];
  return messageKey ? t(messageKey) : fallback;
}

function gapLabel(t: ClaimsTranslator, gap: InsightGap): string {
  return t(gapMessageKeys[gap.code], { count: gap.count ?? 0 });
}

function StrengthSummary({ claim, t }: { claim: ClaimDraft; t: ClaimsTranslator }) {
  const strengthLabel = t(strengthMessageKeys[claim.strength.level]);

  return (
    <div className="insights-strength-row">
      <span>{t("claims.score", { score: claim.strength.score, level: strengthLabel })}</span>
      <span
        className="insights-strength-bar"
        role="meter"
        aria-label={t("claims.strength")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={claim.strength.score}
      >
        <span
          className="insights-strength-fill"
          style={{ width: `${claim.strength.score}%` }}
        />
      </span>
    </div>
  );
}

export function ClaimsOpportunitiesView({
  evidence,
  study,
  t,
  onOpenEvidence,
}: ClaimsOpportunitiesViewProps) {
  const insights = useMemo(() => deriveInsights(evidence), [evidence]);
  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null);
  const selectedClaim = insights.claims.find((claim) => claim.id === selectedClaimId)
    ?? insights.claims[0]
    ?? null;
  const excludedCount = insights.excludedSyntheticCount
    + insights.excludedUntraceableCount
    + insights.excludedRejectedOrStaleCount;
  const evidenceByRevision = useMemo(() => new Map(
    evidence
      .filter((item) => item.revisionId)
      .map((item) => [`${item.id}:${item.revisionId}`, item] as const),
  ), [evidence]);

  return (
    <section className="insights-view" aria-labelledby="claims-view-title">
      <header className="insights-hero">
        <div className="insights-hero-copy">
          <span className="insights-preview-badge">
            <Sparkles size={14} aria-hidden="true" />
            {t("claims.previewBadge")}
          </span>
          <h1 id="claims-view-title">{t("claims.heroTitle")}</h1>
          <p>{t("claims.heroBody")}</p>
          {study ? (
            <div className="insights-study-context">
              <strong>{study.title}</strong>
              <span>{study.decisionQuestion}</span>
            </div>
          ) : null}
        </div>
        <div className="insights-original-language">
          <ShieldCheck size={20} aria-hidden="true" />
          <p>{t("claims.originalLanguage")}</p>
        </div>
      </header>

      <dl className="insights-metrics">
        <div className="insights-metric">
          <dt>{t("claims.input")}</dt>
          <dd>{insights.inputEvidenceCount}</dd>
        </div>
        <div className="insights-metric">
          <dt>{t("claims.eligible")}</dt>
          <dd>{insights.eligibleEvidenceCount}</dd>
        </div>
        <div className="insights-metric">
          <dt>{t("claims.reviewed")}</dt>
          <dd>{insights.reviewedEvidenceCount}</dd>
        </div>
        <div className="insights-metric">
          <dt>{t("claims.excluded")}</dt>
          <dd>{excludedCount}</dd>
        </div>
      </dl>

      {insights.gaps.length > 0 ? (
        <ul className="insights-global-gaps" aria-label={t("claims.gaps")}>
          {insights.gaps.map((gap) => (
            <li
              key={`${gap.code}:${gap.count ?? 0}`}
              className={`insights-gap severity-${gap.severity}`}
            >
              {gap.severity === "blocking" ? (
                <AlertTriangle size={15} aria-hidden="true" />
              ) : gap.severity === "warning" ? (
                <CircleDotDashed size={15} aria-hidden="true" />
              ) : (
                <CheckCircle2 size={15} aria-hidden="true" />
              )}
              {gapLabel(t, gap)}
            </li>
          ))}
        </ul>
      ) : null}

      {insights.claims.length === 0 ? (
        <div className="insights-empty" role="status">
          <span className="insights-empty-icon">
            <GitBranch size={28} aria-hidden="true" />
          </span>
          <h2>{t("claims.emptyTitle")}</h2>
          <p>{t("claims.emptyBody")}</p>
        </div>
      ) : (
        <>
          <div className="insights-grid">
            <section className="insights-claim-panel" aria-labelledby="claim-drafts-title">
              <div className="insights-panel-heading">
                <div>
                  <span>{t("claims.nonPersisted")}</span>
                  <h2 id="claim-drafts-title">{t("claims.listTitle")}</h2>
                </div>
                <strong>{insights.claims.length}</strong>
              </div>

              <div className="insights-claim-list">
                {insights.claims.map((claim) => {
                  const active = selectedClaim?.id === claim.id;
                  return (
                    <button
                      key={claim.id}
                      type="button"
                      className={`insights-claim-card${active ? " active" : ""}`}
                      aria-pressed={active}
                      onClick={() => setSelectedClaimId(claim.id)}
                    >
                      <span className="insights-claim-topic">
                        {topicLabel(t, claim.topicKey, claim.topicLabel)}
                      </span>
                      <strong className="insights-claim-summary">{claim.statement}</strong>
                      <StrengthSummary claim={claim} t={t} />
                    </button>
                  );
                })}
              </div>
            </section>

            {selectedClaim ? (
              <article className="insights-inspector" aria-labelledby="selected-claim-title">
                <header className="insights-inspector-head">
                  <div>
                    <span>{t("claims.statement")}</span>
                    <h2 id="selected-claim-title">{selectedClaim.statement}</h2>
                  </div>
                  <span className="insights-preview-badge">{t("claims.nonPersisted")}</span>
                </header>

                <div className="insights-statement">
                  <span>{t("claims.strength")}</span>
                  <StrengthSummary claim={selectedClaim} t={t} />
                </div>

                <dl className="insights-stat-strip">
                  <div className="insights-stat">
                    <dt>{t("relation.supports")}</dt>
                    <dd>{selectedClaim.strength.supportingCount}</dd>
                  </div>
                  <div className="insights-stat">
                    <dt>{t("relation.challenges")}</dt>
                    <dd>{selectedClaim.strength.challengingCount}</dd>
                  </div>
                  <div className="insights-stat">
                    <dt>{t("relation.contextualizes")}</dt>
                    <dd>{selectedClaim.strength.contextualCount}</dd>
                  </div>
                  <div className="insights-stat">
                    <dt>{t("sources.title")}</dt>
                    <dd>{selectedClaim.strength.distinctSourceCount}</dd>
                  </div>
                </dl>

                <section aria-labelledby="evidence-edges-title">
                  <div className="insights-panel-heading">
                    <h3 id="evidence-edges-title">{t("claims.evidenceEdges")}</h3>
                    <strong>{selectedClaim.edges.length}</strong>
                  </div>
                  <ul className="insights-edge-list">
                    {selectedClaim.edges.map((edge) => {
                      const exactEvidence = evidenceByRevision.get(
                        `${edge.evidenceId}:${edge.evidenceRevisionId}`,
                      );
                      return (
                        <li key={`${edge.evidenceId}:${edge.evidenceRevisionId}`} className="insights-evidence-edge">
                          <div className="insights-edge-top">
                            <span className={`insights-edge-relation relation-${edge.relation}`}>
                              <Link2 size={13} aria-hidden="true" />
                              {t(relationMessageKeys[edge.relation])}
                            </span>
                            <span>{t(reviewMessageKeys[edge.reviewStatus])}</span>
                          </div>
                          <strong>{edge.title}</strong>
                          <blockquote className="insights-edge-quote">{edge.quote}</blockquote>
                          <div className="insights-edge-meta">
                            <span>{edge.sourceName}</span>
                            <span>{edge.locatorLabel}</span>
                            <span>{t("detail.confidence", { value: Math.round(edge.confidence * 100) })}</span>
                            <code title={t("detail.evidenceRevision")}>{edge.evidenceRevisionId}</code>
                            <code title={t("detail.sourceRevision")}>{edge.sourceRevisionId}</code>
                          </div>
                          <button
                            type="button"
                            className="insights-open-evidence"
                            disabled={!exactEvidence}
                            onClick={() => {
                              if (exactEvidence) onOpenEvidence(exactEvidence);
                            }}
                          >
                            {t("claims.openEvidence")}
                            <ArrowUpRight size={15} aria-hidden="true" />
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </section>

                <section aria-labelledby="claim-gaps-title">
                  <div className="insights-panel-heading">
                    <h3 id="claim-gaps-title">{t("claims.gaps")}</h3>
                    <strong>{selectedClaim.gaps.length}</strong>
                  </div>
                  {selectedClaim.gaps.length > 0 ? (
                    <ul className="insights-global-gaps">
                      {selectedClaim.gaps.map((gap) => (
                        <li
                          key={`${gap.code}:${gap.count ?? 0}`}
                          className={`insights-gap severity-${gap.severity}`}
                        >
                          <CircleDotDashed size={15} aria-hidden="true" />
                          {gapLabel(t, gap)}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>{t("claims.noGaps")}</p>
                  )}
                </section>
              </article>
            ) : null}
          </div>

          <section className="insights-opportunity-panel" aria-labelledby="opportunity-drafts-title">
            <div className="insights-panel-heading">
              <div>
                <span>{t("claims.nonPersisted")}</span>
                <h2 id="opportunity-drafts-title">{t("claims.opportunitiesTitle")}</h2>
              </div>
              <strong>{insights.opportunities.length}</strong>
            </div>
            <div className="insights-opportunity-list">
              {insights.opportunities.map((opportunity) => (
                <article key={opportunity.id} className="insights-opportunity-card">
                  <div className="insights-opportunity-meta">
                    <span>
                      <Lightbulb size={15} aria-hidden="true" />
                      {t("claims.opportunity")}
                    </span>
                    <span className="insights-readiness">
                      {t(opportunity.readiness === "ready_for_human_review"
                        ? "claims.readyReview"
                        : "claims.needsEvidence")}
                    </span>
                  </div>
                  <span>{topicLabel(t, opportunity.topicKey, opportunity.focus)}</span>
                  <h3>{opportunity.problemStatement}</h3>
                  <div className="insights-next-step">
                    <span>{t("claims.nextStep")}</span>
                    <strong>{t(nextStepMessageKeys[opportunity.nextStep])}</strong>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </>
      )}
    </section>
  );
}
