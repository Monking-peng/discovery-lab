export type Study = {
  id: string;
  revisionId?: string;
  title: string;
  decisionQuestion: string;
  status: "active" | "draft" | "archived";
  updatedAt: string;
  sourceCount: number;
  evidenceCount: number;
};

export type SourceItem = {
  id: string;
  name: string;
  type: string;
  status: "queued" | "uploading" | "processing" | "ready" | "failed";
  progress?: number;
  updatedAt?: string;
  revisionId?: string;
  revision?: number;
};

export type Evidence = {
  id: string;
  revisionId?: string;
  revision?: number;
  runId?: string;
  runStepId?: string;
  studyId: string;
  kind: "pain" | "need" | "behavior" | "constraint" | "counterevidence" | "signal";
  title: string;
  quote: string;
  observation: string;
  interpretation: string;
  inference?: string;
  sourceName: string;
  sourceId: string;
  sourceRevisionId?: string;
  sourceType: string;
  locatorLabel: string;
  reviewStatus: "approved" | "reviewed" | "pending" | "rejected" | "stale";
  confidence: number;
  relationship: "supports" | "challenges" | "neutral";
  tags: string[];
  syntheticDemo: boolean;
  humanAuthored?: boolean;
  parentRevisionId?: string;
  contentHash?: string;
  createdAt: string;
};

export type RunStep = {
  id: string;
  name: string;
  ordinal: number;
  status: "pending" | "ready" | "running" | "waiting_human" | "succeeded" | "failed" | "skipped" | "cancelled";
  outputSummary: Record<string, unknown>;
  error: Record<string, unknown> | null;
  startedAt?: string;
  completedAt?: string;
  createdAt: string;
};

export type RunSummary = {
  id: string;
  studyId: string;
  sourceId?: string;
  workflowName: string;
  workflowVersion: string;
  status: "queued" | "running" | "succeeded" | "partially_succeeded" | "failed" | "cancelled";
  outputSummary: Record<string, unknown>;
  error: Record<string, unknown> | null;
  startedAt?: string;
  completedAt?: string;
  createdAt: string;
  steps: RunStep[];
};

export type ListResult<T> = {
  items: T[];
  total: number;
};

export type EvidenceContext = {
  evidenceId: string;
  evidenceRevisionId?: string;
  sourceRevisionId?: string;
  sourceName: string;
  locatorLabel: string;
  before: string;
  highlight: string;
  after: string;
  sourceContentHash?: string;
  segmentContentHash?: string;
  evidenceContentHash?: string;
  /** The immutable Evidence Revision returned by context replay, not the current list item. */
  evidenceSnapshot?: Evidence;
  integrity?: {
    quoteMatchesSegment: boolean;
    segmentHashMatches: boolean;
    evidenceHashMatches: boolean;
  };
};

export const CLAIM_STATUSES = ["PROPOSED", "REVIEWED", "REJECTED", "STALE", "INVALIDATED"] as const;
export type ClaimStatus = (typeof CLAIM_STATUSES)[number];
export const CLAIM_REVIEW_DECISIONS = ["ACCEPT", "REQUEST_CHANGES", "REJECT"] as const;
export type ClaimReviewDecision = (typeof CLAIM_REVIEW_DECISIONS)[number];
export const CLAIM_RELATIONS = ["supports", "contradicts", "contextualizes", "insufficient_for"] as const;
export type ClaimEvidenceRelation = (typeof CLAIM_RELATIONS)[number];
export const COUNTEREVIDENCE_STATUSES = ["NOT_RUN", "SEARCHED_NONE_FOUND", "FOUND"] as const;
export type CounterevidenceStatus = (typeof COUNTEREVIDENCE_STATUSES)[number];

export type EvidenceReview = {
  id: string;
  evidenceId: string;
  evidenceRevisionId: string;
  decision: ClaimReviewDecision;
  reviewer: string;
  rationale: string | null;
  clientRequestId: string;
  createdAt: string;
};

export type EvidenceRevisionAuthorInput = {
  baseRevisionId: string;
  observation: string;
  interpretation?: string | null;
  inference?: string | null;
  confidence: number;
  tags: string[];
  editor: string;
  rationale: string;
  clientRequestId: string;
};

export type AuthoredEvidenceRevision = {
  evidenceId: string;
  evidenceRevisionId: string;
  parentRevisionId: string;
  revision: number;
  sourceRevisionId: string;
  segmentId: string;
  reviewStatus: "PROPOSED";
  contentHash: string;
  provenance: Record<string, unknown>;
  clientRequestId: string;
  createdAt: string;
};

export type ClaimEvidenceEdge = {
  id: string;
  evidenceId: string;
  evidenceRevisionId: string;
  sourceId: string;
  sourceRevisionId: string;
  relation: ClaimEvidenceRelation;
  rationale: string;
  relevance: number;
  relationConfirmed: boolean;
  contextUrl: string;
  latestEvidenceReview: EvidenceReview | null;
};

export type ClaimReview = {
  id: string;
  claimId: string;
  claimRevisionId: string;
  decision: ClaimReviewDecision;
  reviewer: string;
  rationale: string | null;
  clientRequestId: string;
  createdAt: string;
  evidenceReviewSnapshot: Record<string, string>;
};

export type Claim = {
  id: string;
  claimId: string;
  studyId: string;
  status: ClaimStatus;
  revisionStatus: ClaimStatus;
  isCurrent: boolean;
  publicationBlockers: string[];
  revisionId: string;
  claimRevisionId: string;
  revision: number;
  topicKey: string;
  statement: string;
  summary: string | null;
  rationale: string;
  confidence: number;
  counterevidenceStatus: CounterevidenceStatus;
  counterevidenceSummary: string | null;
  provenance: Record<string, unknown>;
  contentHash: string;
  createdAt: string;
  evidenceEdges: ClaimEvidenceEdge[];
  latestReview: ClaimReview | null;
};

export type ClaimEvidenceEdgeInput = {
  evidenceId: string;
  evidenceRevisionId: string;
  relation: ClaimEvidenceRelation;
  rationale: string;
  relevance: number;
  relationConfirmed: boolean;
};

export type ClaimRevisionInput = {
  topicKey: string;
  statement: string;
  summary?: string | null;
  rationale: string;
  confidence: number;
  counterevidenceStatus: CounterevidenceStatus;
  counterevidenceSummary?: string | null;
  provenance?: Record<string, unknown>;
  evidenceEdges: ClaimEvidenceEdgeInput[];
  clientRequestId: string;
};

export type ArtifactReviewInput = {
  decision: ClaimReviewDecision;
  reviewer: string;
  rationale?: string | null;
  clientRequestId: string;
};

export const OPPORTUNITY_STATUSES = ["DRAFT"] as const;
export type OpportunityStatus = (typeof OPPORTUNITY_STATUSES)[number];

export type OpportunityDraft = {
  id: string;
  studyId: string;
  claimId: string;
  claimRevisionId: string;
  status: OpportunityStatus;
  title: string;
  problemStatement: string;
  desiredOutcome: string;
  nextStep: string;
  rationale: string | null;
  confidence: number;
  assumptions: string[];
  risks: string[];
  provenance: Record<string, unknown>;
  contentHash: string;
  clientRequestId: string;
  createdAt: string;
  claimStatement: string;
  claimContextUrl: string;
  publishable: false;
  publicationBlockers: string[];
};

export type OpportunityDraftInput = {
  claimId: string;
  claimRevisionId: string;
  title: string;
  problemStatement: string;
  desiredOutcome: string;
  nextStep: string;
  rationale?: string | null;
  confidence: number;
  assumptions: string[];
  risks: string[];
  provenance?: Record<string, unknown>;
  clientRequestId: string;
};

export const RETRIEVAL_PURPOSES = ["support", "counterevidence", "explore"] as const;
export type RetrievalPurpose = (typeof RETRIEVAL_PURPOSES)[number];

export type RetrievalCreateInput = {
  query: string;
  purpose: RetrievalPurpose;
  limit: number;
  clientRequestId: string;
};

export type ContextManifestEvidence = {
  evidenceType: string;
  quote: string;
  observation: string | null;
  interpretation: string | null;
  inference: string | null;
  locator: Record<string, unknown>;
};

export type ContextManifestEvidenceReview = {
  decision: "ACCEPT";
  reviewer: string;
  rationale: string | null;
  createdAt: string;
};

export type ContextManifestItem = {
  id: string;
  rank: number;
  evidenceId: string;
  evidenceRevisionId: string;
  sourceId: string;
  sourceRevisionId: string;
  evidenceReviewId: string;
  evidenceContentHash: string;
  sourceContentHash: string;
  contextUrl: string;
  sourceName: string;
  evidence: ContextManifestEvidence;
  review: ContextManifestEvidenceReview;
  lexicalScore: number;
  vectorScore: number;
  hybridScore: number;
  lexicalRank: number;
  vectorRank: number;
};

export type ContextManifest = {
  id: string;
  contextManifestId: string;
  studyId: string;
  query: string;
  purpose: RetrievalPurpose;
  resultLimit: number;
  profileName: string;
  profileVersion: string;
  lexicalAlgorithm: string;
  vectorAlgorithm: string;
  vectorAlgorithmDescription: string;
  fusionAlgorithm: string;
  queryHandling: string;
  contentHash: string;
  clientRequestId: string;
  createdAt: string;
  items: ContextManifestItem[];
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly code?: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function number(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function optionalNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function listPayload(payload: unknown): unknown[] {
  if (Array.isArray(payload)) return payload;
  if (!isRecord(payload)) return [];
  for (const key of ["items", "data", "results", "studies", "evidence"]) {
    if (Array.isArray(payload[key])) return payload[key] as unknown[];
  }
  return [];
}

function pagedPayload(payload: unknown): { items: unknown[]; total: number } {
  const items = listPayload(payload);
  const item = isRecord(payload) ? payload : {};
  return { items, total: number(item.total, items.length) };
}

function normalizeStatus<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === "string" && allowed.includes(value as T) ? (value as T) : fallback;
}

function normalizeStudy(value: unknown): Study {
  const item = isRecord(value) ? value : {};
  return {
    id: text(item.id),
    revisionId: text(item.revisionId, text(item.revision_id)) || undefined,
    title: text(item.title, text(item.name, "Untitled study")),
    decisionQuestion: text(item.decisionQuestion, text(item.decision_question, "尚未设置决策问题")),
    status: normalizeStatus(item.status, ["active", "draft", "archived"] as const, "draft"),
    updatedAt: text(item.updatedAt, text(item.updated_at, new Date().toISOString())),
    sourceCount: number(item.sourceCount, number(item.source_count)),
    evidenceCount: number(item.evidenceCount, number(item.evidence_count)),
  };
}

function compactTitle(value: string, maxLength = 110): string {
  const compact = value.replace(/\s+/g, " ").trim();
  if (compact.length <= maxLength) return compact;
  return `${compact.slice(0, maxLength - 1).trimEnd()}…`;
}

function normalizeSourceStatus(value: unknown): SourceItem["status"] {
  const normalized = text(value).toLowerCase();
  if (normalized === "uploaded" || normalized === "queued") return "queued";
  if (normalized === "uploading") return "uploading";
  if (normalized === "processing") return "processing";
  if (normalized === "processed" || normalized === "ready" || normalized === "succeeded") return "ready";
  if (normalized === "failed") return "failed";
  return "queued";
}

function normalizeSource(value: unknown): SourceItem {
  const item = isRecord(value) ? value : {};
  const revision = isRecord(item.revision) ? item.revision : {};
  const status = normalizeSourceStatus(item.status ?? item.domain_status);
  return {
    id: text(item.id, text(item.source_id)),
    name: text(item.name, text(item.display_name, text(revision.filename, "Untitled source"))),
    type: text(item.type, text(item.source_type, text(revision.mime_type, "document"))),
    status,
    progress: optionalNumber(item.progress) ?? (status === "ready" ? 100 : status === "processing" ? 55 : 0),
    updatedAt: text(item.updatedAt, text(item.updated_at, text(item.created_at))) || undefined,
    revisionId: text(item.revisionId, text(item.revision_id, text(revision.id))) || undefined,
    revision: optionalNumber(item.revision_number) ?? optionalNumber(revision.revision),
  };
}

function normalizeEvidence(value: unknown): Evidence {
  const item = isRecord(value) ? value : {};
  const locator = isRecord(item.locator) ? item.locator : {};
  const source = isRecord(item.source) ? item.source : {};
  const provenance = isRecord(item.provenance) ? item.provenance : {};
  const provenanceRun = isRecord(provenance.run) ? provenance.run : {};
  const quote = text(item.quote, text(item.raw_quote));
  const observation = text(item.observation);
  const tags = Array.isArray(item.tags) ? item.tags.filter((tag): tag is string => typeof tag === "string") : [];
  const syntheticDemo = provenance.synthetic_demo === true || tags.some((tag) => {
    const normalized = tag.toLowerCase().replaceAll("_", "-");
    return normalized === "synthetic-demo" || normalized === "demo-extractor";
  });
  const apiTitle = text(item.title, observation || "Untitled evidence");
  return {
    id: text(item.id),
    revisionId:
      text(item.revisionId, text(item.revision_id, text(item.evidence_revision_id))) || undefined,
    revision: optionalNumber(item.revision),
    runId: text(item.runId, text(item.run_id, text(provenanceRun.run_id))) || undefined,
    runStepId:
      text(item.runStepId, text(item.run_step_id, text(provenanceRun.extract_step_id))) || undefined,
    studyId: text(item.studyId, text(item.study_id)),
    kind: normalizeStatus(
      item.kind,
      ["pain", "need", "behavior", "constraint", "counterevidence", "signal"] as const,
      "signal",
    ),
    title: syntheticDemo && quote ? compactTitle(quote) : apiTitle,
    quote,
    observation,
    interpretation: text(item.interpretation),
    inference: text(item.inference) || undefined,
    sourceName: text(item.sourceName, text(item.source_name, text(source.name, "Unknown source"))),
    sourceId: text(item.sourceId, text(item.source_id, text(source.id))),
    sourceRevisionId:
      text(item.sourceRevisionId, text(item.source_revision_id, text(source.revision_id))) || undefined,
    sourceType: text(item.sourceType, text(item.source_type, text(source.type, "document"))),
    locatorLabel: text(
      item.locatorLabel,
      text(item.locator_label, text(locator.label, text(locator.display, "Locator unavailable"))),
    ),
    reviewStatus: normalizeStatus(
      item.reviewStatus ?? item.review_status,
      ["approved", "reviewed", "pending", "rejected", "stale"] as const,
      "pending",
    ),
    confidence: Math.min(1, Math.max(0, number(item.confidence, 0))),
    relationship: normalizeStatus(
      item.relationship,
      ["supports", "challenges", "neutral"] as const,
      "neutral",
    ),
    tags,
    syntheticDemo,
    humanAuthored: provenance.human_authored === true,
    parentRevisionId: text(provenance.parent_revision_id) || undefined,
    contentHash: text(item.contentHash, text(item.content_hash)) || undefined,
    createdAt: text(item.createdAt, text(item.created_at, new Date().toISOString())),
  };
}

function invalidResponse(field: string): never {
  throw new ApiError(`API response is missing or invalid: ${field}`, undefined, "invalid_response", { field });
}

function requiredRecord(value: unknown, field: string): Record<string, unknown> {
  return isRecord(value) ? value : invalidResponse(field);
}

function requiredString(value: unknown, field: string): string {
  return typeof value === "string" && value.trim() ? value : invalidResponse(field);
}

function requiredNumber(value: unknown, field: string): number {
  return typeof value === "number" && Number.isFinite(value) ? value : invalidResponse(field);
}

function requiredBoolean(value: unknown, field: string): boolean {
  return typeof value === "boolean" ? value : invalidResponse(field);
}

function requiredEnum<T extends string>(value: unknown, allowed: readonly T[], field: string): T {
  return typeof value === "string" && allowed.includes(value as T)
    ? value as T
    : invalidResponse(field);
}

function nullableString(value: unknown, field: string): string | null {
  if (value === null || value === undefined) return null;
  return typeof value === "string" ? value : invalidResponse(field);
}

function normalizeEvidenceReview(value: unknown, field = "evidence_review"): EvidenceReview {
  const item = requiredRecord(value, field);
  return {
    id: requiredString(item.id, `${field}.id`),
    evidenceId: requiredString(item.evidence_id, `${field}.evidence_id`),
    evidenceRevisionId: requiredString(item.evidence_revision_id, `${field}.evidence_revision_id`),
    decision: requiredEnum(item.decision, CLAIM_REVIEW_DECISIONS, `${field}.decision`),
    reviewer: requiredString(item.reviewer, `${field}.reviewer`),
    rationale: nullableString(item.rationale, `${field}.rationale`),
    clientRequestId: requiredString(item.client_request_id, `${field}.client_request_id`),
    createdAt: requiredString(item.created_at, `${field}.created_at`),
  };
}

function normalizeAuthoredEvidenceRevision(value: unknown): AuthoredEvidenceRevision {
  const item = requiredRecord(value, "authored_evidence_revision");
  const provenance = requiredRecord(item.provenance, "authored_evidence_revision.provenance");
  return {
    evidenceId: requiredString(item.evidence_id, "authored_evidence_revision.evidence_id"),
    evidenceRevisionId: requiredString(
      item.evidence_revision_id,
      "authored_evidence_revision.evidence_revision_id",
    ),
    parentRevisionId: requiredString(
      item.parent_revision_id,
      "authored_evidence_revision.parent_revision_id",
    ),
    revision: requiredNumber(item.revision, "authored_evidence_revision.revision"),
    sourceRevisionId: requiredString(
      item.source_revision_id,
      "authored_evidence_revision.source_revision_id",
    ),
    segmentId: requiredString(item.segment_id, "authored_evidence_revision.segment_id"),
    reviewStatus: requiredEnum(
      item.review_status,
      ["PROPOSED"] as const,
      "authored_evidence_revision.review_status",
    ),
    contentHash: requiredString(item.content_hash, "authored_evidence_revision.content_hash"),
    provenance,
    clientRequestId: requiredString(
      item.client_request_id,
      "authored_evidence_revision.client_request_id",
    ),
    createdAt: requiredString(item.created_at, "authored_evidence_revision.created_at"),
  };
}

function normalizeClaimReview(value: unknown, field = "claim_review"): ClaimReview {
  const item = requiredRecord(value, field);
  const evidenceReviewSnapshot = requiredRecord(
    item.evidence_review_snapshot,
    `${field}.evidence_review_snapshot`,
  );
  if (Object.values(evidenceReviewSnapshot).some((entry) => typeof entry !== "string")) {
    invalidResponse(`${field}.evidence_review_snapshot`);
  }
  return {
    id: requiredString(item.id, `${field}.id`),
    claimId: requiredString(item.claim_id, `${field}.claim_id`),
    claimRevisionId: requiredString(item.claim_revision_id, `${field}.claim_revision_id`),
    decision: requiredEnum(item.decision, CLAIM_REVIEW_DECISIONS, `${field}.decision`),
    reviewer: requiredString(item.reviewer, `${field}.reviewer`),
    rationale: nullableString(item.rationale, `${field}.rationale`),
    clientRequestId: requiredString(item.client_request_id, `${field}.client_request_id`),
    createdAt: requiredString(item.created_at, `${field}.created_at`),
    evidenceReviewSnapshot: evidenceReviewSnapshot as Record<string, string>,
  };
}

function normalizeClaimEdge(value: unknown, index: number): ClaimEvidenceEdge {
  const field = `claim.evidence_edges[${index}]`;
  const item = requiredRecord(value, field);
  const relevance = requiredNumber(item.relevance, `${field}.relevance`);
  if (relevance < 0 || relevance > 1) invalidResponse(`${field}.relevance`);
  return {
    id: requiredString(item.id, `${field}.id`),
    evidenceId: requiredString(item.evidence_id, `${field}.evidence_id`),
    evidenceRevisionId: requiredString(item.evidence_revision_id, `${field}.evidence_revision_id`),
    sourceId: requiredString(item.source_id, `${field}.source_id`),
    sourceRevisionId: requiredString(item.source_revision_id, `${field}.source_revision_id`),
    relation: requiredEnum(item.relation, CLAIM_RELATIONS, `${field}.relation`),
    rationale: requiredString(item.rationale, `${field}.rationale`),
    relevance,
    relationConfirmed: requiredBoolean(item.relation_confirmed, `${field}.relation_confirmed`),
    contextUrl: requiredString(item.context_url, `${field}.context_url`),
    latestEvidenceReview: item.latest_evidence_review == null
      ? null
      : normalizeEvidenceReview(item.latest_evidence_review, `${field}.latest_evidence_review`),
  };
}

function normalizeClaim(value: unknown): Claim {
  const item = requiredRecord(value, "claim");
  if (!Array.isArray(item.evidence_edges)) invalidResponse("claim.evidence_edges");
  const confidence = requiredNumber(item.confidence, "claim.confidence");
  if (confidence < 0 || confidence > 1) invalidResponse("claim.confidence");
  const revisionId = requiredString(item.revision_id, "claim.revision_id");
  const claimRevisionId = requiredString(item.claim_revision_id, "claim.claim_revision_id");
  if (revisionId !== claimRevisionId) invalidResponse("claim.revision_id");
  if (!Array.isArray(item.publication_blockers) || item.publication_blockers.some((entry) => typeof entry !== "string")) {
    invalidResponse("claim.publication_blockers");
  }
  return {
    id: requiredString(item.id, "claim.id"),
    claimId: requiredString(item.claim_id, "claim.claim_id"),
    studyId: requiredString(item.study_id, "claim.study_id"),
    status: requiredEnum(item.status, CLAIM_STATUSES, "claim.status"),
    revisionStatus: requiredEnum(item.revision_status, CLAIM_STATUSES, "claim.revision_status"),
    isCurrent: requiredBoolean(item.is_current, "claim.is_current"),
    publicationBlockers: item.publication_blockers as string[],
    revisionId,
    claimRevisionId,
    revision: requiredNumber(item.revision, "claim.revision"),
    topicKey: requiredString(item.topic_key, "claim.topic_key"),
    statement: requiredString(item.statement, "claim.statement"),
    summary: nullableString(item.summary, "claim.summary"),
    rationale: requiredString(item.rationale, "claim.rationale"),
    confidence,
    counterevidenceStatus: requiredEnum(
      item.counterevidence_status,
      COUNTEREVIDENCE_STATUSES,
      "claim.counterevidence_status",
    ),
    counterevidenceSummary: nullableString(
      item.counterevidence_summary,
      "claim.counterevidence_summary",
    ),
    provenance: isRecord(item.provenance) ? item.provenance : invalidResponse("claim.provenance"),
    contentHash: requiredString(item.content_hash, "claim.content_hash"),
    createdAt: requiredString(item.created_at, "claim.created_at"),
    evidenceEdges: item.evidence_edges.map(normalizeClaimEdge),
    latestReview: item.latest_review == null
      ? null
      : normalizeClaimReview(item.latest_review, "claim.latest_review"),
  };
}

function requiredStringList(value: unknown, field: string): string[] {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string")) {
    invalidResponse(field);
  }
  return value as string[];
}

function normalizeOpportunityDraft(value: unknown): OpportunityDraft {
  const item = requiredRecord(value, "opportunity");
  const confidence = requiredNumber(item.confidence, "opportunity.confidence");
  if (confidence < 0 || confidence > 1) invalidResponse("opportunity.confidence");
  const publishable = requiredBoolean(item.publishable, "opportunity.publishable");
  if (publishable) invalidResponse("opportunity.publishable");
  return {
    id: requiredString(item.id, "opportunity.id"),
    studyId: requiredString(item.study_id, "opportunity.study_id"),
    claimId: requiredString(item.claim_id, "opportunity.claim_id"),
    claimRevisionId: requiredString(item.claim_revision_id, "opportunity.claim_revision_id"),
    status: requiredEnum(item.status, OPPORTUNITY_STATUSES, "opportunity.status"),
    title: requiredString(item.title, "opportunity.title"),
    problemStatement: requiredString(item.problem_statement, "opportunity.problem_statement"),
    desiredOutcome: requiredString(item.desired_outcome, "opportunity.desired_outcome"),
    nextStep: requiredString(item.next_step, "opportunity.next_step"),
    rationale: nullableString(item.rationale, "opportunity.rationale"),
    confidence,
    assumptions: requiredStringList(item.assumptions, "opportunity.assumptions"),
    risks: requiredStringList(item.risks, "opportunity.risks"),
    provenance: requiredRecord(item.provenance, "opportunity.provenance"),
    contentHash: requiredString(item.content_hash, "opportunity.content_hash"),
    clientRequestId: requiredString(item.client_request_id, "opportunity.client_request_id"),
    createdAt: requiredString(item.created_at, "opportunity.created_at"),
    claimStatement: requiredString(item.claim_statement, "opportunity.claim_statement"),
    claimContextUrl: requiredString(item.claim_context_url, "opportunity.claim_context_url"),
    publishable: false,
    publicationBlockers: requiredStringList(
      item.publication_blockers,
      "opportunity.publication_blockers",
    ),
  };
}

function normalizeContextManifestEvidence(value: unknown, field: string): ContextManifestEvidence {
  const item = requiredRecord(value, field);
  return {
    evidenceType: requiredString(item.evidence_type, `${field}.evidence_type`),
    quote: requiredString(item.quote, `${field}.quote`),
    observation: nullableString(item.observation, `${field}.observation`),
    interpretation: nullableString(item.interpretation, `${field}.interpretation`),
    inference: nullableString(item.inference, `${field}.inference`),
    locator: requiredRecord(item.locator, `${field}.locator`),
  };
}

function normalizeContextManifestReview(
  value: unknown,
  field: string,
): ContextManifestEvidenceReview {
  const item = requiredRecord(value, field);
  return {
    decision: requiredEnum(item.decision, ["ACCEPT"] as const, `${field}.decision`),
    reviewer: requiredString(item.reviewer, `${field}.reviewer`),
    rationale: nullableString(item.rationale, `${field}.rationale`),
    createdAt: requiredString(item.created_at, `${field}.created_at`),
  };
}

function normalizeContextManifestItem(value: unknown, index: number): ContextManifestItem {
  const field = `context_manifest.items[${index}]`;
  const item = requiredRecord(value, field);
  return {
    id: requiredString(item.id, `${field}.id`),
    rank: requiredNumber(item.rank, `${field}.rank`),
    evidenceId: requiredString(item.evidence_id, `${field}.evidence_id`),
    evidenceRevisionId: requiredString(
      item.evidence_revision_id,
      `${field}.evidence_revision_id`,
    ),
    sourceId: requiredString(item.source_id, `${field}.source_id`),
    sourceRevisionId: requiredString(item.source_revision_id, `${field}.source_revision_id`),
    evidenceReviewId: requiredString(item.evidence_review_id, `${field}.evidence_review_id`),
    evidenceContentHash: requiredString(
      item.evidence_content_hash,
      `${field}.evidence_content_hash`,
    ),
    sourceContentHash: requiredString(item.source_content_hash, `${field}.source_content_hash`),
    contextUrl: requiredString(item.context_url, `${field}.context_url`),
    sourceName: requiredString(item.source_name, `${field}.source_name`),
    evidence: normalizeContextManifestEvidence(item.evidence, `${field}.evidence`),
    review: normalizeContextManifestReview(item.review, `${field}.review`),
    lexicalScore: requiredNumber(item.lexical_score, `${field}.lexical_score`),
    vectorScore: requiredNumber(item.vector_score, `${field}.vector_score`),
    hybridScore: requiredNumber(item.hybrid_score, `${field}.hybrid_score`),
    lexicalRank: requiredNumber(item.lexical_rank, `${field}.lexical_rank`),
    vectorRank: requiredNumber(item.vector_rank, `${field}.vector_rank`),
  };
}

function normalizeContextManifest(value: unknown): ContextManifest {
  const item = requiredRecord(value, "context_manifest");
  if (!Array.isArray(item.items)) invalidResponse("context_manifest.items");
  const id = requiredString(item.id, "context_manifest.id");
  const contextManifestId = requiredString(
    item.context_manifest_id,
    "context_manifest.context_manifest_id",
  );
  if (id !== contextManifestId) invalidResponse("context_manifest.context_manifest_id");
  const resultLimit = requiredNumber(item.result_limit, "context_manifest.result_limit");
  if (!Number.isInteger(resultLimit) || resultLimit < 1 || resultLimit > 50) {
    invalidResponse("context_manifest.result_limit");
  }
  const items = item.items.map(normalizeContextManifestItem);
  if (items.some((entry, index) => entry.rank !== index + 1)) {
    invalidResponse("context_manifest.items.rank");
  }
  return {
    id,
    contextManifestId,
    studyId: requiredString(item.study_id, "context_manifest.study_id"),
    query: requiredString(item.query, "context_manifest.query"),
    purpose: requiredEnum(item.purpose, RETRIEVAL_PURPOSES, "context_manifest.purpose"),
    resultLimit,
    profileName: requiredString(item.profile_name, "context_manifest.profile_name"),
    profileVersion: requiredString(item.profile_version, "context_manifest.profile_version"),
    lexicalAlgorithm: requiredString(
      item.lexical_algorithm,
      "context_manifest.lexical_algorithm",
    ),
    vectorAlgorithm: requiredString(item.vector_algorithm, "context_manifest.vector_algorithm"),
    vectorAlgorithmDescription: requiredString(
      item.vector_algorithm_description,
      "context_manifest.vector_algorithm_description",
    ),
    fusionAlgorithm: requiredString(item.fusion_algorithm, "context_manifest.fusion_algorithm"),
    queryHandling: requiredString(item.query_handling, "context_manifest.query_handling"),
    contentHash: requiredString(item.content_hash, "context_manifest.content_hash"),
    clientRequestId: requiredString(
      item.client_request_id,
      "context_manifest.client_request_id",
    ),
    createdAt: requiredString(item.created_at, "context_manifest.created_at"),
    items,
  };
}

function normalizeRunStep(value: unknown): RunStep {
  const item = isRecord(value) ? value : {};
  const status = normalizeStatus(
    text(item.status).toLowerCase(),
    ["pending", "ready", "running", "waiting_human", "succeeded", "failed", "skipped", "cancelled"] as const,
    "pending",
  );
  return {
    id: text(item.id),
    name: text(item.name, "unknown_step"),
    ordinal: number(item.ordinal),
    status,
    outputSummary: isRecord(item.outputSummary)
      ? item.outputSummary
      : isRecord(item.output_summary)
        ? item.output_summary
        : {},
    error: isRecord(item.error) ? item.error : null,
    startedAt: text(item.startedAt, text(item.started_at)) || undefined,
    completedAt: text(item.completedAt, text(item.completed_at)) || undefined,
    createdAt: text(item.createdAt, text(item.created_at, new Date().toISOString())),
  };
}

function normalizeRun(value: unknown): RunSummary {
  const item = isRecord(value) ? value : {};
  const steps = Array.isArray(item.steps) ? item.steps.map(normalizeRunStep) : [];
  return {
    id: text(item.id),
    studyId: text(item.studyId, text(item.study_id)),
    sourceId: text(item.sourceId, text(item.source_id)) || undefined,
    workflowName: text(item.workflowName, text(item.workflow_name, "evidence_ingestion")),
    workflowVersion: text(item.workflowVersion, text(item.workflow_version, "unknown")),
    status: normalizeStatus(
      text(item.status).toLowerCase(),
      ["queued", "running", "succeeded", "partially_succeeded", "failed", "cancelled"] as const,
      "queued",
    ),
    outputSummary: isRecord(item.outputSummary)
      ? item.outputSummary
      : isRecord(item.output_summary)
        ? item.output_summary
        : {},
    error: isRecord(item.error) ? item.error : null,
    startedAt: text(item.startedAt, text(item.started_at)) || undefined,
    completedAt: text(item.completedAt, text(item.completed_at)) || undefined,
    createdAt: text(item.createdAt, text(item.created_at, new Date().toISOString())),
    steps: steps.sort((left, right) => left.ordinal - right.ordinal),
  };
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 7000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const isFormData = init?.body instanceof FormData;
  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(isFormData ? {} : init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      let code: string | undefined;
      let details: unknown;
      try {
        const payload = (await response.json()) as unknown;
        if (isRecord(payload)) {
          const detail = payload.detail;
          const errorBody = payload.error;
          if (isRecord(errorBody)) {
            message = text(errorBody.message, typeof detail === "string" ? detail : message);
            code = text(errorBody.code) || undefined;
            details = errorBody.details;
          } else if (typeof detail === "string") {
            message = detail;
          } else if (isRecord(detail)) {
            message = text(detail.message, message);
            code = text(detail.code) || undefined;
            details = detail.details;
          } else {
            message = text(payload.message, message);
            code = text(payload.code) || undefined;
            details = payload.details;
          }
        }
      } catch {
        // Keep the HTTP status when the API does not return JSON.
      }
      throw new ApiError(message, response.status, code, details);
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(`连接 ${API_URL} 超时`, undefined, "request_timeout");
    }
    throw new ApiError(
      error instanceof Error ? error.message : "API connection failed",
      undefined,
      "network_error",
    );
  } finally {
    window.clearTimeout(timeout);
  }
}

function claimInputPayload(input: ClaimRevisionInput): Record<string, unknown> {
  return {
    topic_key: input.topicKey,
    statement: input.statement,
    summary: input.summary ?? null,
    rationale: input.rationale,
    confidence: input.confidence,
    counterevidence_status: input.counterevidenceStatus,
    counterevidence_summary: input.counterevidenceSummary ?? null,
    provenance: input.provenance ?? {},
    evidence_edges: input.evidenceEdges.map((edge) => ({
      evidence_id: edge.evidenceId,
      evidence_revision_id: edge.evidenceRevisionId,
      relation: edge.relation,
      rationale: edge.rationale,
      relevance: edge.relevance,
      relation_confirmed: edge.relationConfirmed,
    })),
    client_request_id: input.clientRequestId,
  };
}

function reviewInputPayload(input: ArtifactReviewInput): Record<string, unknown> {
  return {
    decision: input.decision,
    reviewer: input.reviewer,
    rationale: input.rationale ?? null,
    client_request_id: input.clientRequestId,
  };
}

function opportunityInputPayload(input: OpportunityDraftInput): Record<string, unknown> {
  return {
    claim_id: input.claimId,
    claim_revision_id: input.claimRevisionId,
    title: input.title,
    problem_statement: input.problemStatement,
    desired_outcome: input.desiredOutcome,
    next_step: input.nextStep,
    rationale: input.rationale ?? null,
    confidence: input.confidence,
    assumptions: input.assumptions,
    risks: input.risks,
    provenance: input.provenance ?? {},
    client_request_id: input.clientRequestId,
  };
}

export const api = {
  async getStudies(): Promise<Study[]> {
    return listPayload(await request<unknown>("/v1/studies")).map(normalizeStudy);
  },

  async createStudy(input: { title: string; decisionQuestion: string }): Promise<Study> {
    return normalizeStudy(
      await request<unknown>("/v1/studies", {
        method: "POST",
        body: JSON.stringify({ title: input.title, decision_question: input.decisionQuestion }),
      }),
    );
  },

  async getEvidence(studyId: string): Promise<Evidence[]> {
    return listPayload(await request<unknown>(`/v1/studies/${encodeURIComponent(studyId)}/evidence`)).map(
      normalizeEvidence,
    );
  },

  async createContextManifest(
    studyId: string,
    input: RetrievalCreateInput,
  ): Promise<ContextManifest> {
    const manifest = normalizeContextManifest(await request<unknown>(
      `/v1/studies/${encodeURIComponent(studyId)}/retrievals`,
      {
        method: "POST",
        body: JSON.stringify({
          query: input.query,
          purpose: input.purpose,
          limit: input.limit,
          client_request_id: input.clientRequestId,
        }),
      },
    ));
    if (
      manifest.studyId !== studyId
      || manifest.query !== input.query
      || manifest.purpose !== input.purpose
      || manifest.resultLimit !== input.limit
      || manifest.clientRequestId !== input.clientRequestId
    ) {
      invalidResponse("context_manifest.request_lineage");
    }
    return manifest;
  },

  async getContextManifest(manifestId: string): Promise<ContextManifest> {
    const manifest = normalizeContextManifest(await request<unknown>(
      `/v1/context-manifests/${encodeURIComponent(manifestId)}`,
    ));
    if (manifest.contextManifestId !== manifestId) {
      invalidResponse("context_manifest.context_manifest_id");
    }
    return manifest;
  },

  async getClaims(studyId: string, limit = 100, offset = 0): Promise<ListResult<Claim>> {
    const safeLimit = Math.max(1, Math.min(100, Math.trunc(limit)));
    const safeOffset = Math.max(0, Math.trunc(offset));
    const payload = await request<unknown>(
      `/v1/studies/${encodeURIComponent(studyId)}/claims?limit=${safeLimit}&offset=${safeOffset}`,
    );
    if (!isRecord(payload) || !Array.isArray(payload.items)) invalidResponse("claims.items");
    return {
      items: payload.items.map(normalizeClaim),
      total: requiredNumber(payload.total, "claims.total"),
    };
  },

  async getOpportunities(
    studyId: string,
    limit = 100,
    offset = 0,
  ): Promise<ListResult<OpportunityDraft>> {
    const safeLimit = Math.max(1, Math.min(100, Math.trunc(limit)));
    const safeOffset = Math.max(0, Math.trunc(offset));
    const payload = await request<unknown>(
      `/v1/studies/${encodeURIComponent(studyId)}/opportunities?limit=${safeLimit}&offset=${safeOffset}`,
    );
    if (!isRecord(payload) || !Array.isArray(payload.items)) invalidResponse("opportunities.items");
    return {
      items: payload.items.map(normalizeOpportunityDraft),
      total: requiredNumber(payload.total, "opportunities.total"),
    };
  },

  async createOpportunity(
    studyId: string,
    input: OpportunityDraftInput,
  ): Promise<OpportunityDraft> {
    const draft = normalizeOpportunityDraft(await request<unknown>(
      `/v1/studies/${encodeURIComponent(studyId)}/opportunities`,
      { method: "POST", body: JSON.stringify(opportunityInputPayload(input)) },
    ));
    if (
      draft.studyId !== studyId
      || draft.claimId !== input.claimId
      || draft.claimRevisionId !== input.claimRevisionId
    ) {
      invalidResponse("opportunity.lineage");
    }
    return draft;
  },

  async getOpportunity(opportunityId: string): Promise<OpportunityDraft> {
    const draft = normalizeOpportunityDraft(await request<unknown>(
      `/v1/opportunities/${encodeURIComponent(opportunityId)}`,
    ));
    if (draft.id !== opportunityId) invalidResponse("opportunity.id");
    return draft;
  },

  async createClaim(studyId: string, input: ClaimRevisionInput): Promise<Claim> {
    return normalizeClaim(await request<unknown>(
      `/v1/studies/${encodeURIComponent(studyId)}/claims`,
      { method: "POST", body: JSON.stringify(claimInputPayload(input)) },
    ));
  },

  async getClaim(claimId: string, claimRevisionId?: string): Promise<Claim> {
    const revisionQuery = claimRevisionId
      ? `?claim_revision_id=${encodeURIComponent(claimRevisionId)}`
      : "";
    const claim = normalizeClaim(await request<unknown>(
      `/v1/claims/${encodeURIComponent(claimId)}${revisionQuery}`,
    ));
    if (claim.claimId !== claimId && claim.id !== claimId) invalidResponse("claim.claim_id");
    if (claimRevisionId && claim.claimRevisionId !== claimRevisionId) {
      invalidResponse("claim.claim_revision_id");
    }
    return claim;
  },

  async createClaimRevision(
    claimId: string,
    baseRevisionId: string,
    input: ClaimRevisionInput,
  ): Promise<Claim> {
    return normalizeClaim(await request<unknown>(
      `/v1/claims/${encodeURIComponent(claimId)}/revisions`,
      {
        method: "POST",
        body: JSON.stringify({ ...claimInputPayload(input), base_revision_id: baseRevisionId }),
      },
    ));
  },

  async reviewClaimRevision(claimRevisionId: string, input: ArtifactReviewInput): Promise<ClaimReview> {
    const review = normalizeClaimReview(await request<unknown>(
      `/v1/claim-revisions/${encodeURIComponent(claimRevisionId)}/reviews`,
      { method: "POST", body: JSON.stringify(reviewInputPayload(input)) },
    ));
    if (review.claimRevisionId !== claimRevisionId) invalidResponse("claim_review.claim_revision_id");
    return review;
  },

  async authorEvidenceRevision(
    evidenceId: string,
    input: EvidenceRevisionAuthorInput,
  ): Promise<AuthoredEvidenceRevision> {
    const revision = normalizeAuthoredEvidenceRevision(await request<unknown>(
      `/v1/evidence/${encodeURIComponent(evidenceId)}/revisions`,
      {
        method: "POST",
        body: JSON.stringify({
          base_revision_id: input.baseRevisionId,
          observation: input.observation,
          interpretation: input.interpretation ?? null,
          inference: input.inference ?? null,
          confidence: input.confidence,
          tags: input.tags,
          editor: input.editor,
          rationale: input.rationale,
          client_request_id: input.clientRequestId,
        }),
      },
    ));
    if (revision.evidenceId !== evidenceId || revision.parentRevisionId !== input.baseRevisionId) {
      invalidResponse("authored_evidence_revision.lineage");
    }
    return revision;
  },

  async reviewEvidence(
    evidenceId: string,
    evidenceRevisionId: string,
    input: ArtifactReviewInput,
  ): Promise<EvidenceReview> {
    const review = normalizeEvidenceReview(await request<unknown>(
      `/v1/evidence/${encodeURIComponent(evidenceId)}/reviews`,
      {
        method: "POST",
        body: JSON.stringify({
          evidence_revision_id: evidenceRevisionId,
          ...reviewInputPayload(input),
        }),
      },
    ));
    if (review.evidenceId !== evidenceId || review.evidenceRevisionId !== evidenceRevisionId) {
      invalidResponse("evidence_review.evidence_revision_id");
    }
    return review;
  },

  async getSources(studyId: string): Promise<ListResult<SourceItem>> {
    const payload = pagedPayload(
      await request<unknown>(`/v1/studies/${encodeURIComponent(studyId)}/sources`),
    );
    return { items: payload.items.map(normalizeSource), total: payload.total };
  },

  async getRuns(studyId: string, limit = 1): Promise<ListResult<RunSummary>> {
    const safeLimit = Math.max(1, Math.min(100, Math.trunc(limit)));
    const payload = pagedPayload(
      await request<unknown>(`/v1/studies/${encodeURIComponent(studyId)}/runs?limit=${safeLimit}`),
    );
    return { items: payload.items.map(normalizeRun), total: payload.total };
  },

  async getEvidenceContext(evidenceId: string, evidenceRevisionId?: string): Promise<EvidenceContext> {
    const revisionQuery = evidenceRevisionId
      ? `?evidence_revision_id=${encodeURIComponent(evidenceRevisionId)}`
      : "";
    const payload = await request<unknown>(
      `/v1/evidence/${encodeURIComponent(evidenceId)}/context${revisionQuery}`,
    );
    const item = isRecord(payload) && isRecord(payload.data) ? payload.data : isRecord(payload) ? payload : {};
    const integrity = isRecord(item.integrity) ? item.integrity : null;
    const source = requiredRecord(item.source, "evidence_context.source");
    const evidence = requiredRecord(item.evidence, "evidence_context.evidence");
    const evidenceSnapshot = normalizeEvidence(evidence);
    const exactEvidenceId = requiredString(evidenceSnapshot.id, "evidence_context.evidence.id");
    const exactEvidenceRevisionId = requiredString(
      evidenceSnapshot.revisionId,
      "evidence_context.evidence.evidence_revision_id",
    );
    const exactSourceRevisionId = requiredString(
      evidenceSnapshot.sourceRevisionId,
      "evidence_context.evidence.source_revision_id",
    );
    const replaySourceRevisionId = requiredString(
      source.source_revision_id,
      "evidence_context.source.source_revision_id",
    );
    if (exactEvidenceId !== evidenceId) invalidResponse("evidence_context.evidence.id");
    if (exactSourceRevisionId !== replaySourceRevisionId) {
      invalidResponse("evidence_context.source.source_revision_id");
    }
    const contextSegments = Array.isArray(item.context_segments)
      ? item.context_segments.filter(isRecord)
      : Array.isArray(item.contextSegments)
        ? item.contextSegments.filter(isRecord)
        : [];
    const targetSegment = contextSegments.find((segment) => (
      segment.is_target === true || segment.isTarget === true
    ));
    return {
      evidenceId: text(item.evidenceId, text(item.evidence_id, evidenceId)),
      evidenceRevisionId: exactEvidenceRevisionId,
      sourceRevisionId: replaySourceRevisionId,
      sourceName: text(item.sourceName, text(item.source_name, "Unknown source")),
      locatorLabel: text(item.locatorLabel, text(item.locator_label, "Locator unavailable")),
      before: text(item.before),
      highlight: text(item.highlight, text(item.quote)),
      after: text(item.after),
      sourceContentHash:
        text(item.sourceContentHash, text(item.source_content_hash, text(source.source_content_hash))) || undefined,
      segmentContentHash: targetSegment
        ? text(targetSegment.contentHash, text(targetSegment.content_hash)) || undefined
        : undefined,
      evidenceContentHash:
        text(item.evidenceContentHash, text(item.evidence_content_hash, text(evidence.content_hash))) || undefined,
      evidenceSnapshot,
      integrity: integrity
        ? {
            quoteMatchesSegment:
              integrity.quoteMatchesSegment === true || integrity.quote_matches_segment === true,
            segmentHashMatches:
              integrity.segmentHashMatches === true || integrity.segment_hash_matches === true,
            evidenceHashMatches:
              integrity.evidenceHashMatches === true || integrity.evidence_hash_matches === true,
          }
        : undefined,
    };
  },

  async uploadSource(studyId: string, file: File): Promise<SourceItem> {
    const body = new FormData();
    body.append("file", file);
    const payload = await request<unknown>(`/v1/studies/${encodeURIComponent(studyId)}/sources`, {
      method: "POST",
      body,
    }, 30000);
    const item = isRecord(payload) && isRecord(payload.data) ? payload.data : payload;
    const normalized = normalizeSource(item);
    return {
      ...normalized,
      name: normalized.name === "Untitled source" ? file.name : normalized.name,
      type: normalized.type === "document" ? file.type || file.name.split(".").pop() || "file" : normalized.type,
    };
  },

  async processSource(sourceId: string): Promise<RunSummary> {
    return normalizeRun(
      await request<unknown>(
        `/v1/sources/${encodeURIComponent(sourceId)}:process`,
        { method: "POST" },
        30000,
      ),
    );
  },
};
