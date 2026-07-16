"use client";

import {
  Activity,
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  Database,
  FlaskConical,
  KeyRound,
  LoaderCircle,
  LockKeyhole,
  Play,
  RefreshCw,
  ShieldCheck,
  Wrench,
  XCircle,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  type AgentRun,
  type AgentToolCall,
  type Claim,
  type Study,
  type ToolRegistry,
} from "@/lib/api";
import type { MessageKey, TranslationVars } from "@/lib/i18n";

type Translator = (key: MessageKey, vars?: TranslationVars) => string;

type AgentRunCenterProps = {
  live: boolean;
  study: Study | null;
  t: Translator;
};

function requestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `request-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function stringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "[unserializable]";
  }
}

function shortHash(value: string): string {
  return value.length > 22 ? `${value.slice(0, 10)}…${value.slice(-8)}` : value;
}

function ToolCallCard({ call, t }: { call: AgentToolCall; t: Translator }) {
  return (
    <article className={`agent-tool-call ${call.accessMode} status-${call.status.toLowerCase()}`}>
      <header>
        <div>
          <span><Wrench size={12} />{call.accessMode} · {call.riskLevel}</span>
          <h3>{call.toolName}</h3>
        </div>
        <span className="agent-tool-status">{call.status}</span>
      </header>
      <div className="agent-hash-lock">
        <LockKeyhole size={12} />
        <span>{t("agent.argumentsHash")}</span>
        <code title={call.argumentsHash}>{shortHash(call.argumentsHash)}</code>
      </div>
      <details>
        <summary>{t("agent.arguments")}</summary>
        <pre>{stringify(call.arguments)}</pre>
      </details>
      <div className="agent-policy-strip">
        <span>{call.requiresApproval ? t("agent.approvalRequired") : t("agent.autoReadOnly")}</span>
        <code>{String(call.policySnapshot.approval_binding ?? "server_allowlist")}</code>
      </div>
      {call.result && (
        <div className="agent-tool-result">
          <CheckCircle2 size={13} />
          <div><strong>{t("agent.toolExecuted")}</strong><pre>{stringify(call.result)}</pre></div>
        </div>
      )}
      {call.approval && (
        <p className="agent-approval-record">
          <ShieldCheck size={12} />
          {call.approval.decision} · {call.approval.reviewer} · {call.approval.rationale}
        </p>
      )}
    </article>
  );
}

export function AgentRunCenter({ live, study, t }: AgentRunCenterProps) {
  const [registry, setRegistry] = useState<ToolRegistry | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState("");
  const [claimRevisionId, setClaimRevisionId] = useState("");
  const [goal, setGoal] = useState("");
  const [query, setQuery] = useState("");
  const [title, setTitle] = useState("");
  const [metric, setMetric] = useState("");
  const [threshold, setThreshold] = useState("");
  const [cohort, setCohort] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [approvalRationale, setApprovalRationale] = useState("");
  const requestRef = useRef(0);

  const reviewedClaims = useMemo(() => claims.filter((claim) => (
    claim.isCurrent && claim.status === "REVIEWED" && claim.revisionStatus === "REVIEWED"
  )), [claims]);
  const selectedRun = runs.find((run) => run.id === selectedRunId) ?? runs[0] ?? null;
  const pendingToolCall = selectedRun?.toolCalls.find((call) => (
    call.status === "APPROVAL_REQUIRED" && call.requiresApproval
  )) ?? null;

  const load = useCallback(async () => {
    if (!live || !study) return;
    const request = ++requestRef.current;
    setLoading(true);
    setError("");
    try {
      const [nextRegistry, nextRuns, nextClaims] = await Promise.all([
        api.getToolRegistry(),
        api.getAgentRuns(study.id, 50),
        api.getClaims(study.id, 100, 0),
      ]);
      if (requestRef.current !== request) return;
      const eligible = nextClaims.items.filter((claim) => (
        claim.isCurrent && claim.status === "REVIEWED" && claim.revisionStatus === "REVIEWED"
      ));
      setRegistry(nextRegistry);
      setRuns(nextRuns.items);
      setClaims(nextClaims.items);
      setSelectedRunId(nextRuns.items[0]?.id ?? "");
      setClaimRevisionId((current) => (
        eligible.some((claim) => claim.claimRevisionId === current)
          ? current
          : eligible[0]?.claimRevisionId ?? ""
      ));
    } catch (cause) {
      if (requestRef.current === request) {
        setError(cause instanceof Error ? cause.message : t("general.unknownError"));
      }
    } finally {
      if (requestRef.current === request) setLoading(false);
    }
  }, [live, study, t]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setRegistry(null);
      setClaims([]);
      setRuns([]);
      setSelectedRunId("");
      setClaimRevisionId("");
      if (live && study) void load();
    }, 0);
    return () => {
      window.clearTimeout(timer);
      requestRef.current += 1;
    };
  }, [live, load, study]);

  async function startRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!live || !study || !claimRevisionId) return;
    setSubmitting(true);
    setError("");
    try {
      const run = await api.createAgentRun(study.id, {
        goal: goal.trim(),
        claimRevisionId,
        retrieval: { query: query.trim(), purpose: "support", limit: 5 },
        requestedAction: {
          toolName: "create_experiment_draft",
          arguments: {
            title: title.trim(),
            primaryMetric: metric.trim(),
            successThreshold: threshold.trim(),
            targetCohort: cohort.trim(),
          },
        },
        clientRequestId: requestId(),
      });
      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      setSelectedRunId(run.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("general.unknownError"));
    } finally {
      setSubmitting(false);
    }
  }

  async function decide(decision: "APPROVE" | "REJECT") {
    if (!pendingToolCall || !reviewer.trim() || !approvalRationale.trim()) return;
    setApproving(true);
    setError("");
    try {
      const run = await api.approveToolCall(pendingToolCall.id, {
        decision,
        argumentsHash: pendingToolCall.argumentsHash,
        reviewer: reviewer.trim(),
        rationale: approvalRationale.trim(),
        clientRequestId: requestId(),
      });
      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      setSelectedRunId(run.id);
      setReviewer("");
      setApprovalRationale("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("general.unknownError"));
    } finally {
      setApproving(false);
    }
  }

  if (!live) {
    return (
      <section className="agent-center agent-center-empty">
        <Activity size={25} />
        <h1>{t("agent.title")}</h1>
        <p>{t("agent.liveOnly")}</p>
      </section>
    );
  }
  if (!study) {
    return (
      <section className="agent-center agent-center-empty">
        <Activity size={25} /><h1>{t("agent.title")}</h1><p>{t("agent.noStudy")}</p>
      </section>
    );
  }

  return (
    <div className="agent-center" aria-label={t("agent.region")}>
      <section className="agent-center-hero">
        <div><span>{t("agent.eyebrow")}</span><h1>{t("agent.title")}</h1><p>{t("agent.body")}</p></div>
        <button className="secondary-button" type="button" onClick={() => void load()} disabled={loading}>
          {loading ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />}
          {t("agent.refresh")}
        </button>
      </section>

      {error && <div className="inline-error" role="alert"><AlertCircle size={16} /><div><strong>{t("agent.failed")}</strong><span>{error}</span></div></div>}

      <div className="agent-center-grid">
        <section className="agent-builder">
          <div className="agent-section-heading">
            <div><span>{t("agent.builderEyebrow")}</span><h2>{t("agent.builder")}</h2></div>
            <FlaskConical size={18} />
          </div>
          {reviewedClaims.length === 0 ? (
            <div className="agent-prerequisite"><AlertCircle size={16} /><div><strong>{t("agent.noReviewedClaim")}</strong><p>{t("agent.noReviewedClaimHelp")}</p></div></div>
          ) : (
            <form className="agent-run-form" onSubmit={(event) => void startRun(event)}>
              <label>{t("agent.claim")}
                <select value={claimRevisionId} onChange={(event) => setClaimRevisionId(event.target.value)} required>
                  {reviewedClaims.map((claim) => <option value={claim.claimRevisionId} key={claim.claimRevisionId}>{claim.statement}</option>)}
                </select>
              </label>
              <label>{t("agent.goal")}<textarea value={goal} onChange={(event) => setGoal(event.target.value)} rows={2} required /></label>
              <label>{t("agent.query")}<input value={query} onChange={(event) => setQuery(event.target.value)} required /></label>
              <div className="agent-form-pair">
                <label>{t("agent.experimentTitle")}<input value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
                <label>{t("agent.cohort")}<input value={cohort} onChange={(event) => setCohort(event.target.value)} required /></label>
              </div>
              <div className="agent-form-pair">
                <label>{t("agent.metric")}<input value={metric} onChange={(event) => setMetric(event.target.value)} required /></label>
                <label>{t("agent.threshold")}<input value={threshold} onChange={(event) => setThreshold(event.target.value)} required /></label>
              </div>
              <p className="agent-form-policy"><ShieldCheck size={13} />{t("agent.startPolicy")}</p>
              <button className="primary-button" type="submit" disabled={submitting}>
                {submitting ? <LoaderCircle className="spin" size={14} /> : <Play size={14} />}{t("agent.start")}
              </button>
            </form>
          )}
        </section>

        <section className="tool-registry">
          <div className="agent-section-heading">
            <div><span>{registry?.policyVersion ?? "tool-policy.v1"}</span><h2>{t("agent.registry")}</h2></div>
            <KeyRound size={18} />
          </div>
          <p className="agent-registry-help">{t("agent.registryHelp")}</p>
          <div className="tool-definition-list">
            {registry?.items.map((tool) => (
              <article key={tool.name}>
                <header><div><span>{tool.accessMode} · {tool.riskLevel}</span><h3>{tool.name}</h3></div><code>v{tool.version}</code></header>
                <p>{tool.description}</p>
                <div><span><ShieldCheck size={11} />{t("agent.allowlisted")}</span><span>{tool.requiresApproval ? t("agent.approvalRequired") : t("agent.autoReadOnly")}</span>{tool.mcpExposed && <span>MCP</span>}</div>
              </article>
            ))}
          </div>
        </section>
      </div>

      <section className="agent-run-workspace">
        <header>
          <div><span>{t("agent.persistedRuns")}</span><h2>{t("agent.runInspector")}</h2></div>
          {runs.length > 0 && <select aria-label={t("agent.selectRun")} value={selectedRun?.id ?? ""} onChange={(event) => setSelectedRunId(event.target.value)}>{runs.map((run) => <option value={run.id} key={run.id}>{run.phase} · {run.id}</option>)}</select>}
        </header>
        {!selectedRun ? (
          <div className="agent-run-empty"><CircleDashed size={20} /><p>{t("agent.noRuns")}</p></div>
        ) : (
          <>
            <div className={`agent-phase-banner phase-${selectedRun.phase.toLowerCase()}`}>
              {selectedRun.phase === "WAITING_HUMAN" ? <LockKeyhole size={18} /> : selectedRun.phase === "COMPLETED" ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
              <div><span>{selectedRun.workflowName} · v{selectedRun.workflowVersion}</span><strong>{selectedRun.phase === "WAITING_HUMAN" ? t("agent.waitingHuman") : t(`agent.phase.${selectedRun.phase}`)}</strong></div>
              <code>{selectedRun.id}</code>
            </div>
            <div className="agent-context-grid">
              <article><span><Database size={12} />{t("agent.contextManifest")}</span><strong>{selectedRun.contextManifest.id}</strong><p>{selectedRun.contextManifest.query}</p><code title={selectedRun.contextManifest.contentHash}>{shortHash(selectedRun.contextManifest.contentHash)}</code><small>{t("agent.contextItems", { count: selectedRun.contextManifest.itemCount })}</small></article>
              <article><span>{t("agent.promptProfile")}</span><strong>{String(selectedRun.promptProfile.system_prompt_version ?? "discovery-agent-system.v1")}</strong>{Object.entries(selectedRun.promptProfile).slice(0, 5).map(([key, value]) => <p key={key}><code>{key}</code><span>{String(value)}</span></p>)}</article>
              <article><span>{t("agent.hypothesis")}</span><strong>{String(selectedRun.hypothesis.statement ?? t("general.unavailable"))}</strong><p>{String(selectedRun.hypothesis.falsification_criterion ?? "")}</p></article>
            </div>
            <ol className="agent-step-grid">
              {selectedRun.steps.map((step) => <li className={step.status} key={step.id}><span>{step.ordinal + 1}</span><div><strong>{step.name}</strong><small>{step.status}</small></div></li>)}
            </ol>
            <div className="agent-tool-call-list">{selectedRun.toolCalls.map((call) => <ToolCallCard call={call} t={t} key={call.id} />)}</div>
            {pendingToolCall && (
              <section className="agent-approval-gate">
                <header><div><span>{t("agent.hitlEyebrow")}</span><h3>{t("agent.hitlTitle")}</h3></div><LockKeyhole size={19} /></header>
                <p>{t("agent.hitlBody")}</p>
                <div className="agent-hash-lock large"><LockKeyhole size={13} /><span>{t("agent.exactApproval")}</span><code title={pendingToolCall.argumentsHash}>{pendingToolCall.argumentsHash}</code></div>
                <div className="agent-form-pair"><label>{t("agent.reviewer")}<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></label><label>{t("agent.approvalRationale")}<textarea value={approvalRationale} onChange={(event) => setApprovalRationale(event.target.value)} rows={2} /></label></div>
                <div className="agent-approval-actions"><button className="danger-button" type="button" disabled={approving || !reviewer.trim() || !approvalRationale.trim()} onClick={() => void decide("REJECT")}>{t("agent.reject")}</button><button className="primary-button" type="button" disabled={approving || !reviewer.trim() || !approvalRationale.trim()} onClick={() => void decide("APPROVE")}>{approving && <LoaderCircle className="spin" size={13} />}{t("agent.approve")}</button></div>
              </section>
            )}
          </>
        )}
      </section>
    </div>
  );
}
