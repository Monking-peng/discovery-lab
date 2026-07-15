import type { Evidence } from "./api";

export type InsightRelation = "supports" | "challenges" | "contextualizes";
export type InsightStrengthLevel = "strong" | "moderate" | "weak" | "insufficient";
export type InsightGapSeverity = "info" | "warning" | "blocking";

export type InsightGapCode =
  | "no_evidence"
  | "synthetic_evidence_excluded"
  | "untraceable_evidence_excluded"
  | "rejected_or_stale_evidence_excluded"
  | "no_reviewed_evidence"
  | "insufficient_support"
  | "counterevidence_missing"
  | "single_source"
  | "review_required"
  | "low_confidence"
  | "semantic_support_unverified"
  | "cohort_coverage_unavailable";

export type InsightGap = {
  code: InsightGapCode;
  severity: InsightGapSeverity;
  count?: number;
};

export type InsightEvidenceEdge = {
  evidenceId: string;
  evidenceRevisionId: string;
  sourceId: string;
  sourceRevisionId: string;
  relation: InsightRelation;
  relationOrigin: "derived-anchor" | "evidence-metadata";
  title: string;
  quote: string;
  sourceName: string;
  locatorLabel: string;
  confidence: number;
  reviewStatus: Evidence["reviewStatus"];
};

export type InsightStrength = {
  score: number;
  level: InsightStrengthLevel;
  evidenceCount: number;
  supportingCount: number;
  challengingCount: number;
  contextualCount: number;
  distinctSourceCount: number;
  reviewedCount: number;
  averageConfidence: number;
};

export type ClaimDraft = {
  id: string;
  persisted: false;
  topicKey: string;
  topicLabel: string;
  statement: string;
  basisEvidenceId: string;
  edges: InsightEvidenceEdge[];
  strength: InsightStrength;
  gaps: InsightGap[];
};

export type OpportunityDraft = {
  id: string;
  persisted: false;
  claimId: string;
  topicKey: string;
  focus: string;
  problemStatement: string;
  readiness: "needs_evidence" | "ready_for_human_review";
  evidenceCount: number;
  nextStep:
    | "collect_supporting_evidence"
    | "seek_counterevidence"
    | "review_evidence"
    | "frame_hypothesis";
};

export type DerivedInsights = {
  persisted: false;
  generatedBy: "deterministic-client-projection";
  inputEvidenceCount: number;
  eligibleEvidenceCount: number;
  excludedSyntheticCount: number;
  excludedUntraceableCount: number;
  excludedRejectedOrStaleCount: number;
  reviewedEvidenceCount: number;
  claims: ClaimDraft[];
  opportunities: OpportunityDraft[];
  gaps: InsightGap[];
};

type TopicDefinition = {
  key: string;
  label: string;
  patterns: readonly string[];
};

type EligibleEvidence = Evidence & {
  revisionId: string;
  sourceRevisionId: string;
};

const TOPICS: readonly TopicDefinition[] = [
  {
    key: "risk-escalation",
    label: "Risk escalation",
    patterns: [
      "risk escalation",
      "escalation",
      "churn risk",
      "retention risk",
      "sla",
      "outage",
      "high risk",
      "高风险",
      "升级",
      "流失风险",
      "服务等级",
    ],
  },
  {
    key: "auto-reply",
    label: "AI reply assistance",
    patterns: [
      "auto reply",
      "auto-reply",
      "reply drafting",
      "drafting",
      "generated reply",
      "自动回复",
      "回复生成",
      "回复草稿",
    ],
  },
  {
    key: "classification-routing",
    label: "Classification and routing",
    patterns: ["classification", "routing", "route", "分类", "路由", "分流"],
  },
  {
    key: "explainability-governance",
    label: "Explainability and governance",
    patterns: [
      "explainability",
      "governance",
      "audit",
      "compliance",
      "human confirmation",
      "可解释",
      "治理",
      "审计",
      "合规",
      "人工确认",
    ],
  },
  {
    key: "onboarding",
    label: "Onboarding",
    patterns: ["onboarding", "time to value", "time-to-value", "上手", "首次价值", "引导"],
  },
  {
    key: "retention",
    label: "Retention",
    patterns: ["retention", "renewal", "churn", "留存", "续费", "流失"],
  },
];

const IGNORED_TAGS = new Set([
  "demo-extractor",
  "source-excerpt",
  "synthetic-demo",
  "unreviewed",
]);

function normalize(value: string): string {
  return value
    .normalize("NFKC")
    .toLocaleLowerCase("en")
    .replace(/[\s_]+/g, " ")
    .trim();
}

function slug(value: string): string {
  const normalized = normalize(value)
    .replace(/[^a-z0-9\u3400-\u9fff]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || "general";
}

function stableHash(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function stableId(prefix: string, topicKey: string, evidenceIds: readonly string[]): string {
  const identity = `${topicKey}:${[...evidenceIds].sort().join(":")}`;
  return `${prefix}-${slug(topicKey)}-${stableHash(identity)}`;
}

function evidenceText(item: Evidence): string {
  return normalize(
    [item.title, item.observation, item.interpretation, item.quote, ...item.tags].join(" "),
  );
}

function resolveTopic(item: Evidence): { key: string; label: string } {
  const haystack = evidenceText(item);
  const known = TOPICS.find((topic) => topic.patterns.some((pattern) => haystack.includes(pattern)));
  if (known) return { key: known.key, label: known.label };

  const meaningfulTag = item.tags
    .map(normalize)
    .filter((tag) => tag && !IGNORED_TAGS.has(tag))
    .sort((left, right) => left.localeCompare(right, "en"))[0];
  if (meaningfulTag) return { key: `tag-${slug(meaningfulTag)}`, label: meaningfulTag };
  return { key: `kind-${item.kind}`, label: item.kind };
}

function isReviewed(item: Evidence): boolean {
  return item.reviewStatus === "approved" || item.reviewStatus === "reviewed";
}

function evidencePriority(item: Evidence): number {
  const reviewBoost = isReviewed(item) ? 2 : item.reviewStatus === "pending" ? 1 : 0;
  const semanticCopyBoost = item.interpretation.trim() ? 2 : item.observation.trim() ? 1 : 0;
  return reviewBoost * 100 + semanticCopyBoost * 10 + item.confidence;
}

function claimStatement(item: Evidence): string {
  return (
    item.interpretation.trim()
    || item.observation.trim()
    || item.title.trim()
    || item.quote.trim()
  );
}

function relationFor(item: Evidence, anchorId: string): InsightRelation {
  if (item.id === anchorId) return "supports";
  if (item.kind === "counterevidence" || item.relationship === "challenges") return "challenges";
  if (item.relationship === "supports") return "supports";
  return "contextualizes";
}

function strengthFor(edges: readonly InsightEvidenceEdge[]): InsightStrength {
  const supportingCount = edges.filter((edge) => edge.relation === "supports").length;
  const challengingCount = edges.filter((edge) => edge.relation === "challenges").length;
  const contextualCount = edges.filter((edge) => edge.relation === "contextualizes").length;
  const distinctSourceCount = new Set(edges.map((edge) => edge.sourceId)).size;
  const reviewedCount = edges.filter((edge) => (
    edge.reviewStatus === "approved" || edge.reviewStatus === "reviewed"
  )).length;
  const averageConfidence = edges.length === 0
    ? 0
    : edges.reduce((sum, edge) => sum + edge.confidence, 0) / edges.length;
  const supportScore = Math.min(30, supportingCount * 10);
  const sourceScore = Math.min(20, distinctSourceCount * 10);
  const confidenceScore = averageConfidence * 25;
  const reviewScore = edges.length === 0 ? 0 : (reviewedCount / edges.length) * 25;
  const rawScore = Math.round(supportScore + sourceScore + confidenceScore + reviewScore);
  const score = supportingCount === 0 ? Math.min(30, rawScore) : Math.min(100, rawScore);
  const level: InsightStrengthLevel = score >= 75
    ? "strong"
    : score >= 55
      ? "moderate"
      : score >= 35
        ? "weak"
        : "insufficient";

  return {
    score,
    level,
    evidenceCount: edges.length,
    supportingCount,
    challengingCount,
    contextualCount,
    distinctSourceCount,
    reviewedCount,
    averageConfidence,
  };
}

function claimGaps(strength: InsightStrength): InsightGap[] {
  const gaps: InsightGap[] = [
    { code: "semantic_support_unverified", severity: "warning" },
    { code: "cohort_coverage_unavailable", severity: "info" },
  ];
  if (strength.supportingCount < 2) {
    gaps.push({ code: "insufficient_support", severity: "blocking", count: strength.supportingCount });
  }
  if (strength.challengingCount === 0) {
    gaps.push({ code: "counterevidence_missing", severity: "warning" });
  }
  if (strength.distinctSourceCount < 2) {
    gaps.push({ code: "single_source", severity: "warning", count: strength.distinctSourceCount });
  }
  if (strength.reviewedCount < strength.evidenceCount) {
    gaps.push({
      code: "review_required",
      severity: "warning",
      count: strength.evidenceCount - strength.reviewedCount,
    });
  }
  if (strength.averageConfidence < 0.7) {
    gaps.push({ code: "low_confidence", severity: "warning" });
  }
  return gaps;
}

function nextStepFor(claim: ClaimDraft): OpportunityDraft["nextStep"] {
  if (claim.strength.supportingCount < 2) return "collect_supporting_evidence";
  if (claim.strength.challengingCount === 0) return "seek_counterevidence";
  if (claim.strength.reviewedCount < claim.strength.evidenceCount) return "review_evidence";
  return "frame_hypothesis";
}

function eligibleEvidence(item: Evidence): item is EligibleEvidence {
  return (
    !item.syntheticDemo
    && item.reviewStatus !== "rejected"
    && item.reviewStatus !== "stale"
    && Boolean(item.id)
    && Boolean(item.revisionId)
    && Boolean(item.sourceId)
    && Boolean(item.sourceRevisionId)
    && Boolean(item.quote.trim())
  );
}

/**
 * Builds a read-only, deterministic preview from already loaded Evidence.
 *
 * This is deliberately not a Claim generation model and never persists data.
 * Synthetic, stale, rejected, or untraceable Evidence is excluded. Every edge
 * binds an immutable Evidence Revision so the UI can replay the exact source.
 */
export function deriveInsights(evidence: readonly Evidence[]): DerivedInsights {
  const excludedSyntheticCount = evidence.filter((item) => item.syntheticDemo).length;
  const excludedRejectedOrStaleCount = evidence.filter((item) => (
    !item.syntheticDemo && (item.reviewStatus === "rejected" || item.reviewStatus === "stale")
  )).length;
  const excludedUntraceableCount = evidence.filter((item) => (
    !item.syntheticDemo
    && item.reviewStatus !== "rejected"
    && item.reviewStatus !== "stale"
    && (!item.revisionId || !item.sourceRevisionId || !item.sourceId || !item.quote.trim())
  )).length;
  const eligible = evidence.filter(eligibleEvidence);
  const reviewedEvidenceCount = eligible.filter(isReviewed).length;
  const clusters = new Map<string, { label: string; items: EligibleEvidence[] }>();

  for (const item of eligible) {
    const topic = resolveTopic(item);
    const current = clusters.get(topic.key) ?? { label: topic.label, items: [] };
    current.items.push(item);
    clusters.set(topic.key, current);
  }

  const claims = [...clusters.entries()]
    .sort(([left], [right]) => left.localeCompare(right, "en"))
    .map(([topicKey, cluster]): ClaimDraft => {
      const ordered = [...cluster.items].sort((left, right) => (
        evidencePriority(right) - evidencePriority(left) || left.id.localeCompare(right.id, "en")
      ));
      const anchor = ordered[0];
      const edges = ordered.map((item): InsightEvidenceEdge => ({
        evidenceId: item.id,
        evidenceRevisionId: item.revisionId,
        sourceId: item.sourceId,
        sourceRevisionId: item.sourceRevisionId,
        relation: relationFor(item, anchor.id),
        relationOrigin: item.id === anchor.id ? "derived-anchor" : "evidence-metadata",
        title: item.title,
        quote: item.quote,
        sourceName: item.sourceName,
        locatorLabel: item.locatorLabel,
        confidence: item.confidence,
        reviewStatus: item.reviewStatus,
      }));
      const strength = strengthFor(edges);
      return {
        id: stableId("claim-preview", topicKey, ordered.map((item) => item.id)),
        persisted: false,
        topicKey,
        topicLabel: cluster.label,
        statement: claimStatement(anchor),
        basisEvidenceId: anchor.id,
        edges,
        strength,
        gaps: claimGaps(strength),
      };
    });

  const opportunities = claims.map((claim): OpportunityDraft => {
    const nextStep = nextStepFor(claim);
    return {
      id: stableId("opportunity-preview", claim.topicKey, [claim.id]),
      persisted: false,
      claimId: claim.id,
      topicKey: claim.topicKey,
      focus: claim.topicLabel,
      problemStatement: claim.statement,
      readiness: nextStep === "frame_hypothesis" ? "ready_for_human_review" : "needs_evidence",
      evidenceCount: claim.edges.length,
      nextStep,
    };
  });

  const gaps: InsightGap[] = [];
  if (evidence.length === 0) gaps.push({ code: "no_evidence", severity: "blocking" });
  if (excludedSyntheticCount > 0) {
    gaps.push({ code: "synthetic_evidence_excluded", severity: "info", count: excludedSyntheticCount });
  }
  if (excludedUntraceableCount > 0) {
    gaps.push({
      code: "untraceable_evidence_excluded",
      severity: "blocking",
      count: excludedUntraceableCount,
    });
  }
  if (excludedRejectedOrStaleCount > 0) {
    gaps.push({
      code: "rejected_or_stale_evidence_excluded",
      severity: "info",
      count: excludedRejectedOrStaleCount,
    });
  }
  if (eligible.length > 0 && reviewedEvidenceCount === 0) {
    gaps.push({ code: "no_reviewed_evidence", severity: "warning" });
  }
  if (eligible.length > 0) {
    gaps.push({ code: "cohort_coverage_unavailable", severity: "info" });
  }

  return {
    persisted: false,
    generatedBy: "deterministic-client-projection",
    inputEvidenceCount: evidence.length,
    eligibleEvidenceCount: eligible.length,
    excludedSyntheticCount,
    excludedUntraceableCount,
    excludedRejectedOrStaleCount,
    reviewedEvidenceCount,
    claims,
    opportunities,
    gaps,
  };
}
