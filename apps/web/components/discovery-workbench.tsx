"use client";

import {
  Activity,
  AlertCircle,
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
  Link2,
  LoaderCircle,
  MoreHorizontal,
  Plus,
  RefreshCw,
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
  type Evidence,
  type EvidenceContext,
  type RunStep,
  type RunSummary,
  type SourceItem,
  type Study,
} from "@/lib/api";
import { demoAgentEvents, demoContexts, demoEvidence, demoSources, demoStudies } from "@/lib/demo-data";

type ConnectionMode = "loading" | "live" | "demo";
type AgentEvent = {
  id: string;
  label: string;
  detail: string;
  status: "complete" | "running" | "pending" | "failed";
  time: string;
};

const kindLabels: Record<Evidence["kind"], string> = {
  pain: "痛点",
  need: "需求",
  behavior: "行为",
  constraint: "约束",
  counterevidence: "反证",
  signal: "信号",
};

const reviewLabels: Record<Evidence["reviewStatus"], string> = {
  approved: "已批准",
  reviewed: "已复核",
  pending: "待复核",
  rejected: "已驳回",
  stale: "已过期",
};

const relationshipLabels: Record<Evidence["relationship"], string> = {
  supports: "支持当前方向",
  challenges: "挑战当前方向",
  neutral: "中性信号",
};

function formatRelativeDate(value: string) {
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) return "刚刚更新";
  const days = Math.floor((Date.now() - time) / 86_400_000);
  if (days <= 0) return "今天更新";
  if (days === 1) return "昨天更新";
  return `${days} 天前更新`;
}

function fileIcon(type: string) {
  const normalized = type.toLowerCase();
  if (normalized.includes("csv") || normalized.includes("sheet")) return FileSpreadsheet;
  if (normalized.includes("zip") || normalized.includes("archive") || normalized.includes("snapshot")) return FileArchive;
  return FileText;
}

function safeMessage(error: unknown) {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : "发生未知错误";
}

function shortHash(value?: string) {
  if (!value) return "Unavailable";
  if (value.length <= 24) return value;
  return `${value.slice(0, 12)}…${value.slice(-8)}`;
}

function valueRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
}

function summaryNumber(summary: Record<string, unknown>, key: string) {
  const value = summary[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function stepDetail(step: RunStep) {
  const summary = step.outputSummary;
  if (step.name === "parse_source") {
    const count = summaryNumber(summary, "segment_count");
    const kinds = Array.isArray(summary.source_kinds)
      ? summary.source_kinds.filter((item): item is string => typeof item === "string").join(", ")
      : "";
    return [count === undefined ? "Source parsed" : `${count} segments`, kinds].filter(Boolean).join(" · ");
  }
  if (step.name === "extract_evidence") {
    const count = summaryNumber(summary, "evidence_candidate_count");
    const extractor = valueRecord(summary.extractor);
    const extractorName = typeof extractor.name === "string" ? extractor.name : "";
    const synthetic = summary.synthetic_demo === true ? "synthetic demo" : "";
    return [count === undefined ? "Evidence extracted" : `${count} candidates`, extractorName, synthetic]
      .filter(Boolean)
      .join(" · ");
  }
  if (step.name === "verify_citations") {
    const checked = summaryNumber(summary, "checked_count");
    const verified = summaryNumber(summary, "verified_count");
    if (checked !== undefined && verified !== undefined) return `${verified}/${checked} citations verified`;
    return "Citation integrity checked";
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

function eventTime(step: RunStep) {
  const raw = step.completedAt || step.startedAt || step.createdAt;
  const date = new Date(raw);
  return Number.isFinite(date.getTime())
    ? date.toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "—";
}

function agentEventsFromRun(run: RunSummary): AgentEvent[] {
  const stepNames = ["parse_source", "extract_evidence", "verify_citations"];
  const namedSteps = stepNames.flatMap((name) => run.steps.filter((step) => step.name === name));
  const steps = namedSteps.length > 0 ? namedSteps : run.steps;
  const labels: Record<string, string> = {
    parse_source: "Parse source",
    extract_evidence: "Extract evidence",
    verify_citations: "Verify citations",
  };
  return steps.map((step) => ({
    id: step.id || `${run.id}-${step.name}`,
    label: labels[step.name] || step.name.replaceAll("_", " "),
    detail: stepDetail(step),
    status: eventStatus(step),
    time: eventTime(step),
  }));
}

function runStatusLabel(status?: RunSummary["status"]) {
  if (status === "succeeded") return "Succeeded · Verified";
  if (status === "partially_succeeded") return "Partially succeeded";
  if (status === "running") return "Running";
  if (status === "queued") return "Queued";
  if (status === "failed") return "Failed";
  if (status === "cancelled") return "Cancelled";
  return "No run yet";
}

function LoadingShell() {
  return (
    <div className="loading-shell" role="status" aria-label="正在连接 Discovery Lab API">
      <div className="loading-brand"><span className="brand-mark"><Sparkles size={17} /></span> Discovery Lab</div>
      <div className="loading-card">
        <LoaderCircle className="spin" size={22} />
        <div>
          <strong>正在打开 Evidence Explorer</strong>
          <span>连接研究项目与证据索引…</span>
        </div>
      </div>
    </div>
  );
}

export function DiscoveryWorkbench() {
  const [mode, setMode] = useState<ConnectionMode>("loading");
  const [connectionError, setConnectionError] = useState("");
  const [studies, setStudies] = useState<Study[]>([]);
  const [selectedStudyId, setSelectedStudyId] = useState("");
  const [liveSources, setLiveSources] = useState<SourceItem[]>([]);
  const [sourceTotal, setSourceTotal] = useState(0);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState("");
  const [liveEvidence, setLiveEvidence] = useState<Evidence[]>([]);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState("");
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

  const loadContext = useCallback(async (item: Evidence) => {
    const requestId = ++contextRequestRef.current;
    setContextLoading(true);
    setContextError("");
    setLiveContext(null);
    try {
      const value = await api.getEvidenceContext(item.id);
      if (contextRequestRef.current === requestId) setLiveContext(value);
    } catch (error) {
      if (contextRequestRef.current === requestId) setContextError(safeMessage(error));
    } finally {
      if (contextRequestRef.current === requestId) setContextLoading(false);
    }
  }, []);

  const loadLiveEvidence = useCallback(async (studyId: string) => {
    const requestId = ++evidenceRequestRef.current;
    setEvidenceLoading(true);
    setEvidenceError("");
    try {
      const items = await api.getEvidence(studyId);
      if (evidenceRequestRef.current !== requestId) return;
      const firstItem = items[0] ?? null;
      setLiveEvidence(items);
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
      setSelectedEvidenceId("");
      setLiveContext(null);
      setEvidenceError(safeMessage(error));
    } finally {
      if (evidenceRequestRef.current === requestId) setEvidenceLoading(false);
    }
  }, [loadContext]);

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
      setSourcesError(safeMessage(sourcesResult.reason));
    }

    if (runsResult.status === "fulfilled") {
      setLiveRuns(runsResult.value.items);
      setRunTotal(runsResult.value.total);
    } else {
      setLiveRuns([]);
      setRunTotal(0);
      setRunsError(safeMessage(runsResult.reason));
    }
    setSourcesLoading(false);
    setRunsLoading(false);
  }, []);

  const connect = useCallback(async () => {
    setMode("loading");
    setConnectionError("");
    try {
      const items = await api.getStudies();
      const nextStudyId = items[0]?.id ?? "";
      setStudies(items);
      setSelectedStudyId(nextStudyId);
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
      setConnectionError(safeMessage(error));
      setStudies(demoStudies);
      setSelectedStudyId("demo-helphub");
      setSelectedEvidenceId("");
      setMode("demo");
      setLiveRuns([]);
      setRunTotal(1);
      setAgentEvents(demoAgentEvents.map((item) => ({ ...item })));
    }
  }, [loadLiveEvidence, loadLiveStudyData]);

  useEffect(() => {
    let cancelled = false;
    void api.getStudies().then((items) => {
      if (cancelled) return;
      const nextStudyId = items[0]?.id ?? "";
      setStudies(items);
      setSelectedStudyId(nextStudyId);
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
      setConnectionError(safeMessage(error));
      setStudies(demoStudies);
      setSelectedStudyId("demo-helphub");
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
  }, [loadLiveEvidence, loadLiveStudyData]);

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
    () => evidence.find((item) => item.id === activeEvidenceId) ?? null,
    [activeEvidenceId, evidence],
  );
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
    : evidenceRun ? agentEventsFromRun(evidenceRun) : [];
  const context = mode === "demo" && selectedEvidence ? demoContexts[selectedEvidence.id] ?? null : liveContext;
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
    setSelectedEvidenceId(item.id);
    if (mode === "live") void loadContext(item);
  }

  const filteredEvidence = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("zh-CN");
    return evidence.filter((item) => {
      if (kindFilter !== "all" && item.kind !== kindFilter) return false;
      if (!query) return true;
      return [item.title, item.quote, item.observation, item.sourceName, ...item.tags]
        .join(" ")
        .toLocaleLowerCase("zh-CN")
        .includes(query);
    });
  }, [evidence, kindFilter, search]);

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
      setCreateError(safeMessage(error));
    } finally {
      setCreatingStudy(false);
    }
  }

  async function handleFile(file?: File) {
    setDragActive(false);
    if (!file || !selectedStudy) return;
    if (mode !== "live") {
      setUploadNotice("Demo preview 不会上传文件。连接真实 API 后即可开始处理资料。");
      return;
    }
    if (file.size > 25 * 1024 * 1024) {
      setUploadNotice("文件超过当前 25 MB 的单文件限制。");
      return;
    }

    const temporaryId = `upload-${Date.now()}`;
    const temporarySource: SourceItem = {
      id: temporaryId,
      name: file.name,
      type: file.type || file.name.split(".").pop() || "file",
      status: "uploading",
      progress: 20,
      updatedAt: "刚刚",
    };
    setLiveSources((current) => [temporarySource, ...current]);
    setUploadNotice(`正在上传 ${file.name}…`);
    try {
      const uploaded = await api.uploadSource(selectedStudy.id, file);
      if (!uploaded.id) throw new ApiError("API 未返回 source id，无法启动处理");
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
          ? "处理完成：引用已通过可重放校验，正在刷新来源、证据与 Run。"
          : "处理任务已启动，Run 时间线会持续显示当前节点状态。",
      );
      void loadLiveEvidence(selectedStudy.id);
      void loadLiveStudyData(selectedStudy.id);
    } catch (error) {
      setLiveSources((current) =>
        current.map((item) =>
          item.id === temporaryId || item.name === file.name ? { ...item, status: "failed", progress: 0 } : item,
        ),
      );
      setUploadNotice(`处理失败：${safeMessage(error)}`);
      void loadLiveStudyData(selectedStudy.id);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  if (mode === "loading") return <LoadingShell />;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-row">
          <span className="brand-mark"><Sparkles size={17} strokeWidth={2.2} /></span>
          <span className="brand-name">Discovery Lab</span>
          <button className="icon-button sidebar-more" aria-label="打开工作区菜单"><ChevronDown size={15} /></button>
        </div>

        <nav className="primary-nav" aria-label="产品导航">
          <a className="nav-item active" href="#evidence"><BookOpenCheck size={16} />Evidence Explorer</a>
          <span className="nav-item"><GitBranch size={16} />Claims &amp; Opportunities</span>
          <a className="nav-item" href="#agent-run"><Activity size={16} />Agent Runs</a>
          <span className="nav-item"><FlaskConical size={16} />Eval &amp; Bad Cases</span>
          <span className="nav-item"><Layers3 size={16} />Integrations</span>
        </nav>

        <div className="studies-heading">
          <span>Studies</span>
          <button
            className="icon-button"
            aria-label="新建 Study"
            title={mode === "demo" ? "连接真实 API 后可新建 Study" : "新建 Study"}
            disabled={mode === "demo"}
            onClick={() => setShowNewStudy(true)}
          ><Plus size={16} /></button>
        </div>
        <div className="study-list" aria-label="Study 列表">
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
                <small>{study.evidenceCount} evidence · {formatRelativeDate(study.updatedAt)}</small>
              </span>
            </button>
          ))}
          {studies.length === 0 && <p className="sidebar-empty">还没有 Study。新建一个决策问题开始研究。</p>}
        </div>

        <div className="sidebar-footer">
          <div className="workspace-avatar">MP</div>
          <div><strong>Builder workspace</strong><small>Local development</small></div>
          <MoreHorizontal size={16} />
        </div>
      </aside>

      <main className="workspace">
        <header className="workspace-header">
          <div>
            <div className="breadcrumb"><FolderKanban size={14} />Studies <span>/</span> {selectedStudy?.title ?? "No study"}</div>
            <h1>Evidence Explorer</h1>
          </div>
          <div className="connection-cluster">
            <span className={`connection-pill ${mode}`}>
              <span className="connection-dot" />
              {mode === "live" ? "API live" : "Demo preview"}
            </span>
            <button className="icon-button header-button" aria-label="刷新连接与数据" onClick={() => void connect()}>
              <RefreshCw size={16} />
            </button>
          </div>
        </header>

        {mode === "demo" && (
          <div className="demo-banner" role="status">
            <div className="demo-banner-icon"><AlertCircle size={17} /></div>
            <div>
              <strong>Demo preview · 当前展示内置的 HelpHub 演示数据</strong>
              <span>未连接 {API_URL}（{connectionError || "API unavailable"}）。演示内容不会被当成真实 API 响应，也不会上传文件。</span>
            </div>
            <button className="text-button" onClick={() => void connect()}><RefreshCw size={14} />重新连接</button>
          </div>
        )}

        <div className="workspace-grid">
          <section className="evidence-column" id="evidence" aria-label="资料与证据列表">
            {selectedStudy ? (
              <>
                <article className="decision-card">
                  <div className="eyebrow"><Gauge size={14} />Current decision</div>
                  <h2>{selectedStudy.decisionQuestion}</h2>
                  <div className="decision-meta">
                    <span><FileCheck2 size={14} />{selectedStudy.sourceCount} sources</span>
                    <span><BookOpenCheck size={14} />{selectedStudy.evidenceCount} evidence</span>
                    <span className="decision-open">Open <ArrowRight size={13} /></span>
                  </div>
                </article>

                <section className="sources-section" aria-labelledby="sources-title">
                  <div className="section-heading">
                    <div>
                      <h2 id="sources-title">Sources</h2>
                      <span>{visibleSourcesLoading ? "Loading…" : `${visibleSourceTotal} in this Study`}</span>
                    </div>
                    {mode === "live" ? (
                      <button className="icon-button" aria-label="刷新来源与 Run" onClick={() => void loadLiveStudyData(selectedStudy.id)}>
                        <RefreshCw size={15} />
                      </button>
                    ) : (
                      <button className="icon-button" aria-label="更多资料操作"><MoreHorizontal size={17} /></button>
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
                      <strong>{mode === "demo" ? "Upload disabled in preview" : "Drop research files here"}</strong>
                      <span>PDF, CSV, TXT or Markdown · max 25 MB</span>
                    </div>
                    <label className="secondary-button" htmlFor="source-upload" aria-disabled={mode === "demo"}>Choose file</label>
                  </div>
                  {uploadNotice && <div className="upload-notice" role="status">{uploadNotice}</div>}

                  <div className="source-list">
                    {visibleSourcesLoading ? (
                      <div className="list-loading source-loading" role="status"><LoaderCircle className="spin" size={16} />Loading sources…</div>
                    ) : visibleSourcesError ? (
                      <div className="inline-error compact" role="alert">
                        <AlertCircle size={16} />
                        <div><strong>来源加载失败</strong><span>{visibleSourcesError}</span></div>
                        <button className="text-button" onClick={() => void loadLiveStudyData(selectedStudy.id)}>重试</button>
                      </div>
                    ) : sources.map((source) => {
                      const SourceIcon = fileIcon(source.type);
                      return (
                        <div className="source-row" key={source.id}>
                          <span className="source-icon"><SourceIcon size={17} /></span>
                          <div className="source-copy">
                            <strong>{source.name}</strong>
                            <span>{source.type}{source.revision ? ` · revision ${source.revision}` : ""}</span>
                            {(source.status === "processing" || source.status === "uploading") && (
                              <span className="progress-track" aria-label={`${source.progress ?? 0}% processed`}>
                                <span style={{ width: `${source.progress ?? 35}%` }} />
                              </span>
                            )}
                          </div>
                          <span className={`source-state ${source.status}`}>
                            {source.status === "ready" && <CheckCircle2 size={13} />}
                            {(source.status === "processing" || source.status === "uploading") && <LoaderCircle className="spin" size={13} />}
                            {source.status === "failed" && <AlertCircle size={13} />}
                            {source.status === "ready" ? "Ready" : source.status === "uploading" ? "Uploading" : source.status === "processing" ? `${source.progress ?? 0}%` : source.status}
                          </span>
                        </div>
                      );
                    })}
                    {!visibleSourcesLoading && !visibleSourcesError && sources.length === 0 && (
                      <p className="section-empty">这个 Study 还没有上传资料。</p>
                    )}
                  </div>
                </section>

                <section className="evidence-section" aria-labelledby="evidence-list-title">
                  <div className="section-heading evidence-heading">
                    <div><h2 id="evidence-list-title">Evidence</h2><span>{filteredEvidence.length} of {evidence.length}</span></div>
                    {mode === "live" && (
                      <button className="icon-button" aria-label="刷新证据" onClick={() => void loadLiveEvidence(selectedStudy.id)}>
                        <RefreshCw size={15} />
                      </button>
                    )}
                  </div>
                  <div className="evidence-tools">
                    <label className="search-box">
                      <Search size={15} />
                      <span className="sr-only">搜索证据</span>
                      <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search evidence…" />
                      {search && <button onClick={() => setSearch("")} aria-label="清除搜索"><X size={13} /></button>}
                    </label>
                    <label className="filter-select">
                      <Filter size={14} />
                      <span className="sr-only">按证据类型筛选</span>
                      <select value={kindFilter} onChange={(event) => setKindFilter(event.target.value as Evidence["kind"] | "all")}>
                        <option value="all">All types</option>
                        {Object.entries(kindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </label>
                  </div>

                  {visibleEvidenceLoading ? (
                    <div className="list-loading" role="status"><LoaderCircle className="spin" size={18} />Loading evidence…</div>
                  ) : visibleEvidenceError ? (
                    <div className="inline-error" role="alert">
                      <AlertCircle size={17} /><div><strong>证据加载失败</strong><span>{visibleEvidenceError}</span></div>
                      <button className="text-button" onClick={() => void loadLiveEvidence(selectedStudy.id)}>重试</button>
                    </div>
                  ) : (
                    <div className="evidence-list">
                      {filteredEvidence.map((item) => (
                        <button
                          className={`evidence-card ${item.id === activeEvidenceId ? "selected" : ""}`}
                          key={item.id}
                          aria-pressed={item.id === activeEvidenceId}
                          onClick={() => selectEvidence(item)}
                        >
                          <div className="evidence-card-top">
                            <span className={`kind-chip ${item.kind}`}>{kindLabels[item.kind]}</span>
                            <span className={`relationship ${item.relationship}`}>{item.relationship === "supports" ? "+" : item.relationship === "challenges" ? "−" : "·"} {relationshipLabels[item.relationship]}</span>
                            {item.syntheticDemo && <span className="synthetic-badge">Synthetic</span>}
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
                        <div className="empty-evidence"><Search size={20} /><strong>没有匹配的证据</strong><span>调整关键词或类型筛选。</span></div>
                      )}
                    </div>
                  )}
                </section>
              </>
            ) : (
              <div className="no-study">
                <FolderKanban size={25} />
                <h2>先建立一个 Study</h2>
                <p>用一个清晰、可做出取舍的决策问题，限定接下来要收集的证据。</p>
                <button className="primary-button" onClick={() => setShowNewStudy(true)}><Plus size={15} />New study</button>
              </div>
            )}
          </section>

          <aside className="detail-column" aria-label="选中证据详情">
            {selectedEvidence ? (
              <>
                <div className="detail-header">
                  <div><span>Evidence detail</span><h2>{selectedEvidence.title}</h2></div>
                  <button className="icon-button" aria-label="更多证据操作"><MoreHorizontal size={18} /></button>
                </div>

                <div className="detail-badges">
                  <span className={`review-badge ${selectedEvidence.reviewStatus}`}>
                    {selectedEvidence.reviewStatus === "approved" ? <ShieldCheck size={14} /> : <Clock3 size={14} />}
                    {reviewLabels[selectedEvidence.reviewStatus]}
                  </span>
                  <span className="confidence-badge"><Gauge size={14} />{Math.round(selectedEvidence.confidence * 100)}% confidence</span>
                  <span className={`kind-chip ${selectedEvidence.kind}`}>{kindLabels[selectedEvidence.kind]}</span>
                  {selectedEvidence.syntheticDemo && <span className="synthetic-badge detail-synthetic">Synthetic demo output</span>}
                </div>

                <section className="detail-section quote-section">
                  <div className="detail-label"><span>VERBATIM QUOTE</span><span className="truth-label">Source fact</span></div>
                  <blockquote>“{selectedEvidence.quote || "API 未返回原文摘录"}”</blockquote>
                </section>

                <div className="reasoning-grid">
                  <section className="detail-section">
                    <div className="detail-label"><span>OBSERVATION</span><span className="truth-label observation">Normalized</span></div>
                    <p>{selectedEvidence.observation || "尚未生成观察。"}</p>
                  </section>
                  <section className="detail-section interpretation-section">
                    <div className="detail-label"><span>INTERPRETATION</span><span className="truth-label inference">AI inference</span></div>
                    <p>{selectedEvidence.interpretation || "尚未生成解释。"}</p>
                  </section>
                </div>

                <section className="provenance-card">
                  <div className="provenance-head"><div className="source-icon"><FileText size={16} /></div><div><span>SOURCE &amp; LOCATOR</span><strong>{selectedEvidence.sourceName}</strong></div><Link2 size={15} /></div>
                  <dl>
                    <div><dt>Type</dt><dd>{selectedEvidence.sourceType}</dd></div>
                    <div><dt>Locator</dt><dd>{selectedEvidence.locatorLabel}</dd></div>
                    <div>
                      <dt>Evidence rev.</dt>
                      <dd className="mono">
                        {selectedEvidence.revisionId
                          ? `${selectedEvidence.revisionId}${selectedEvidence.revision ? ` · r${selectedEvidence.revision}` : ""}`
                          : selectedEvidence.revision ? `r${selectedEvidence.revision}` : "Unavailable"}
                      </dd>
                    </div>
                    <div><dt>Source rev.</dt><dd className="mono">{selectedEvidence.sourceRevisionId || "Unavailable"}</dd></div>
                    <div><dt>Run</dt><dd className="mono">{evidenceRun?.id || selectedEvidence.runId || "Unavailable"}</dd></div>
                    <div><dt>Run step</dt><dd className="mono">{selectedEvidence.runStepId || "Unavailable"}</dd></div>
                  </dl>
                </section>

                <section className="context-section">
                  <div className="section-heading">
                    <div><h2>Original context</h2><span>{context?.locatorLabel || selectedEvidence.locatorLabel}</span></div>
                    {mode === "live" && <button className="text-button" onClick={() => void loadContext(selectedEvidence)}><RefreshCw size={13} />Reload</button>}
                  </div>
                  {visibleContextLoading ? (
                    <div className="context-loading" role="status"><LoaderCircle className="spin" size={17} />Locating source passage…</div>
                  ) : visibleContextError ? (
                    <div className="inline-error compact" role="alert"><AlertCircle size={16} /><div><strong>原文定位失败</strong><span>{visibleContextError}</span></div></div>
                  ) : context ? (
                    <>
                      <div className="source-context">
                        <p>{context.before}</p>
                        <mark>{context.highlight}</mark>
                        <p>{context.after}</p>
                      </div>
                      {context.integrity && (
                        <div className="integrity-card" aria-label="Deterministic citation integrity checks">
                          <div className="integrity-heading">
                            <div><ShieldCheck size={15} /><strong>Citation integrity</strong></div>
                            <span>Deterministic replay</span>
                          </div>
                          <div className="integrity-checks">
                            {[
                              ["Exact quote", context.integrity.quoteMatchesSegment],
                              ["Segment hash", context.integrity.segmentHashMatches],
                              ["Evidence hash", context.integrity.evidenceHashMatches],
                            ].map(([label, passed]) => (
                              <span className={`integrity-check ${passed ? "passed" : "failed"}`} key={String(label)}>
                                {passed ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
                                {label}
                              </span>
                            ))}
                          </div>
                          <div className="integrity-hashes">
                            <span>Source SHA-256 <code title={context.sourceContentHash}>{shortHash(context.sourceContentHash)}</code></span>
                            <span>Segment <code title={context.segmentContentHash}>{shortHash(context.segmentContentHash)}</code></span>
                            <span>
                              Evidence
                              <code title={context.evidenceContentHash || selectedEvidence.contentHash}>
                                {shortHash(context.evidenceContentHash || selectedEvidence.contentHash)}
                              </code>
                            </span>
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    <p className="section-empty">这条证据没有可显示的上下文。</p>
                  )}
                </section>

                <section className="agent-run" id="agent-run">
                  <div className="agent-run-heading">
                    <div>
                      <span>
                        {mode === "live" && evidenceRun
                          ? `EVIDENCE RUN · ${selectedEvidence.sourceName}`
                          : mode === "live" && runTotal > 0
                            ? `${runTotal} RUN${runTotal === 1 ? "" : "S"} IN STUDY · NONE LINKED`
                            : "AGENT RUN"}
                      </span>
                      <strong>
                        {evidenceRun ? `${evidenceRun.workflowName} · v${evidenceRun.workflowVersion}` : "Evidence extraction pipeline"}
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
                      {mode === "demo" && currentRunStatus === undefined ? "Demo run" : runStatusLabel(currentRunStatus)}
                    </span>
                  </div>
                  {mode === "live" && runsLoading ? (
                    <div className="agent-empty"><LoaderCircle className="spin" size={17} /><span>Loading latest run…</span></div>
                  ) : mode === "live" && runsError ? (
                    <div className="inline-error compact" role="alert">
                      <AlertCircle size={16} />
                      <div><strong>Run 加载失败</strong><span>{runsError}</span></div>
                      <button className="text-button" onClick={() => void loadLiveStudyData(selectedEvidence.studyId)}>重试</button>
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
                          ? "没有找到与当前证据或来源关联的 Run，因此不会展示其他来源的时间线。"
                          : "这个 Study 还没有处理 Run；上传资料后会显示三个可追踪节点。"}
                      </span>
                    </div>
                  )}
                </section>
              </>
            ) : (
              <div className="detail-empty"><BookOpenCheck size={25} /><h2>选择一条证据</h2><p>在这里核对原始引用、来源定位、不可变 revision 和 AI 推理。</p></div>
            )}
          </aside>
        </div>
      </main>

      {showNewStudy && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setShowNewStudy(false)}>
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="new-study-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-head"><div><span>NEW STUDY</span><h2 id="new-study-title">Define the decision</h2></div><button className="icon-button" aria-label="关闭" onClick={() => setShowNewStudy(false)}><X size={17} /></button></div>
            <form onSubmit={(event) => void createStudy(event)}>
              <label>Study name<input autoFocus value={newStudyTitle} onChange={(event) => setNewStudyTitle(event.target.value)} placeholder="e.g. Enterprise onboarding" required /></label>
              <label>Decision question<textarea value={newStudyQuestion} onChange={(event) => setNewStudyQuestion(event.target.value)} placeholder="What decision should the evidence help us make?" rows={4} required /></label>
              {createError && <div className="form-error" role="alert">{createError}</div>}
              <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setShowNewStudy(false)}>Cancel</button><button className="primary-button" disabled={creatingStudy}>{creatingStudy && <LoaderCircle className="spin" size={14} />}Create study</button></div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
