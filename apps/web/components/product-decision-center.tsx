"use client";

import {
  AlertCircle,
  ArrowUpRight,
  CheckCircle2,
  FileCheck2,
  FileText,
  FlaskConical,
  GitCommitHorizontal,
  Link2,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
  Scale,
  ShieldAlert,
} from "lucide-react";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import {
  API_URL,
  api,
  type PrdArtifact,
  type PrdCitation,
  type ProductArtifactBundle,
  type ProductArtifactChain,
  type ProductDecision,
  type Study,
} from "@/lib/api";
import type { MessageKey, TranslationVars } from "@/lib/i18n";

type Translator = (key: MessageKey, vars?: TranslationVars) => string;

type ProductDecisionCenterProps = {
  live: boolean;
  study?: Study | null;
  t: Translator;
};

const SECTION_KEYS = {
  problem: "product.section.problem",
  evidence_summary: "product.section.evidence_summary",
  hypothesis: "product.section.hypothesis",
  experiment: "product.section.experiment",
  decision: "product.section.decision",
  scope: "product.section.scope",
  non_goals: "product.section.non_goals",
  success_metrics: "product.section.success_metrics",
  risks_and_guardrails: "product.section.risks_and_guardrails",
  rollout: "product.section.rollout",
} as const satisfies Record<string, MessageKey>;

function requestId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `product-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function shortHash(value: string): string {
  return `${value.slice(0, 10)}…${value.slice(-8)}`;
}

function CitationCard({ citation, t }: { citation: PrdCitation; t: Translator }) {
  const isClaim = citation.kind === "claim_revision";
  return (
    <article className={`product-citation ${citation.kind}`}>
      <header>
        <span>{isClaim ? <GitCommitHorizontal size={13} /> : <Link2 size={13} />}</span>
        <div>
          <strong>{isClaim ? t("product.claimCitation") : t("product.evidenceCitation")}</strong>
          <small>{t("product.reviewedBy", { reviewer: citation.reviewReviewer })}</small>
        </div>
        <CheckCircle2 size={15} />
      </header>
      {isClaim ? (
        <>
          <p>{citation.statement}</p>
          <dl>
            <div><dt>{t("product.claimRevision")}</dt><dd><code>{citation.claimRevisionId}</code></dd></div>
            <div><dt>{t("product.contentHash")}</dt><dd><code title={citation.contentHash}>{shortHash(citation.contentHash)}</code></dd></div>
          </dl>
        </>
      ) : (
        <>
          <blockquote>{citation.quote}</blockquote>
          {citation.observation && <p>{citation.observation}</p>}
          <dl>
            <div><dt>{t("product.evidenceRevision")}</dt><dd><code>{citation.evidenceRevisionId}</code></dd></div>
            <div><dt>{t("product.sourceRevision")}</dt><dd><code>{citation.sourceRevisionId}</code></dd></div>
            <div><dt>{t("product.contentHash")}</dt><dd><code title={citation.evidenceContentHash}>{shortHash(citation.evidenceContentHash)}</code></dd></div>
            <div><dt>{t("product.sourceHash")}</dt><dd><code title={citation.sourceContentHash}>{shortHash(citation.sourceContentHash)}</code></dd></div>
          </dl>
        </>
      )}
      <a href={`${API_URL}${citation.contextUrl}`} target="_blank" rel="noreferrer">
        {t("product.openExact")}<ArrowUpRight size={12} />
      </a>
    </article>
  );
}

function PrdCard({ prd, t }: { prd: PrdArtifact; t: Translator }) {
  return (
    <article className="product-prd-card">
      <header>
        <div>
          <span><FileText size={13} />{t("product.prdDraft")}</span>
          <h4>{prd.title}</h4>
          <code title={prd.contentHash}>{shortHash(prd.contentHash)}</code>
        </div>
        <span className="product-not-publishable"><ShieldAlert size={13} />{t("product.notPublishable")}</span>
      </header>
      <section className="product-blockers">
        <strong>{t("product.blockers")}</strong>
        <div>{prd.publicationBlockers.map((blocker) => <code key={blocker}>{blocker}</code>)}</div>
      </section>
      <section className="product-prd-sections">
        <h5>{t("product.sections")}</h5>
        {Object.entries(prd.sections).map(([name, section]) => (
          <details open={name === "problem" || name === "evidence_summary"} key={name}>
            <summary>{t(SECTION_KEYS[name as keyof typeof SECTION_KEYS] ?? "product.sections")}</summary>
            <p>{section.body}</p>
            {section.citationRefs.length > 0 && (
              <div className="product-section-refs">
                {section.citationRefs.map((citationId) => <code key={citationId}>{citationId}</code>)}
              </div>
            )}
          </details>
        ))}
      </section>
      <section className="product-citations">
        <header>
          <div><span>{t("product.citations")}</span><strong>{t("product.citationCount", { count: prd.citations.length })}</strong></div>
          <LockKeyhole size={17} />
        </header>
        <div>{prd.citations.map((citation) => <CitationCard citation={citation} t={t} key={citation.citationId} />)}</div>
      </section>
    </article>
  );
}

function DecisionCard({
  decision,
  prds,
  t,
  onPrd,
}: {
  decision: ProductDecision;
  prds: PrdArtifact[];
  t: Translator;
  onPrd: (prd: PrdArtifact) => void;
}) {
  const [title, setTitle] = useState("Product Discovery PRD");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setGenerating(true);
    setError("");
    try {
      onPrd(await api.createPrd(decision.id, {
        title: title.trim(),
        clientRequestId: requestId(),
      }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("general.unknownError"));
    } finally {
      setGenerating(false);
    }
  }

  return (
    <article className={`product-decision-card decision-${decision.decision.toLowerCase()}`}>
      <header>
        <span><Scale size={14} />{t(`product.decision.${decision.decision}`)}</span>
        <code>{decision.id}</code>
      </header>
      <p>{decision.observedResult}</p>
      <small>{decision.rationale} · {decision.decidedBy}</small>
      <form className="product-prd-form" onSubmit={(event) => void generate(event)}>
        <label>{t("product.prdTitle")}<input value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
        <button className="secondary-button" type="submit" disabled={generating || !title.trim()}>
          {generating ? <LoaderCircle className="spin" size={13} /> : <FileCheck2 size={13} />}
          {t("product.generatePrd")}
        </button>
      </form>
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="product-prd-list">
        {prds.length === 0
          ? <p className="section-empty">{t("product.noPrds")}</p>
          : prds.map((prd) => <PrdCard prd={prd} t={t} key={prd.id} />)}
      </div>
    </article>
  );
}

function ProductChainCard({
  chain,
  t,
  onDecision,
  onPrd,
}: {
  chain: ProductArtifactChain;
  t: Translator;
  onDecision: (decision: ProductDecision) => void;
  onPrd: (prd: PrdArtifact) => void;
}) {
  const [decision, setDecision] = useState<ProductDecision["decision"]>("PROCEED");
  const [observedResult, setObservedResult] = useState("");
  const [rationale, setRationale] = useState("");
  const [decidedBy, setDecidedBy] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function saveDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const created = await api.createProductDecision(chain.experiment.id, {
        decision,
        observedResult: observedResult.trim(),
        rationale: rationale.trim(),
        decidedBy: decidedBy.trim(),
        clientRequestId: requestId(),
      });
      onDecision(created);
      setObservedResult("");
      setRationale("");
      setDecidedBy("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("general.unknownError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="product-chain-card">
      <header>
        <div><span>{t("product.chain")}</span><h2>{chain.experiment.title}</h2></div>
        <code>{chain.experiment.id}</code>
      </header>
      <div className="product-artifact-pair">
        <article className="product-hypothesis">
          <span><FlaskConical size={13} />{t("product.hypothesis")}</span>
          <h3>{chain.hypothesis.statement}</h3>
          <dl>
            <div><dt>{t("product.expectedOutcome")}</dt><dd>{chain.hypothesis.expectedOutcome}</dd></div>
            <div><dt>{t("product.falsification")}</dt><dd>{chain.hypothesis.falsificationCriterion}</dd></div>
          </dl>
        </article>
        <article className="product-experiment">
          <span><FileCheck2 size={13} />{t("product.experiment")}</span>
          <dl>
            <div><dt>{t("product.cohort")}</dt><dd>{chain.experiment.targetCohort}</dd></div>
            <div><dt>{t("product.metric")}</dt><dd>{chain.experiment.primaryMetric}</dd></div>
            <div><dt>{t("product.threshold")}</dt><dd>{chain.experiment.successThreshold}</dd></div>
          </dl>
        </article>
      </div>
      <section className="product-pins">
        <strong><LockKeyhole size={13} />{t("product.exactPins")}</strong>
        <div><span>{t("product.claimRevision")}</span><code>{chain.hypothesis.claimRevisionId}</code></div>
        <div><span>{t("product.contextManifest")}</span><code>{chain.hypothesis.contextManifestId}</code></div>
        <div><span>{t("product.toolCall")}</span><code>{chain.experiment.toolCallId}</code></div>
      </section>
      <div className="product-decision-grid">
        <form className="product-decision-form" onSubmit={(event) => void saveDecision(event)}>
          <h3>{t("product.decisionForm")}</h3>
          <label>{t("product.decision")}
            <select value={decision} onChange={(event) => setDecision(event.target.value as ProductDecision["decision"])}>
              <option value="PROCEED">{t("product.decision.PROCEED")}</option>
              <option value="ITERATE">{t("product.decision.ITERATE")}</option>
              <option value="STOP">{t("product.decision.STOP")}</option>
            </select>
          </label>
          <label>{t("product.observedResult")}<textarea value={observedResult} onChange={(event) => setObservedResult(event.target.value)} rows={3} required /></label>
          <label>{t("product.decisionRationale")}<textarea value={rationale} onChange={(event) => setRationale(event.target.value)} rows={2} required /></label>
          <label>{t("product.decidedBy")}<input value={decidedBy} onChange={(event) => setDecidedBy(event.target.value)} required /></label>
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="primary-button" type="submit" disabled={saving || !observedResult.trim() || !rationale.trim() || !decidedBy.trim()}>
            {saving ? <LoaderCircle className="spin" size={13} /> : <Scale size={13} />}{t("product.saveDecision")}
          </button>
        </form>
        <section className="product-decision-history">
          <h3>{t("product.decisionHistory")}</h3>
          {chain.decisions.length === 0 ? (
            <p className="section-empty">{t("product.noDecisions")}</p>
          ) : (
            chain.decisions.map((item) => (
              <DecisionCard
                decision={item}
                prds={chain.prds.filter((prd) => prd.decisionId === item.id)}
                t={t}
                onPrd={onPrd}
                key={item.id}
              />
            ))
          )}
        </section>
      </div>
    </section>
  );
}

export function ProductDecisionCenter({ live, study, t }: ProductDecisionCenterProps) {
  const [bundle, setBundle] = useState<ProductArtifactBundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const requestRef = useRef(0);

  const load = useCallback(async () => {
    if (!live || !study) return;
    const request = ++requestRef.current;
    setLoading(true);
    setError("");
    try {
      const next = await api.getProductArtifacts(study.id);
      if (requestRef.current === request) setBundle(next);
    } catch (cause) {
      if (requestRef.current === request) {
        setBundle(null);
        setError(cause instanceof Error ? cause.message : t("general.unknownError"));
      }
    } finally {
      if (requestRef.current === request) setLoading(false);
    }
  }, [live, study, t]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setBundle(null);
      if (live && study) void load();
    }, 0);
    return () => {
      window.clearTimeout(timer);
      requestRef.current += 1;
    };
  }, [live, load, study]);

  function addDecision(experimentId: string, decision: ProductDecision) {
    setBundle((current) => current ? {
      ...current,
      items: current.items.map((chain) => chain.experiment.id === experimentId
        ? { ...chain, decisions: [decision, ...chain.decisions] }
        : chain),
    } : current);
  }

  function addPrd(experimentId: string, prd: PrdArtifact) {
    setBundle((current) => current ? {
      ...current,
      items: current.items.map((chain) => chain.experiment.id === experimentId
        ? { ...chain, prds: [prd, ...chain.prds] }
        : chain),
    } : current);
  }

  if (!live) {
    return <section className="product-center product-center-empty"><Scale size={25} /><h1>{t("product.title")}</h1><p>{t("product.liveOnly")}</p></section>;
  }
  if (!study) {
    return <section className="product-center product-center-empty"><Scale size={25} /><h1>{t("product.title")}</h1><p>{t("product.noStudy")}</p></section>;
  }

  return (
    <div className="product-center" aria-label={t("product.region")}>
      <section className="product-center-hero">
        <div><span>{t("product.eyebrow")}</span><h1>{t("product.title")}</h1><p>{t("product.body")}</p></div>
        <button className="secondary-button" type="button" onClick={() => void load()} disabled={loading}>
          {loading ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />}{t("product.refresh")}
        </button>
      </section>
      {error && <div className="inline-error" role="alert"><AlertCircle size={16} /><div><strong>{t("product.loadFailed")}</strong><span>{error}</span></div></div>}
      {loading && !bundle && <div className="product-loading"><LoaderCircle className="spin" size={17} />{t("product.loading")}</div>}
      {bundle?.items.length === 0 && (
        <section className="product-no-experiments"><ShieldAlert size={22} /><h2>{t("product.noExperiments")}</h2><p>{t("product.noExperimentsHelp")}</p></section>
      )}
      <div className="product-chain-list">
        {bundle?.items.map((chain) => (
          <ProductChainCard
            chain={chain}
            t={t}
            onDecision={(decision) => addDecision(chain.experiment.id, decision)}
            onPrd={(prd) => addPrd(chain.experiment.id, prd)}
            key={chain.experiment.id}
          />
        ))}
      </div>
    </div>
  );
}
