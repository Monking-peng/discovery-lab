"use client";

import {
  AlertCircle,
  Bug,
  Check,
  CheckCircle2,
  FlaskConical,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  type BadCaseInbox,
  type CurrentEvaluationReport,
  type EvaluationCase,
  type EvaluationSuite,
} from "@/lib/api";
import type { MessageKey, TranslationVars } from "@/lib/i18n";

type Translator = (key: MessageKey, vars?: TranslationVars) => string;

type EvaluationCenterProps = {
  live: boolean;
  t: Translator;
};

function compactValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return "[unserializable]";
  }
}

function CaseRow({ item, t }: { item: EvaluationCase; t: Translator }) {
  return (
    <li className={`eval-case ${item.status}`}>
      <div className="eval-case-heading">
        <span className="eval-case-status" aria-label={t(`eval.status.${item.status}`)}>
          {item.status === "passed" ? <Check size={12} /> : item.status === "failed" ? <X size={12} /> : "–"}
        </span>
        <code>{item.caseId}</code>
        <strong>{t(`eval.status.${item.status}`)}</strong>
      </div>
      <div className="eval-assertions">
        {Object.entries(item.assertions).map(([name, passed]) => (
          <span className={passed ? "passed" : "failed"} key={name}>
            {passed ? <CheckCircle2 size={11} /> : <AlertCircle size={11} />}
            {name}
          </span>
        ))}
      </div>
      {Object.keys(item.details).length > 0 && (
        <details>
          <summary>{t("eval.caseDetails")}</summary>
          <dl>
            {Object.entries(item.details).map(([name, value]) => (
              <div key={name}><dt>{name}</dt><dd>{compactValue(value)}</dd></div>
            ))}
          </dl>
        </details>
      )}
    </li>
  );
}

function SuiteCard({ suite, t }: { suite: EvaluationSuite; t: Translator }) {
  return (
    <section className="eval-suite" aria-label={suite.dataset}>
      <header>
        <div>
          <span>{t("eval.executableDataset")}</span>
          <h2>{suite.dataset}</h2>
        </div>
        <code>r{suite.datasetRevision}</code>
      </header>
      <div className="eval-suite-metrics">
        <span><strong>{suite.summary.case_count}</strong>{t("eval.cases")}</span>
        <span className="passed"><strong>{suite.summary.passed}</strong>{t("eval.passed")}</span>
        <span className={suite.summary.failed > 0 ? "failed" : ""}><strong>{suite.summary.failed}</strong>{t("eval.failed")}</span>
      </div>
      <ol className="eval-case-list">
        {suite.cases.map((item) => <CaseRow item={item} t={t} key={item.caseId} />)}
      </ol>
    </section>
  );
}

export function EvaluationCenter({ live, t }: EvaluationCenterProps) {
  const [report, setReport] = useState<CurrentEvaluationReport | null>(null);
  const [inbox, setInbox] = useState<BadCaseInbox | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const requestRef = useRef(0);

  const load = useCallback(async () => {
    if (!live) return;
    const request = ++requestRef.current;
    setLoading(true);
    setError("");
    try {
      const [nextReport, nextInbox] = await Promise.all([
        api.getCurrentEvaluationReport(),
        api.getBadCases(),
      ]);
      if (requestRef.current !== request) return;
      setReport(nextReport);
      setInbox(nextInbox);
    } catch (cause) {
      if (requestRef.current !== request) return;
      setReport(null);
      setInbox(null);
      setError(cause instanceof Error ? cause.message : t("general.unknownError"));
    } finally {
      if (requestRef.current === request) setLoading(false);
    }
  }, [live, t]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (live) void load();
    }, 0);
    return () => {
      window.clearTimeout(timer);
      requestRef.current += 1;
    };
  }, [live, load]);

  if (!live) {
    return (
      <section className="eval-center eval-empty">
        <FlaskConical size={25} />
        <h1>{t("eval.title")}</h1>
        <p>{t("eval.liveOnly")}</p>
      </section>
    );
  }

  return (
    <div className="eval-center" aria-label={t("eval.region")}>
      <section className="eval-hero">
        <div className="eval-hero-copy">
          <span>{t("eval.eyebrow")}</span>
          <h1>{t("eval.title")}</h1>
          <p>{t("eval.body")}</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => void load()} disabled={loading}>
          {loading ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />}
          {t("eval.refresh")}
        </button>
      </section>

      {error && (
        <div className="inline-error" role="alert">
          <AlertCircle size={17} />
          <div><strong>{t("eval.loadFailed")}</strong><span>{error}</span></div>
        </div>
      )}
      {loading && !report && (
        <div className="eval-loading" role="status"><LoaderCircle className="spin" size={18} />{t("eval.loading")}</div>
      )}

      {report && inbox && (
        <>
          <section className={`eval-gate ${report.releaseGatePassed ? "passed" : "failed"}`}>
            <span className="eval-gate-icon">
              {report.releaseGatePassed ? <ShieldCheck size={23} /> : <AlertCircle size={23} />}
            </span>
            <div>
              <span>{t("eval.releaseGate")}</span>
              <h2>{report.releaseGatePassed ? t("eval.gatePassed") : t("eval.gateFailed")}</h2>
              <p>{t("eval.totalCases", { count: report.totalCases })}</p>
            </div>
            <dl>
              <div><dt>{t("eval.passed")}</dt><dd>{report.passed}</dd></div>
              <div><dt>{t("eval.failed")}</dt><dd>{report.failed}</dd></div>
              <div><dt>{t("eval.skipped")}</dt><dd>{report.skipped}</dd></div>
            </dl>
          </section>

          <div className="eval-suite-grid">
            <SuiteCard suite={report.sourceToEvidence} t={t} />
            <SuiteCard suite={report.evidenceToClaim} t={t} />
          </div>

          <section className="bad-case-center" aria-label={t("eval.badCases")}>
            <header>
              <div>
                <span><Bug size={13} />{t("eval.badCaseInbox")}</span>
                <h2>{t("eval.badCases")}</h2>
                <p>{t("eval.badCaseBody")}</p>
              </div>
              <dl>
                <div><dt>{t("eval.total")}</dt><dd>{inbox.total}</dd></div>
                <div><dt>{t("eval.unresolved")}</dt><dd>{inbox.unresolved}</dd></div>
              </dl>
            </header>
            {inbox.items.length === 0 ? (
              <p className="section-empty">{t("eval.noBadCases")}</p>
            ) : (
              <div className="bad-case-list">
                {inbox.items.map((item) => (
                  <article className={`bad-case-card severity-${item.severity}`} key={item.id}>
                    <header>
                      <div><span>{item.stage}</span><h3>{item.id}</h3></div>
                      <span className="bad-case-severity">{item.severity}</span>
                    </header>
                    <p>{item.symptom}</p>
                    <dl>
                      <div><dt>{t("eval.fixture")}</dt><dd><code>{item.fixture}</code></dd></div>
                      <div><dt>{t("eval.safeError")}</dt><dd><code>{item.safeErrorCode}</code></dd></div>
                      <div><dt>{t("eval.rootCause")}</dt><dd>{item.rootCause}</dd></div>
                      <div><dt>{t("eval.resolution")}</dt><dd>{item.resolution}</dd></div>
                      <div><dt>{t("eval.regressionTest")}</dt><dd><code>{item.regressionTest}</code></dd></div>
                    </dl>
                    <div className={`bad-case-recovery ${item.recoveryVerified ? "verified" : "unresolved"}`}>
                      {item.recoveryVerified ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
                      {item.recoveryVerified ? t("eval.recoveryVerified") : t("eval.recoveryPending")}
                      {item.dataLoss && <strong>{t("eval.dataLoss")}</strong>}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
