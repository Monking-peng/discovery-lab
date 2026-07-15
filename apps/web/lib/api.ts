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
  integrity?: {
    quoteMatchesSegment: boolean;
    segmentHashMatches: boolean;
    evidenceHashMatches: boolean;
  };
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
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
    contentHash: text(item.contentHash, text(item.content_hash)) || undefined,
    createdAt: text(item.createdAt, text(item.created_at, new Date().toISOString())),
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
      try {
        const detail = (await response.json()) as unknown;
        if (isRecord(detail)) message = text(detail.detail, text(detail.message, message));
      } catch {
        // Keep the HTTP status when the API does not return JSON.
      }
      throw new ApiError(message, response.status);
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(`连接 ${API_URL} 超时`);
    }
    throw new ApiError(error instanceof Error ? error.message : "API connection failed");
  } finally {
    window.clearTimeout(timeout);
  }
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
    const source = isRecord(item.source) ? item.source : {};
    const evidence = isRecord(item.evidence) ? item.evidence : {};
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
      evidenceRevisionId:
        text(evidence.evidenceRevisionId, text(evidence.evidence_revision_id)) || undefined,
      sourceRevisionId:
        text(source.sourceRevisionId, text(source.source_revision_id)) || undefined,
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
