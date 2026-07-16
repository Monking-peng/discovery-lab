"use client";

import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  BookOpenCheck,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  Clock3,
  FileArchive,
  FileCheck2,
  FileSpreadsheet,
  FileText,
  Filter,
  FlaskConical,
  FolderKanban,
  Gauge,
  GitBranch,
  Layers3,
  Languages,
  LayoutDashboard,
  Link2,
  LockKeyhole,
  LoaderCircle,
  MoreHorizontal,
  PencilLine,
  Plus,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  API_URL,
  ApiError,
  api,
  type ClaimReviewDecision,
  type Evidence,
  type EvidenceContext,
  type EvidenceRevisionAuthorInput,
  type RunStep,
  type RunSummary,
  type SourceItem,
  type Study,
} from "@/lib/api";
import { AgentRunCenter } from "@/components/agent-run-center";
import { ClaimsOpportunitiesView } from "@/components/claims-opportunities-view";
import { EvaluationCenter } from "@/components/evaluation-center";
import { OverviewCenter } from "@/components/overview-center";
import { ProductDecisionCenter } from "@/components/product-decision-center";
import { RetrievalLab } from "@/components/retrieval-lab";
import { demoAgentEvents, demoContexts, demoEvidence, demoSources, demoStudies } from "@/lib/demo-data";
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  getInitialLocale,
  serializeLocaleCookie,
  serializeLocaleForStorage,
  translate,
  type Locale,
  type MessageKey,
  type TranslationVars,
} from "@/lib/i18n";

type ConnectionMode = "loading" | "live" | "demo";
type WorkbenchView = "overview" | "evidence" | "claims" | "runs" | "eval" | "product";
type EvidenceDetailTab = "summary" | "review" | "source";
type Translator = (key: MessageKey, vars?: TranslationVars) => string;
type AgentEvent = {
  id: string;
  label: string;
  detail: string;
  status: "complete" | "running" | "pending" | "failed";
  time: string;
};

const kindMessageKeys: Record<Evidence["kind"], MessageKey> = {
  pain: "kind.pain",
  need: "kind.need",
  behavior: "kind.behavior",
  constraint: "kind.constraint",
  counterevidence: "kind.counterevidence",
  signal: "kind.signal",
};

const reviewMessageKeys: Record<Evidence["reviewStatus"], MessageKey> = {
  approved: "review.approved",
  reviewed: "review.reviewed",
  pending: "review.pending",
  rejected: "review.rejected",
  stale: "review.stale",
};

const relationshipMessageKeys: Record<Evidence["relationship"], MessageKey> = {
  supports: "relationship.supports",
  challenges: "relationship.challenges",
  neutral: "relationship.neutral",
};

function formatRelativeDate(value: string, t: Translator) {
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) return t("relative.today");
  const days = Math.floor((Date.now() - time) / 86_400_000);
  if (days <= 0) return t("relative.today");
  if (days === 1) return t("relative.yesterday");
  return t("relative.days", { count: days });
}

function fileIcon(type: string) {
  const normalized = type.toLowerCase();
  if (normalized.includes("csv") || normalized.includes("sheet")) return FileSpreadsheet;
  if (normalized.includes("zip") || normalized.includes("archive") || normalized.includes("snapshot")) return FileArchive;
  return FileText;
}

function safeMessage(error: unknown, t: Translator) {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : t("general.unknownError");
}

function shortHash(value: string | undefined, t: Translator) {
  if (!value) return t("general.unavailable");
  if (value.length <= 24) return value;
  return `${value.slice(0, 12)}…${value.slice(-8)}`;
}

function requestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function exactEvidenceSnapshot(
  value: EvidenceContext,
  expected: Evidence,
  expectedRevisionId: string,
  t: Translator,
): Evidence {
  const snapshot = value.evidenceSnapshot;
  if (
    value.evidenceId !== expected.id
    || value.evidenceRevisionId !== expectedRevisionId
    || value.sourceRevisionId !== expected.sourceRevisionId
    || !snapshot
    || snapshot.id !== expected.id
    || snapshot.revisionId !== expectedRevisionId
    || snapshot.studyId !== expected.studyId
    || snapshot.sourceId !== expected.sourceId
    || snapshot.sourceRevisionId !== expected.sourceRevisionId
  ) {
    throw new ApiError(t("context.revisionMismatch"));
  }
  return snapshot;
}

function valueRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
}

function summaryNumber(summary: Record<string, unknown>, key: string) {
  const value = summary[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function stepDetail(step: RunStep, t: Translator) {
  const summary = step.outputSummary;
  if (step.name === "parse_source") {
    const count = summaryNumber(summary, "segment_count");
    const kinds = Array.isArray(summary.source_kinds)
      ? summary.source_kinds.filter((item): item is string => typeof item === "string").join(", ")
      : "";
    return [count === undefined ? t("runStep.sourceParsed") : t("runStep.segments", { count }), kinds]
      .filter(Boolean)
      .join(" · ");
  }
  if (step.name === "extract_evidence") {
    const count = summaryNumber(summary, "evidence_candidate_count");
    const extractor = valueRecord(summary.extractor);
    const extractorName = typeof extractor.name === "string" ? extractor.name : "";
    const synthetic = summary.synthetic_demo === true ? t("runStep.synthetic") : "";
    return [count === undefined ? t("runStep.evidenceExtracted") : t("runStep.candidates", { count }), extractorName, synthetic]
      .filter(Boolean)
      .join(" · ");
  }
  if (step.name === "verify_citations") {
    const checked = summaryNumber(summary, "checked_count");
    const verified = summaryNumber(summary, "verified_count");
    if (checked !== undefined && verified !== undefined) return t("runStep.verified", { verified, checked });
    return t("runStep.integrityChecked");
  }
  const errorCode = typeof step.error?.code === "string" ? step.error.code : "";
  return errorCode || step.status.replaceAll("_", " ");
}

function eventStatus(step: RunStep): AgentEvent["status"] {
  if (step.status === "succeeded") return "complete";
  if (step.status === "running") return "running";
  if (step.status === "failed" || step.status === "cancelled") return "failed";
  return "pending";
}

function eventTime(step: RunStep, locale: Locale) {
  const raw = step.completedAt || step.startedAt || step.createdAt;
  const date = new Date(raw);
  return Number.isFinite(date.getTime())
    ? date.toLocaleTimeString(locale, { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "—";
}

function agentEventsFromRun(run: RunSummary, t: Translator, locale: Locale): AgentEvent[] {
  const stepNames = ["parse_source", "extract_evidence", "verify_citations"];
  const namedSteps = stepNames.flatMap((name) => run.steps.filter((step) => step.name === name));
  const steps = namedSteps.length > 0 ? namedSteps : run.steps;
  const labels: Record<string, string> = {
    parse_source: t("runStep.parse"),
    extract_evidence: t("runStep.extract"),
    verify_citations: t("runStep.verify"),
  };
  return steps.map((step) => ({
    id: step.id || `${run.id}-${step.name}`,
    label: labels[step.name] || step.name.replaceAll("_", " "),
    detail: stepDetail(step, t),
    status: eventStatus(step),
    time: eventTime(step, locale),
  }));
}

function runStatusLabel(status: RunSummary["status"] | undefined, t: Translator) {
  if (status === "succeeded") return t("runStatus.succeeded");
  if (status === "partially_succeeded") return t("runStatus.partiallySucceeded");
  if (status === "running") return t("runStatus.running");
  if (status === "queued") return t("runStatus.queued");
  if (status === "failed") return t("runStatus.failed");
  if (status === "cancelled") return t("runStatus.cancelled");
  return t("runStatus.none");
}

function LoadingShell({ t }: { t: Translator }) {
  return (
    <div className="loading-shell" role="status" aria-label={t("loading.aria")}>
      <div className="loading-brand"><span className="brand-mark"><Sparkles size={17} /></span> Discovery Lab</div>
      <div className="loading-card">
        <LoaderCircle className="spin" size={22} />
        <div>
          <strong>{t("loading.title")}</strong>
          <span>{t("loading.detail")}</span>
        </div>
      </div>
    </div>
  );
}

type EvidenceReviewPanelProps = {
  evidence: Evidence;
  live: boolean;
  currentRevision: boolean;
  t: Translator;
  onReview: (decision: ClaimReviewDecision, reviewer: string, rationale: string) => Promise<void>;
  onAuthor: (input: EvidenceRevisionAuthorInput) => Promise<void>;
};

const RESERVED_SYNTHETIC_TAGS = new Set([
  "synthetic-demo",
  "demo-extractor",
  "simulation-output",
]);

function editableHumanTags(tags: string[]) {
  return tags.filter((tag) => (
    !RESERVED_SYNTHETIC_TAGS.has(tag.trim().toLocaleLowerCase().replaceAll("_", "-"))
  ));
}

function EvidenceReviewPanel({
  evidence,
  live,
  currentRevision,
  t,
  onReview,
  onAuthor,
}: EvidenceReviewPanelProps) {
  const [reviewer, setReviewer] = useState("");
  const [reviewRationale, setReviewRationale] = useState("");
  const [authorOpen, setAuthorOpen] = useState(evidence.syntheticDemo);
  const [editor, setEditor] = useState("");
  const [editRationale, setEditRationale] = useState("");
  const [observation, setObservation] = useState(evidence.observation);
  const [interpretation, setInterpretation] = useState(evidence.interpretation);
  const [inference, setInference] = useState(evidence.inference ?? "");
  const [confidence, setConfidence] = useState(String(Math.round(evidence.confidence * 100)));
  const [tags, setTags] = useState(editableHumanTags(evidence.tags).join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const exactRevisionId = evidence.revisionId ?? "";
  const reviewReady = live && Boolean(exactRevisionId && reviewer.trim() && reviewRationale.trim()) && !busy;
  const authorReady = live && currentRevision && Boolean(
    exactRevisionId
    && editor.trim()
    && editRationale.trim()
    && observation.trim()
    && confidence.trim(),
  ) && !busy;

  async function submitReview(decision: ClaimReviewDecision) {
    if (!reviewReady || (decision === "ACCEPT" && evidence.syntheticDemo)) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await onReview(decision, reviewer.trim(), reviewRationale.trim());
      setNotice(t("evidenceReview.reviewSaved"));
    } catch (reviewError) {
      setError(safeMessage(reviewError, t));
    } finally {
      setBusy(false);
    }
  }

  async function submitAuthor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!authorReady) return;
    const confidenceValue = Number(confidence);
    if (!Number.isFinite(confidenceValue) || confidenceValue < 0 || confidenceValue > 100) {
      setError(t("evidenceReview.confidenceInvalid"));
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await onAuthor({
        baseRevisionId: exactRevisionId,
        observation: observation.trim(),
        interpretation: interpretation.trim() || null,
        inference: inference.trim() || null,
        confidence: confidenceValue / 100,
        tags: tags.split(/[,;\n]/).map((tag) => tag.trim()).filter(Boolean),
        editor: editor.trim(),
        rationale: editRationale.trim(),
        clientRequestId: requestId(),
      });
      setNotice(t("evidenceReview.revisionSaved"));
    } catch (authorError) {
      setError(safeMessage(authorError, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="evidence-review-card" aria-labelledby="evidence-review-title">
      <div className="evidence-review-heading">
        <div>
          <span>{t("evidenceReview.eyebrow")}</span>
          <h2 id="evidence-review-title">{t("evidenceReview.title")}</h2>
        </div>
        <span className="revision-lock"><LockKeyhole size={12} />{t("evidenceReview.exactRevision", { revision: exactRevisionId || t("general.unavailable") })}</span>
      </div>

      {evidence.syntheticDemo && (
        <div className="evidence-review-warning" role="note">
          <AlertTriangle size={16} />
          <div><strong>{t("evidenceReview.syntheticBlocked")}</strong><span>{t("evidenceReview.syntheticHelp")}</span></div>
        </div>
      )}
      {evidence.humanAuthored && (
        <div className="evidence-review-lineage"><PencilLine size={13} />{t("evidenceReview.humanAuthored")}</div>
      )}

      <div className="evidence-review-fields">
        <label>{t("evidenceReview.reviewer")}<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} disabled={!live || busy} /></label>
        <label>{t("evidenceReview.rationale")}<textarea value={reviewRationale} onChange={(event) => setReviewRationale(event.target.value)} rows={2} disabled={!live || busy} /></label>
      </div>
      <div className="evidence-review-actions">
        <button type="button" className="primary-button" onClick={() => void submitReview("ACCEPT")} disabled={!reviewReady || evidence.syntheticDemo}>
          {busy && <LoaderCircle className="spin" size={13} />}{t("evidenceReview.accept")}
        </button>
        <button type="button" className="secondary-button" onClick={() => void submitReview("REQUEST_CHANGES")} disabled={!reviewReady}>{t("evidenceReview.requestChanges")}</button>
        <button type="button" className="danger-button" onClick={() => void submitReview("REJECT")} disabled={!reviewReady}>{t("evidenceReview.reject")}</button>
      </div>

      {!authorOpen ? (
        <button type="button" className="evidence-author-toggle" onClick={() => setAuthorOpen(true)} disabled={!live || !currentRevision || busy}>
          <PencilLine size={13} />{t("evidenceReview.authorTitle")}
        </button>
      ) : (
        <form className="evidence-author-form" onSubmit={(event) => void submitAuthor(event)}>
          <div className="evidence-author-head"><div><span>{t("evidenceReview.authorEyebrow")}</span><h3>{t("evidenceReview.authorTitle")}</h3></div>{!evidence.syntheticDemo && <button type="button" className="text-button" onClick={() => setAuthorOpen(false)}>{t("general.close")}</button>}</div>
          <p>{t("evidenceReview.authorBody")}</p>
          {!currentRevision && <div className="evidence-review-warning compact"><AlertTriangle size={14} /><span>{t("evidenceReview.historicalBlocked")}</span></div>}
          <div className="locked-quote" role="note" aria-label={t("evidenceReview.quoteLocked")}>
            <div><LockKeyhole size={12} /><strong>{t("evidenceReview.quoteLocked")}</strong></div>
            <blockquote>“{evidence.quote}”</blockquote>
          </div>
          <div className="evidence-author-grid">
            <label>{t("evidenceReview.observation")}<textarea value={observation} onChange={(event) => setObservation(event.target.value)} rows={3} required disabled={!currentRevision || busy} /></label>
            <label>{t("evidenceReview.interpretation")}<textarea value={interpretation} onChange={(event) => setInterpretation(event.target.value)} rows={3} disabled={!currentRevision || busy} /></label>
            <label>{t("evidenceReview.inference")}<textarea value={inference} onChange={(event) => setInference(event.target.value)} rows={3} disabled={!currentRevision || busy} /></label>
            <label>{t("evidenceReview.tags")}<input value={tags} onChange={(event) => setTags(event.target.value)} disabled={!currentRevision || busy} /></label>
            <label>{t("evidenceReview.confidence")}<input type="number" min="0" max="100" step="1" value={confidence} onChange={(event) => setConfidence(event.target.value)} required disabled={!currentRevision || busy} /></label>
            <label>{t("evidenceReview.editor")}<input value={editor} onChange={(event) => setEditor(event.target.value)} required disabled={!currentRevision || busy} /></label>
            <label className="evidence-author-rationale">{t("evidenceReview.editRationale")}<textarea value={editRationale} onChange={(event) => setEditRationale(event.target.value)} rows={2} required disabled={!currentRevision || busy} /></label>
          </div>
          <button className="primary-button evidence-author-submit" disabled={!authorReady}>
            {busy ? <LoaderCircle className="spin" size={13} /> : <Save size={13} />}{t("evidenceReview.createRevision")}
          </button>
        </form>
      )}

      {error && <div className="form-error" role="alert">{error}</div>}
      {notice && <div className="evidence-review-success" role="status"><CheckCircle2 size={13} />{notice}</div>}
    </section>
  );
}

function preferredInitialStudyId(items: Study[]): string {
  const preferred = items.reduce<Study | null>((best, candidate) => {
    if (!best) return candidate;
    if (candidate.evidenceCount !== best.evidenceCount) {
      return candidate.evidenceCount > best.evidenceCount ? candidate : best;
    }
    if (candidate.sourceCount !== best.sourceCount) {
      return candidate.sourceCount > best.sourceCount ? candidate : best;
    }
    return best;
  }, null);
  return preferred?.id ?? "";
}

export function DiscoveryWorkbench() {
  const [locale, setLocale] = useState<Locale>(DEFAULT_LOCALE);
  const [activeView, setActiveView] = useState<WorkbenchView>("overview");
  const [mode, setMode] = useState<ConnectionMode>("loading");
  const [connectionError, setConnectionError] = useState("");
  const [studies, setStudies] = useState<Study[]>([]);
  const [selectedStudyId, setSelectedStudyId] = useState("");
  const [liveSources, setLiveSources] = useState<SourceItem[]>([]);
  const [sourceTotal, setSourceTotal] = useState(0);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState("");
  const [liveEvidence, setLiveEvidence] = useState<Evidence[]>([]);
  const [pinnedEvidenceSnapshot, setPinnedEvidenceSnapshot] = useState<Evidence | null>(null);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState("");
  const [evidenceDetailTab, setEvidenceDetailTab] = useState<EvidenceDetailTab>("summary");
  const [liveContext, setLiveContext] = useState<EvidenceContext | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [contextLoading, setContextLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState("");
  const [contextError, setContextError] = useState("");
  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<Evidence["kind"] | "all">("all");
  const [dragActive, setDragActive] = useState(false);
  const [uploadNotice, setUploadNotice] = useState("");
  const [showNewStudy, setShowNewStudy] = useState(false);
  const [newStudyTitle, setNewStudyTitle] = useState("");
  const [newStudyQuestion, setNewStudyQuestion] = useState("");
  const [creatingStudy, setCreatingStudy] = useState(false);
  const [createError, setCreateError] = useState("");
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);
  const [liveRuns, setLiveRuns] = useState<RunSummary[]>([]);
  const [runTotal, setRunTotal] = useState(0);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runsError, setRunsError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const evidenceRequestRef = useRef(0);
  const contextRequestRef = useRef(0);
  const studyDataRequestRef = useRef(0);
  const localeReadyRef = useRef(false);
  const localeRef = useRef<Locale>(DEFAULT_LOCALE);
  const t = useCallback<Translator>((key, vars) => translate(locale, key, vars), [locale]);
  const describeError = useCallback((error: unknown) => safeMessage(
    error,
    (key, vars) => translate(localeRef.current, key, vars),
  ), []);

  useEffect(() => {
    localeRef.current = locale;
  }, [locale]);

  useEffect(() => {
    const saved = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    const initialLocale = getInitialLocale(saved, window.navigator.language);
    const timer = window.setTimeout(() => {
      localeReadyRef.current = true;
      setLocale(initialLocale);
      document.documentElement.lang = initialLocale;
      window.localStorage.setItem(LOCALE_STORAGE_KEY, serializeLocaleForStorage(initialLocale));
      document.cookie = serializeLocaleCookie(initialLocale);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!localeReadyRef.current) return;
    document.documentElement.lang = locale;
    window.localStorage.setItem(LOCALE_STORAGE_KEY, serializeLocaleForStorage(locale));
    document.cookie = serializeLocaleCookie(locale);
  }, [locale]);

  useEffect(() => {
    const syncViewFromHash = () => {
      if (window.location.hash === "#evidence") setActiveView("evidence");
      else if (window.location.hash === "#claims") setActiveView("claims");
      else if (window.location.hash === "#runs") setActiveView("runs");
      else if (window.location.hash === "#eval") setActiveView("eval");
      else if (window.location.hash === "#product") setActiveView("product");
      else setActiveView("overview");
    };
    syncViewFromHash();
    window.addEventListener("hashchange", syncViewFromHash);
    return () => window.removeEventListener("hashchange", syncViewFromHash);
  }, []);

  const loadContext = useCallback(async (item: Evidence) => {
    const requestId = ++contextRequestRef.current;
    setContextLoading(true);
    setContextError("");
    setLiveContext(null);
    try {
      const value = await api.getEvidenceContext(item.id, item.revisionId);
      const evidenceRevisionMismatch = item.revisionId
        && value.evidenceRevisionId !== item.revisionId;
      const sourceRevisionMismatch = item.sourceRevisionId
        && value.sourceRevisionId !== item.sourceRevisionId;
      if (evidenceRevisionMismatch || sourceRevisionMismatch) {
        throw new ApiError(translate(localeRef.current, "context.revisionMismatch"));
      }
      if (contextRequestRef.current === requestId) setLiveContext(value);
    } catch (error) {
      if (contextRequestRef.current === requestId) setContextError(describeError(error));
    } finally {
      if (contextRequestRef.current === requestId) setContextLoading(false);
    }
  }, [describeError]);

  const loadLiveEvidence = useCallback(async (studyId: string) => {
    const requestId = ++evidenceRequestRef.current;
    setEvidenceLoading(true);
    setEvidenceError("");
    try {
      const items = await api.getEvidence(studyId);
      if (evidenceRequestRef.current !== requestId) return;
      const firstItem = items[0] ?? null;
      setLiveEvidence(items);
      setPinnedEvidenceSnapshot(null);
      setSelectedEvidenceId(firstItem?.id ?? "");
      if (firstItem) {
        void loadContext(firstItem);
      } else {
        contextRequestRef.current += 1;
        setLiveContext(null);
        setContextLoading(false);
      }
    } catch (error) {
      if (evidenceRequestRef.current !== requestId) return;
      setLiveEvidence([]);
      setPinnedEvidenceSnapshot(null);
      setSelectedEvidenceId("");
      setLiveContext(null);
      setEvidenceError(describeError(error));
    } finally {
      if (evidenceRequestRef.current === requestId) setEvidenceLoading(false);
    }
  }, [describeError, loadContext]);

  const loadLiveStudyData = useCallback(async (studyId: string) => {
    const requestId = ++studyDataRequestRef.current;
    setSourcesLoading(true);
    setRunsLoading(true);
    setSourcesError("");
    setRunsError("");
    const [sourcesResult, runsResult] = await Promise.allSettled([
      api.getSources(studyId),
      api.getRuns(studyId, 100),
    ]);
    if (studyDataRequestRef.current !== requestId) return;

    if (sourcesResult.status === "fulfilled") {
      setLiveSources(sourcesResult.value.items);
      setSourceTotal(sourcesResult.value.total);
    } else {
      setLiveSources([]);
      setSourceTotal(0);
      setSourcesError(describeError(sourcesResult.reason));
    }

    if (runsResult.status === "fulfilled") {
      setLiveRuns(runsResult.value.items);
      setRunTotal(runsResult.value.total);
    } else {
      setLiveRuns([]);
      setRunTotal(0);
      setRunsError(describeError(runsResult.reason));
    }
    setSourcesLoading(false);
    setRunsLoading(false);
  }, [describeError]);

  const connect = useCallback(async () => {
    setMode("loading");
    setConnectionError("");
    try {
      const items = await api.getStudies();
      const nextStudyId = preferredInitialStudyId(items);
      setStudies(items);
      setSelectedStudyId(nextStudyId);
      setPinnedEvidenceSnapshot(null);
      setMode("live");
      setAgentEvents([]);
      setLiveRuns([]);
      setRunTotal(0);
      setLiveSources([]);
      setSourceTotal(0);
      if (nextStudyId) {
        void loadLiveEvidence(nextStudyId);
        void loadLiveStudyData(nextStudyId);
      }
    } catch (error) {
      evidenceRequestRef.current += 1;
      contextRequestRef.current += 1;
      setConnectionError(describeError(error));
      setStudies(demoStudies);
      setSelectedStudyId("demo-helphub");
      setSelectedEvidenceId("");
      setPinnedEvidenceSnapshot(null);
      setMode("demo");
      setLiveRuns([]);
      setRunTotal(1);
      setAgentEvents(demoAgentEvents.map((item) => ({ ...item })));
    }
  }, [describeError, loadLiveEvidence, loadLiveStudyData]);

  useEffect(() => {
    let cancelled = false;
    void api.getStudies().then((items) => {
      if (cancelled) return;
      const nextStudyId = preferredInitialStudyId(items);
      setStudies(items);
      setSelectedStudyId(nextStudyId);
      setPinnedEvidenceSnapshot(null);
      setMode("live");
      setAgentEvents([]);
      setLiveRuns([]);
      setRunTotal(0);
      setLiveSources([]);
      setSourceTotal(0);
      if (nextStudyId) {
        void loadLiveEvidence(nextStudyId);
        void loadLiveStudyData(nextStudyId);
      }
    }).catch((error: unknown) => {
      if (cancelled) return;
      setConnectionError(describeError(error));
      setStudies(demoStudies);
      setSelectedStudyId("demo-helphub");
      setPinnedEvidenceSnapshot(null);
      setMode("demo");
      setLiveRuns([]);
      setRunTotal(1);
      setAgentEvents(demoAgentEvents.map((item) => ({ ...item })));
    });
    return () => {
      cancelled = true;
      evidenceRequestRef.current += 1;
      contextRequestRef.current += 1;
      studyDataRequestRef.current += 1;
    };
  }, [describeError, loadLiveEvidence, loadLiveStudyData]);

  const selectedStudy = useMemo(
    () => studies.find((study) => study.id === selectedStudyId) ?? null,
    [selectedStudyId, studies],
  );

  const evidence = useMemo(
    () => mode === "demo" ? demoEvidence.filter((item) => item.studyId === selectedStudyId) : liveEvidence,
    [liveEvidence, mode, selectedStudyId],
  );
  const sources = mode === "demo" ? demoSources[selectedStudyId] ?? [] : liveSources;
  const visibleSourceTotal = mode === "demo" ? sources.length : sourceTotal;
  const activeEvidenceId = evidence.some((item) => item.id === selectedEvidenceId)
    ? selectedEvidenceId
    : evidence[0]?.id ?? "";

  const selectedEvidence = useMemo(
    () => pinnedEvidenceSnapshot?.id === activeEvidenceId
      ? pinnedEvidenceSnapshot
      : evidence.find((item) => item.id === activeEvidenceId) ?? null,
    [activeEvidenceId, evidence, pinnedEvidenceSnapshot],
  );
  const kindLabels = useMemo<Record<Evidence["kind"], string>>(() => ({
    pain: t(kindMessageKeys.pain),
    need: t(kindMessageKeys.need),
    behavior: t(kindMessageKeys.behavior),
    constraint: t(kindMessageKeys.constraint),
    counterevidence: t(kindMessageKeys.counterevidence),
    signal: t(kindMessageKeys.signal),
  }), [t]);
  const reviewLabels = useMemo<Record<Evidence["reviewStatus"], string>>(() => ({
    approved: t(reviewMessageKeys.approved),
    reviewed: t(reviewMessageKeys.reviewed),
    pending: t(reviewMessageKeys.pending),
    rejected: t(reviewMessageKeys.rejected),
    stale: t(reviewMessageKeys.stale),
  }), [t]);
  const relationshipLabels = useMemo<Record<Evidence["relationship"], string>>(() => ({
    supports: t(relationshipMessageKeys.supports),
    challenges: t(relationshipMessageKeys.challenges),
    neutral: t(relationshipMessageKeys.neutral),
  }), [t]);
  const evidenceRun = useMemo(() => {
    if (mode !== "live" || !selectedEvidence) return null;
    if (selectedEvidence.runId) {
      const exactRun = liveRuns.find((run) => run.id === selectedEvidence.runId);
      if (exactRun) return exactRun;
    }
    if (selectedEvidence.runStepId) {
      const stepRun = liveRuns.find((run) => (
        run.steps.some((step) => step.id === selectedEvidence.runStepId)
      ));
      if (stepRun) return stepRun;
    }
    return [...liveRuns]
      .filter((run) => run.sourceId === selectedEvidence.sourceId)
      .sort((left, right) => (
        new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime()
      ))[0] ?? null;
  }, [liveRuns, mode, selectedEvidence]);
  const displayedAgentEvents = mode === "demo"
    ? agentEvents
    : evidenceRun ? agentEventsFromRun(evidenceRun, t, locale) : [];
  const context = mode === "demo" && selectedEvidence ? demoContexts[selectedEvidence.id] ?? null : liveContext;
  const selectedIsCurrentEvidenceRevision = mode === "live" && Boolean(
    selectedEvidence?.revisionId
    && liveEvidence.find((item) => item.id === selectedEvidence.id)?.revisionId === selectedEvidence.revisionId,
  );
  const visibleEvidenceLoading = mode === "live" && evidenceLoading;
  const visibleEvidenceError = mode === "live" ? evidenceError : "";
  const visibleContextLoading = mode === "live" && contextLoading;
  const visibleContextError = mode === "live" ? contextError : "";
  const visibleSourcesLoading = mode === "live" && sourcesLoading;
  const visibleSourcesError = mode === "live" ? sourcesError : "";
  const currentRunStatus = mode === "demo"
    ? displayedAgentEvents.some((event) => event.status === "running") ? "running" : undefined
    : evidenceRun?.status;

  function selectStudy(studyId: string) {
    setSelectedStudyId(studyId);
    setSelectedEvidenceId("");
    setPinnedEvidenceSnapshot(null);
    setUploadNotice("");
    if (mode !== "live") {
      setAgentEvents(studyId === "demo-helphub" ? demoAgentEvents.map((item) => ({ ...item })) : []);
      return;
    }
    contextRequestRef.current += 1;
    studyDataRequestRef.current += 1;
    setLiveSources([]);
    setSourceTotal(0);
    setSourcesError("");
    setLiveEvidence([]);
    setLiveContext(null);
    setContextLoading(false);
    setLiveRuns([]);
    setRunTotal(0);
    setRunsError("");
    setAgentEvents([]);
    void loadLiveEvidence(studyId);
    void loadLiveStudyData(studyId);
  }

  function selectEvidence(item: Evidence) {
    setPinnedEvidenceSnapshot(null);
    setSelectedEvidenceId(item.id);
    setEvidenceDetailTab("summary");
    if (mode === "live") void loadContext(item);
  }

  function navigateView(view: WorkbenchView) {
    setActiveView(view);
    const hash = `#${view}`;
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${hash}`);
    window.requestAnimationFrame(() => {
      document.getElementById("main-content")?.focus({ preventScroll: true });
    });
  }

  function openEvidenceFromClaim(item: Evidence) {
    navigateView("evidence");
    selectEvidence(item);
    window.requestAnimationFrame(() => {
      document.querySelector<HTMLElement>(`[data-evidence-id="${CSS.escape(item.id)}"]`)?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    });
  }

  async function openEvidenceRevisionFromClaim(
    evidenceId: string,
    evidenceRevisionId: string,
    expectedSourceRevisionId?: string,
  ) {
    navigateView("evidence");
    if (mode !== "live") {
      const previewItem = evidence.find((item) => item.id === evidenceId && item.revisionId === evidenceRevisionId);
      if (previewItem) openEvidenceFromClaim(previewItem);
      return;
    }
    const requestId = ++contextRequestRef.current;
    setContextLoading(true);
    setContextError("");
    setLiveContext(null);
    try {
      const value = await api.getEvidenceContext(evidenceId, evidenceRevisionId);
      const snapshot = value.evidenceSnapshot;
      if (
        value.evidenceId !== evidenceId
        || value.evidenceRevisionId !== evidenceRevisionId
        || !snapshot
        || snapshot.id !== evidenceId
        || snapshot.revisionId !== evidenceRevisionId
        || snapshot.studyId !== selectedStudyId
        || snapshot.sourceRevisionId !== value.sourceRevisionId
        || (expectedSourceRevisionId && snapshot.sourceRevisionId !== expectedSourceRevisionId)
      ) {
        throw new ApiError(translate(localeRef.current, "context.revisionMismatch"));
      }
      if (contextRequestRef.current !== requestId) return;
      setPinnedEvidenceSnapshot(snapshot);
      setSelectedEvidenceId(snapshot.id);
      setEvidenceDetailTab("summary");
      setLiveContext(value);
      window.requestAnimationFrame(() => {
        document.querySelector<HTMLElement>(`[data-evidence-id="${CSS.escape(snapshot.id)}"]`)?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      });
    } catch (error) {
      if (contextRequestRef.current === requestId) setContextError(describeError(error));
    } finally {
      if (contextRequestRef.current === requestId) setContextLoading(false);
    }
  }

  async function reviewEvidenceRevision(
    item: Evidence,
    decision: ClaimReviewDecision,
    reviewer: string,
    rationale: string,
  ) {
    if (mode !== "live" || !item.revisionId) {
      throw new ApiError(t("evidenceReview.liveOnly"));
    }
    if (decision === "ACCEPT" && item.syntheticDemo) {
      throw new ApiError(t("evidenceReview.syntheticBlocked"), 409, "synthetic_evidence_accept_forbidden");
    }
    const requestedRevisionId = item.revisionId;
    const request = ++contextRequestRef.current;
    setContextLoading(true);
    setContextError("");
    try {
      await api.reviewEvidence(item.id, requestedRevisionId, {
        decision,
        reviewer,
        rationale,
        clientRequestId: requestId(),
      });
      if (contextRequestRef.current !== request) return;
      const value = await api.getEvidenceContext(item.id, requestedRevisionId);
      const snapshot = exactEvidenceSnapshot(value, item, requestedRevisionId, t);
      if (contextRequestRef.current !== request) return;

      const currentRevisionId = liveEvidence.find((candidate) => candidate.id === item.id)?.revisionId;
      if (currentRevisionId === requestedRevisionId) {
        setLiveEvidence((current) => current.map((candidate) => (
          candidate.id === snapshot.id && candidate.revisionId === requestedRevisionId ? snapshot : candidate
        )));
        setPinnedEvidenceSnapshot(null);
      } else {
        setPinnedEvidenceSnapshot(snapshot);
      }
      setSelectedEvidenceId(snapshot.id);
      setLiveContext(value);
    } catch (error) {
      if (contextRequestRef.current === request) setContextError(describeError(error));
      throw error;
    } finally {
      if (contextRequestRef.current === request) setContextLoading(false);
    }
  }

  async function authorEvidenceRevision(item: Evidence, input: EvidenceRevisionAuthorInput) {
    const currentRevisionId = liveEvidence.find((candidate) => candidate.id === item.id)?.revisionId;
    if (
      mode !== "live"
      || !item.revisionId
      || input.baseRevisionId !== item.revisionId
      || currentRevisionId !== item.revisionId
    ) {
      throw new ApiError(t("evidenceReview.historicalBlocked"), 409, "evidence_revision_conflict");
    }
    const request = ++contextRequestRef.current;
    setContextLoading(true);
    setContextError("");
    try {
      const authored = await api.authorEvidenceRevision(item.id, input);
      if (contextRequestRef.current !== request) return;
      const value = await api.getEvidenceContext(item.id, authored.evidenceRevisionId);
      const snapshot = exactEvidenceSnapshot(value, item, authored.evidenceRevisionId, t);
      if (snapshot.quote !== item.quote) {
        throw new ApiError(t("evidenceReview.quoteChanged"), 409, "immutable_quote_changed");
      }
      if (contextRequestRef.current !== request) return;

      setLiveEvidence((current) => current.map((candidate) => (
        candidate.id === snapshot.id ? snapshot : candidate
      )));
      setPinnedEvidenceSnapshot(null);
      setSelectedEvidenceId(snapshot.id);
      setLiveContext(value);
    } catch (error) {
      if (contextRequestRef.current === request) setContextError(describeError(error));
      throw error;
    } finally {
      if (contextRequestRef.current === request) setContextLoading(false);
    }
  }

  const filteredEvidence = useMemo(() => {
    const query = search.trim().toLocaleLowerCase(locale);
    return evidence.filter((item) => {
      if (kindFilter !== "all" && item.kind !== kindFilter) return false;
      if (!query) return true;
      return [item.title, item.quote, item.observation, item.sourceName, ...item.tags]
        .join(" ")
        .toLocaleLowerCase(locale)
        .includes(query);
    });
  }, [evidence, kindFilter, locale, search]);

  async function createStudy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mode !== "live" || !newStudyTitle.trim() || !newStudyQuestion.trim()) return;
    setCreatingStudy(true);
    setCreateError("");
    try {
      const created = await api.createStudy({
        title: newStudyTitle.trim(),
        decisionQuestion: newStudyQuestion.trim(),
      });
      setStudies((current) => [created, ...current]);
      selectStudy(created.id);
      setShowNewStudy(false);
      setNewStudyTitle("");
      setNewStudyQuestion("");
    } catch (error) {
      setCreateError(describeError(error));
    } finally {
      setCreatingStudy(false);
    }
  }

  async function handleFile(file?: File) {
    setDragActive(false);
    if (!file || !selectedStudy) return;
    if (mode !== "live") {
      setUploadNotice(t("upload.demo"));
      return;
    }
    if (file.size > 25 * 1024 * 1024) {
      setUploadNotice(t("upload.tooLarge"));
      return;
    }

    const temporaryId = `upload-${Date.now()}`;
    const temporarySource: SourceItem = {
      id: temporaryId,
      name: file.name,
      type: file.type || file.name.split(".").pop() || "file",
      status: "uploading",
      progress: 20,
      updatedAt: new Date().toISOString(),
    };
    setLiveSources((current) => [temporarySource, ...current]);
    setUploadNotice(t("upload.uploading", { name: file.name }));
    try {
      const uploaded = await api.uploadSource(selectedStudy.id, file);
      if (!uploaded.id) throw new ApiError(t("upload.missingId"));
      setLiveSources((current) =>
        current.map((item) =>
          item.id === temporaryId ? { ...uploaded, status: "processing", progress: 55 } : item,
        ),
      );
      const run = await api.processSource(uploaded.id);
      setLiveRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      setRunTotal((current) => Math.max(1, current));
      setLiveSources((current) =>
        current.map((item) => (
          item.id === uploaded.id
            ? { ...item, status: run.status === "succeeded" ? "ready" : "processing", progress: run.status === "succeeded" ? 100 : 72 }
            : item
        )),
      );
      setUploadNotice(
        run.status === "succeeded"
          ? t("upload.complete")
          : t("upload.started"),
      );
      void loadLiveEvidence(selectedStudy.id);
      void loadLiveStudyData(selectedStudy.id);
    } catch (error) {
      setLiveSources((current) =>
        current.map((item) =>
          item.id === temporaryId || item.name === file.name ? { ...item, status: "failed", progress: 0 } : item,
        ),
      );
      setUploadNotice(t("upload.failed", { error: describeError(error) }));
      void loadLiveStudyData(selectedStudy.id);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  if (mode === "loading") return <LoadingShell t={t} />;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">{t("nav.skipToContent")}</a>
      <aside className="sidebar">
        <div className="brand-row">
          <span className="brand-mark"><Sparkles size={17} strokeWidth={2.2} /></span>
          <span className="brand-name">Discovery Lab</span>
          <button className="icon-button sidebar-more" aria-label={t("sidebar.menu")}><ChevronDown size={15} /></button>
        </div>

        <nav className="primary-nav" aria-label={t("nav.aria")}>
          <button
            type="button"
            className={`nav-item primary ${activeView === "overview" ? "active" : ""}`}
            aria-current={activeView === "overview" ? "page" : undefined}
            onClick={() => navigateView("overview")}
          ><LayoutDashboard size={16} />{t("nav.overview")}</button>
          <button
            type="button"
            className={`nav-item primary ${activeView === "evidence" ? "active" : ""}`}
            aria-current={activeView === "evidence" ? "page" : undefined}
            onClick={() => navigateView("evidence")}
          ><BookOpenCheck size={16} />{t("nav.evidence")}</button>
          <button
            type="button"
            className={`nav-item primary ${activeView === "claims" ? "active" : ""}`}
            aria-current={activeView === "claims" ? "page" : undefined}
            onClick={() => navigateView("claims")}
          ><GitBranch size={16} />{t("nav.claims")}</button>
          <button
            type="button"
            className={`nav-item secondary ${activeView === "runs" ? "active" : ""}`}
            aria-current={activeView === "runs" ? "page" : undefined}
            onClick={() => navigateView("runs")}
          >
            <Activity size={16} />{t("nav.runs")}
          </button>
          <button
            type="button"
            className={`nav-item secondary ${activeView === "eval" ? "active" : ""}`}
            aria-current={activeView === "eval" ? "page" : undefined}
            onClick={() => navigateView("eval")}
          >
            <FlaskConical size={16} />{t("nav.eval")}
          </button>
          <button
            type="button"
            className={`nav-item secondary ${activeView === "product" ? "active" : ""}`}
            aria-current={activeView === "product" ? "page" : undefined}
            onClick={() => navigateView("product")}
          >
            <Layers3 size={16} />{t("nav.product")}
          </button>
        </nav>

        <div className="studies-heading">
          <span>{t("sidebar.studies")}</span>
          <button
            className="icon-button"
            aria-label={t("sidebar.newStudy")}
            title={mode === "demo" ? t("sidebar.newStudyLiveOnly") : t("sidebar.newStudy")}
            disabled={mode === "demo"}
            onClick={() => setShowNewStudy(true)}
          ><Plus size={16} /></button>
        </div>
        <div className="study-list" aria-label={t("sidebar.studyList")}>
          {studies.map((study) => (
            <button
              className={`study-item ${study.id === selectedStudyId ? "selected" : ""}`}
              key={study.id}
              aria-pressed={study.id === selectedStudyId}
              onClick={() => selectStudy(study.id)}
            >
              <span className={`study-status ${study.status}`} aria-hidden="true" />
              <span className="study-copy">
                <strong>{study.title}</strong>
                <small>{t("sidebar.evidenceCount", { count: study.evidenceCount })} · {formatRelativeDate(study.updatedAt, t)}</small>
              </span>
            </button>
          ))}
          {studies.length === 0 && <p className="sidebar-empty">{t("sidebar.empty")}</p>}
        </div>

        <div className="sidebar-footer">
          <div className="workspace-avatar">MP</div>
          <div><strong>{t("sidebar.workspace")}</strong><small>{t("sidebar.environment")}</small></div>
          <MoreHorizontal size={16} />
        </div>
      </aside>

      <main className="workspace" id="main-content" tabIndex={-1}>
        <header className="workspace-header">
          <div>
            <div className="breadcrumb"><FolderKanban size={14} />{t("header.studies")} <span>/</span> {selectedStudy?.title ?? t("header.noStudy")}</div>
            <h1>{activeView === "overview" ? t("header.overview") : activeView === "claims" ? t("header.claims") : activeView === "runs" ? t("header.runs") : activeView === "eval" ? t("header.eval") : activeView === "product" ? t("header.product") : t("header.evidence")}</h1>
          </div>
          <div className="connection-cluster">
            <div className="locale-switcher" role="group" aria-label={t("language.label")}>
              <Languages size={15} aria-hidden="true" />
              <button type="button" aria-pressed={locale === "en"} onClick={() => setLocale("en")}>EN</button>
              <button type="button" aria-pressed={locale === "zh-CN"} onClick={() => setLocale("zh-CN")}>简中</button>
            </div>
            <span className={`connection-pill ${mode}`}>
              <span className="connection-dot" />
              {mode === "live" ? t("connection.live") : t("connection.demo")}
            </span>
            <button className="icon-button header-button" aria-label={t("connection.refresh")} onClick={() => void connect()}>
              <RefreshCw size={16} />
            </button>
          </div>
        </header>

        {mode === "demo" && (
          <div className="demo-banner" role="status">
            <div className="demo-banner-icon"><AlertCircle size={17} /></div>
            <div>
              <strong>{t("demo.title")}</strong>
              <span>{t("demo.body", { url: API_URL, error: connectionError || t("demo.apiUnavailable") })}</span>
            </div>
            <button className="text-button" onClick={() => void connect()}><RefreshCw size={14} />{t("demo.reconnect")}</button>
          </div>
        )}

        {activeView === "overview" ? (
          <OverviewCenter
            live={mode === "live"}
            study={selectedStudy}
            t={t}
            onNavigate={navigateView}
          />
        ) : activeView === "evidence" ? (
        <div className="workspace-grid">
          <section className="evidence-column" id="evidence" aria-label={t("evidence.region")}>
            {selectedStudy ? (
              <>
                <article className="decision-card">
                  <div className="eyebrow"><Gauge size={14} />{t("decision.eyebrow")}</div>
                  <h2>{selectedStudy.decisionQuestion}</h2>
                  <div className="decision-meta">
                    <span><FileCheck2 size={14} />{t("decision.sources", { count: selectedStudy.sourceCount })}</span>
                    <span><BookOpenCheck size={14} />{t("decision.evidence", { count: selectedStudy.evidenceCount })}</span>
                    <span className="decision-open">{t("decision.context")} <ArrowRight size={13} /></span>
                  </div>
                </article>

                <section className="sources-section" aria-labelledby="sources-title">
                  <div className="section-heading">
                    <div>
                      <h2 id="sources-title">{t("sources.title")}</h2>
                      <span>{visibleSourcesLoading ? t("sources.loading") : t("sources.inStudy", { count: visibleSourceTotal })}</span>
                    </div>
                    {mode === "live" ? (
                      <button className="icon-button" aria-label={t("sources.refresh")} onClick={() => void loadLiveStudyData(selectedStudy.id)}>
                        <RefreshCw size={15} />
                      </button>
                    ) : (
                      <button className="icon-button" aria-label={t("sources.more")}><MoreHorizontal size={17} /></button>
                    )}
                  </div>

                  <div
                    className={`dropzone ${dragActive ? "drag-active" : ""} ${mode === "demo" ? "preview-disabled" : ""}`}
                    onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
                    onDragOver={(event) => event.preventDefault()}
                    onDragLeave={(event) => { event.preventDefault(); setDragActive(false); }}
                    onDrop={(event) => { event.preventDefault(); void handleFile(event.dataTransfer.files[0]); }}
                  >
                    <input
                      ref={fileInputRef}
                      id="source-upload"
                      type="file"
                      accept=".pdf,.csv,.txt,.md,text/plain,text/markdown,text/csv,application/pdf"
                      disabled={mode === "demo"}
                      onChange={(event) => void handleFile(event.target.files?.[0])}
                    />
                    <div className="dropzone-icon"><UploadCloud size={19} /></div>
                    <div className="dropzone-copy">
                      <strong>{mode === "demo" ? t("sources.uploadDisabled") : t("sources.drop")}</strong>
                      <span>{t("sources.formats")}</span>
                    </div>
                    <label className="secondary-button" htmlFor="source-upload" aria-disabled={mode === "demo"}>{t("sources.choose")}</label>
                  </div>
                  {uploadNotice && <div className="upload-notice" role="status">{uploadNotice}</div>}

                  <div className="source-list">
                    {visibleSourcesLoading ? (
                      <div className="list-loading source-loading" role="status"><LoaderCircle className="spin" size={16} />{t("sources.loadingList")}</div>
                    ) : visibleSourcesError ? (
                      <div className="inline-error compact" role="alert">
                        <AlertCircle size={16} />
                        <div><strong>{t("sources.loadFailed")}</strong><span>{visibleSourcesError}</span></div>
                        <button className="text-button" onClick={() => void loadLiveStudyData(selectedStudy.id)}>{t("general.retry")}</button>
                      </div>
                    ) : sources.map((source) => {
                      const SourceIcon = fileIcon(source.type);
                      return (
                        <div className="source-row" key={source.id}>
                          <span className="source-icon"><SourceIcon size={17} /></span>
                          <div className="source-copy">
                            <strong>{source.name}</strong>
                            <span>{source.type}{source.revision ? ` · ${t("sources.revision", { revision: source.revision })}` : ""}</span>
                            {(source.status === "processing" || source.status === "uploading") && (
                              <span className="progress-track" aria-label={t("sources.progress", { progress: source.progress ?? 0 })}>
                                <span style={{ width: `${source.progress ?? 35}%` }} />
                              </span>
                            )}
                          </div>
                          <span className={`source-state ${source.status}`}>
                            {source.status === "ready" && <CheckCircle2 size={13} />}
                            {(source.status === "processing" || source.status === "uploading") && <LoaderCircle className="spin" size={13} />}
                            {source.status === "failed" && <AlertCircle size={13} />}
                            {source.status === "processing"
                              ? `${t("sourceStatus.processing")} ${source.progress ?? 0}%`
                              : t(`sourceStatus.${source.status}` as MessageKey)}
                          </span>
                        </div>
                      );
                    })}
                    {!visibleSourcesLoading && !visibleSourcesError && sources.length === 0 && (
                      <p className="section-empty">{t("sources.empty")}</p>
                    )}
                  </div>
                </section>

                <section className="evidence-section" aria-labelledby="evidence-list-title">
                  <div className="section-heading evidence-heading">
                    <div><h2 id="evidence-list-title">{t("evidence.title")}</h2><span>{t("evidence.count", { visible: filteredEvidence.length, total: evidence.length })}</span></div>
                    {mode === "live" && (
                      <button className="icon-button" aria-label={t("evidence.refresh")} onClick={() => void loadLiveEvidence(selectedStudy.id)}>
                        <RefreshCw size={15} />
                      </button>
                    )}
                  </div>
                  <div className="evidence-tools">
                    <label className="search-box">
                      <Search size={15} />
                      <span className="sr-only">{t("evidence.searchLabel")}</span>
                      <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("evidence.searchPlaceholder")} />
                      {search && <button onClick={() => setSearch("")} aria-label={t("evidence.clearSearch")}><X size={13} /></button>}
                    </label>
                    <label className="filter-select">
                      <Filter size={14} />
                      <span className="sr-only">{t("evidence.filterLabel")}</span>
                      <select value={kindFilter} onChange={(event) => setKindFilter(event.target.value as Evidence["kind"] | "all")}>
                        <option value="all">{t("evidence.allTypes")}</option>
                        {Object.entries(kindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </label>
                  </div>

                  <RetrievalLab
                    key={selectedStudy.id}
                    studyId={selectedStudy.id}
                    live={mode === "live"}
                    t={t}
                    onOpenEvidenceRevision={(evidenceId, revisionId, sourceRevisionId) => (
                      openEvidenceRevisionFromClaim(evidenceId, revisionId, sourceRevisionId)
                    )}
                  />

                  {visibleEvidenceLoading ? (
                    <div className="list-loading" role="status"><LoaderCircle className="spin" size={18} />{t("evidence.loading")}</div>
                  ) : visibleEvidenceError ? (
                    <div className="inline-error" role="alert">
                      <AlertCircle size={17} /><div><strong>{t("evidence.loadFailed")}</strong><span>{visibleEvidenceError}</span></div>
                      <button className="text-button" onClick={() => void loadLiveEvidence(selectedStudy.id)}>{t("general.retry")}</button>
                    </div>
                  ) : (
                    <div className="evidence-list">
                      {filteredEvidence.map((item) => (
                        <button
                          className={`evidence-card ${item.id === activeEvidenceId ? "selected" : ""}`}
                          key={item.id}
                          data-evidence-id={item.id}
                          aria-pressed={item.id === activeEvidenceId}
                          onClick={() => selectEvidence(item)}
                        >
                          <div className="evidence-card-top">
                            <span className={`kind-chip ${item.kind}`}>{kindLabels[item.kind]}</span>
                            <span className={`relationship ${item.relationship}`}>{item.relationship === "supports" ? "+" : item.relationship === "challenges" ? "−" : "·"} {relationshipLabels[item.relationship]}</span>
                            {item.syntheticDemo && <span className="synthetic-badge">{t("evidence.synthetic")}</span>}
                            <span className={`mini-review ${item.reviewStatus}`} title={reviewLabels[item.reviewStatus]}>
                              {item.reviewStatus === "approved" || item.reviewStatus === "reviewed" ? <Check size={12} /> : <Clock3 size={11} />}
                            </span>
                          </div>
                          <h3>{item.title}</h3>
                          <p>“{item.quote}”</p>
                          <div className="evidence-card-meta"><span>{item.sourceName}</span><span>{item.locatorLabel.split(" · ")[0]}</span></div>
                        </button>
                      ))}
                      {filteredEvidence.length === 0 && (
                        <div className="empty-evidence"><Search size={20} /><strong>{t("evidence.emptyTitle")}</strong><span>{t("evidence.emptyBody")}</span></div>
                      )}
                    </div>
                  )}
                </section>
              </>
            ) : (
              <div className="no-study">
                <FolderKanban size={25} />
                <h2>{t("study.emptyTitle")}</h2>
                <p>{t("study.emptyBody")}</p>
                <button className="primary-button" onClick={() => setShowNewStudy(true)}><Plus size={15} />{t("study.create")}</button>
              </div>
            )}
          </section>

          <aside className="detail-column" aria-label={t("detail.region")}>
            {selectedEvidence ? (
              <>
                <div className="detail-header">
                  <div><span>{t("detail.eyebrow")}</span><h2>{selectedEvidence.title}</h2></div>
                  <button className="icon-button" aria-label={t("detail.more")}><MoreHorizontal size={18} /></button>
                </div>

                <div className="detail-badges">
                  <span className={`review-badge ${selectedEvidence.reviewStatus}`}>
                    {selectedEvidence.reviewStatus === "approved" ? <ShieldCheck size={14} /> : <Clock3 size={14} />}
                    {reviewLabels[selectedEvidence.reviewStatus]}
                  </span>
                  <span className="confidence-badge"><Gauge size={14} />{t("detail.confidence", { value: Math.round(selectedEvidence.confidence * 100) })}</span>
                  <span className={`kind-chip ${selectedEvidence.kind}`}>{kindLabels[selectedEvidence.kind]}</span>
                  {selectedEvidence.syntheticDemo && <span className="synthetic-badge detail-synthetic">{t("detail.synthetic")}</span>}
                </div>

                <div className="detail-tabs" role="tablist" aria-label={t("detail.tabs")}>
                  {([
                    ["summary", "detail.tab.summary"],
                    ["review", "detail.tab.review"],
                    ["source", "detail.tab.source"],
                  ] as const).map(([tab, label]) => (
                    <button
                      key={tab}
                      type="button"
                      role="tab"
                      aria-selected={evidenceDetailTab === tab}
                      className={evidenceDetailTab === tab ? "active" : ""}
                      onClick={() => setEvidenceDetailTab(tab)}
                    >{t(label)}</button>
                  ))}
                </div>

                {visibleContextError && (
                  <div className="inline-error detail-context-error" role="alert">
                    <AlertCircle size={16} />
                    <div><strong>{t("context.failed")}</strong><span>{visibleContextError}</span></div>
                  </div>
                )}

                {evidenceDetailTab === "summary" && (
                  <div className="detail-tab-panel" role="tabpanel">
                <section className="detail-section quote-section">
                  <div className="detail-label"><span>{t("detail.quote")}</span><span className="truth-label">{t("detail.sourceFact")}</span></div>
                  <blockquote>“{selectedEvidence.quote || t("detail.quoteMissing")}”</blockquote>
                </section>

                <div className="reasoning-grid">
                  <section className="detail-section">
                    <div className="detail-label"><span>{t("detail.observation")}</span><span className="truth-label observation">{t("detail.normalized")}</span></div>
                    <p>{selectedEvidence.observation || t("detail.observationMissing")}</p>
                  </section>
                  <section className="detail-section interpretation-section">
                    <div className="detail-label"><span>{t("detail.interpretation")}</span><span className="truth-label inference">{t("detail.aiInference")}</span></div>
                    <p>{selectedEvidence.interpretation || t("detail.interpretationMissing")}</p>
                  </section>
                </div>

                <section className="provenance-card">
                  <div className="provenance-head"><div className="source-icon"><FileText size={16} /></div><div><span>{t("detail.sourceLocator")}</span><strong>{selectedEvidence.sourceName}</strong></div><Link2 size={15} /></div>
                  <dl>
                    <div><dt>{t("detail.type")}</dt><dd>{selectedEvidence.sourceType}</dd></div>
                    <div><dt>{t("detail.locator")}</dt><dd>{selectedEvidence.locatorLabel}</dd></div>
                    <div>
                      <dt>{t("detail.evidenceRevision")}</dt>
                      <dd className="mono">
                        {selectedEvidence.revisionId
                          ? `${selectedEvidence.revisionId}${selectedEvidence.revision ? ` · r${selectedEvidence.revision}` : ""}`
                          : selectedEvidence.revision ? `r${selectedEvidence.revision}` : t("general.unavailable")}
                      </dd>
                    </div>
                    <div><dt>{t("detail.sourceRevision")}</dt><dd className="mono">{selectedEvidence.sourceRevisionId || t("general.unavailable")}</dd></div>
                    <div><dt>{t("detail.run")}</dt><dd className="mono">{evidenceRun?.id || selectedEvidence.runId || t("general.unavailable")}</dd></div>
                    <div><dt>{t("detail.runStep")}</dt><dd className="mono">{selectedEvidence.runStepId || t("general.unavailable")}</dd></div>
                  </dl>
                </section>
                  </div>
                )}

                {evidenceDetailTab === "review" && (
                  <div className="detail-tab-panel" role="tabpanel">
                    {mode === "live" && selectedEvidence.revisionId ? (
                      <EvidenceReviewPanel
                        key={`${selectedEvidence.id}:${selectedEvidence.revisionId}`}
                        evidence={selectedEvidence}
                        live
                        currentRevision={selectedIsCurrentEvidenceRevision}
                        t={t}
                        onReview={(decision, reviewer, rationale) => reviewEvidenceRevision(
                          selectedEvidence,
                          decision,
                          reviewer,
                          rationale,
                        )}
                        onAuthor={(input) => authorEvidenceRevision(selectedEvidence, input)}
                      />
                    ) : (
                      <div className="detail-tab-placeholder"><ShieldCheck size={22} /><p>{t("detail.reviewPreview")}</p></div>
                    )}
                  </div>
                )}

                {evidenceDetailTab === "source" && (
                  <div className="detail-tab-panel" role="tabpanel">
                <section className="context-section">
                  <div className="section-heading">
                    <div><h2>{t("context.title")}</h2><span>{context?.locatorLabel || selectedEvidence.locatorLabel}</span></div>
                    {mode === "live" && <button className="text-button" onClick={() => void loadContext(selectedEvidence)}><RefreshCw size={13} />{t("context.reload")}</button>}
                  </div>
                  {visibleContextLoading ? (
                    <div className="context-loading" role="status"><LoaderCircle className="spin" size={17} />{t("context.locating")}</div>
                  ) : visibleContextError ? (
                    <p className="section-empty">{t("context.failed")}</p>
                  ) : context ? (
                    <>
                      <div className="source-context">
                        <p>{context.before}</p>
                        <mark>{context.highlight}</mark>
                        <p>{context.after}</p>
                      </div>
                      {context.integrity && (
                        <div className="integrity-card" aria-label={t("integrity.aria")}>
                          <div className="integrity-heading">
                            <div><ShieldCheck size={15} /><strong>{t("integrity.title")}</strong></div>
                            <span>{t("integrity.replay")}</span>
                          </div>
                          <div className="integrity-checks">
                            {[
                              [t("integrity.quote"), context.integrity.quoteMatchesSegment],
                              [t("integrity.segmentHash"), context.integrity.segmentHashMatches],
                              [t("integrity.evidenceHash"), context.integrity.evidenceHashMatches],
                            ].map(([label, passed]) => (
                              <span className={`integrity-check ${passed ? "passed" : "failed"}`} key={String(label)}>
                                {passed ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
                                {label}
                              </span>
                            ))}
                          </div>
                          <div className="integrity-hashes">
                            <span>{t("integrity.sourceHash")} <code title={context.sourceContentHash}>{shortHash(context.sourceContentHash, t)}</code></span>
                            <span>{t("integrity.segment")} <code title={context.segmentContentHash}>{shortHash(context.segmentContentHash, t)}</code></span>
                            <span>
                              {t("integrity.evidence")}
                              <code title={context.evidenceContentHash || selectedEvidence.contentHash}>
                                {shortHash(context.evidenceContentHash || selectedEvidence.contentHash, t)}
                              </code>
                            </span>
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    <p className="section-empty">{t("context.empty")}</p>
                  )}
                </section>

                <section className="agent-run" id="agent-run">
                  <div className="agent-run-heading">
                    <div>
                      <span>
                        {mode === "live" && evidenceRun
                          ? t("runs.evidenceRun", { source: selectedEvidence.sourceName })
                          : mode === "live" && runTotal > 0
                            ? t("runs.unlinked", { count: runTotal })
                            : t("runs.agent")}
                      </span>
                      <strong>
                        {evidenceRun ? `${evidenceRun.workflowName} · v${evidenceRun.workflowVersion}` : t("runs.pipeline")}
                      </strong>
                    </div>
                    <span className={`run-status ${currentRunStatus || "idle"}`}>
                      {currentRunStatus === "running" || currentRunStatus === "queued" ? (
                        <LoaderCircle className="spin" size={12} />
                      ) : currentRunStatus === "succeeded" ? (
                        <CheckCircle2 size={12} />
                      ) : currentRunStatus === "failed" || currentRunStatus === "cancelled" ? (
                        <AlertCircle size={12} />
                      ) : (
                        <CircleDashed size={12} />
                      )}
                      {mode === "demo" && currentRunStatus === undefined ? t("runs.demo") : runStatusLabel(currentRunStatus, t)}
                    </span>
                  </div>
                  {mode === "live" && runsLoading ? (
                    <div className="agent-empty"><LoaderCircle className="spin" size={17} /><span>{t("runs.loading")}</span></div>
                  ) : mode === "live" && runsError ? (
                    <div className="inline-error compact" role="alert">
                      <AlertCircle size={16} />
                      <div><strong>{t("runs.loadFailed")}</strong><span>{runsError}</span></div>
                      <button className="text-button" onClick={() => void loadLiveStudyData(selectedEvidence.studyId)}>{t("general.retry")}</button>
                    </div>
                  ) : displayedAgentEvents.length > 0 ? (
                    <ol className="run-timeline">
                      {displayedAgentEvents.map((event) => (
                        <li className={event.status} key={event.id}>
                          <span className="timeline-node">
                            {event.status === "complete" ? <Check size={11} /> : event.status === "running" ? <LoaderCircle className="spin" size={11} /> : event.status === "failed" ? <X size={11} /> : <span />}
                          </span>
                          <div><strong>{event.label}</strong><span>{event.detail}</span></div>
                          <time>{event.time}</time>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <div className="agent-empty">
                      <Activity size={17} />
                      <span>
                        {mode === "live" && runTotal > 0
                          ? t("runs.unlinkedBody")
                          : t("runs.emptyBody")}
                      </span>
                    </div>
                  )}
                </section>
                  </div>
                )}
              </>
            ) : (
              <div className="detail-empty"><BookOpenCheck size={25} /><h2>{t("detail.emptyTitle")}</h2><p>{t("detail.emptyBody")}</p></div>
            )}
          </aside>
        </div>
        ) : activeView === "claims" ? (
          <ClaimsOpportunitiesView
            evidence={evidence}
            study={selectedStudy}
            t={t}
            live={mode === "live"}
            onOpenEvidence={openEvidenceFromClaim}
            onOpenEvidenceRevision={(evidenceId, revisionId) => {
              void openEvidenceRevisionFromClaim(evidenceId, revisionId);
            }}
          />
        ) : activeView === "eval" ? (
          <EvaluationCenter live={mode === "live"} t={t} />
        ) : activeView === "product" ? (
          <ProductDecisionCenter live={mode === "live"} study={selectedStudy} t={t} />
        ) : (
          <AgentRunCenter live={mode === "live"} study={selectedStudy} t={t} />
        )}
      </main>

      {showNewStudy && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setShowNewStudy(false)}>
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="new-study-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-head"><div><span>{t("modal.eyebrow")}</span><h2 id="new-study-title">{t("modal.title")}</h2></div><button className="icon-button" aria-label={t("general.close")} onClick={() => setShowNewStudy(false)}><X size={17} /></button></div>
            <form onSubmit={(event) => void createStudy(event)}>
              <label>{t("modal.studyName")}<input autoFocus value={newStudyTitle} onChange={(event) => setNewStudyTitle(event.target.value)} placeholder={t("modal.studyPlaceholder")} required /></label>
              <label>{t("modal.question")}<textarea value={newStudyQuestion} onChange={(event) => setNewStudyQuestion(event.target.value)} placeholder={t("modal.questionPlaceholder")} rows={4} required /></label>
              {createError && <div className="form-error" role="alert">{createError}</div>}
              <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setShowNewStudy(false)}>{t("modal.cancel")}</button><button className="primary-button" disabled={creatingStudy}>{creatingStudy && <LoaderCircle className="spin" size={14} />}{t("modal.create")}</button></div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
