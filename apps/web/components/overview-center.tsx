"use client";

import {
  ArrowRight,
  BookOpenCheck,
  CheckCircle2,
  FileCheck2,
  FlaskConical,
  GitBranch,
  Layers3,
  PlayCircle,
  Route,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";

import type { Study } from "@/lib/api";
import type { MessageKey, TranslationVars } from "@/lib/i18n";

type OverviewTarget = "evidence" | "claims" | "runs" | "eval" | "product";
type Translator = (key: MessageKey, vars?: TranslationVars) => string;

type OverviewCenterProps = {
  live: boolean;
  study: Study | null;
  t: Translator;
  onNavigate: (target: OverviewTarget) => void;
};

const workflowSteps: ReadonlyArray<{
  target: OverviewTarget;
  icon: typeof BookOpenCheck;
  title: MessageKey;
  body: MessageKey;
  action: MessageKey;
}> = [
  { target: "evidence", icon: BookOpenCheck, title: "overview.step1.title", body: "overview.step1.body", action: "overview.step1.action" },
  { target: "claims", icon: GitBranch, title: "overview.step2.title", body: "overview.step2.body", action: "overview.step2.action" },
  { target: "runs", icon: Workflow, title: "overview.step3.title", body: "overview.step3.body", action: "overview.step3.action" },
  { target: "eval", icon: FlaskConical, title: "overview.step4.title", body: "overview.step4.body", action: "overview.step4.action" },
  { target: "product", icon: FileCheck2, title: "overview.step5.title", body: "overview.step5.body", action: "overview.step5.action" },
];

const capabilities: ReadonlyArray<{
  icon: typeof Route;
  title: MessageKey;
  body: MessageKey;
}> = [
  { icon: Route, title: "overview.trace.title", body: "overview.trace.body" },
  { icon: ShieldCheck, title: "overview.agent.title", body: "overview.agent.body" },
  { icon: CheckCircle2, title: "overview.quality.title", body: "overview.quality.body" },
];

function compactStudyTitle(title: string) {
  return title.replace(/\s+\(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?\)$/, "");
}

export function OverviewCenter({ live, study, t, onNavigate }: OverviewCenterProps) {
  const studyTitle = study ? compactStudyTitle(study.title) : t("overview.noStudy");

  return (
    <section className="overview-center" aria-label={t("overview.region")}>
      <div className="overview-content">
        <header className="overview-hero">
          <div className="overview-hero-copy">
            <span className="overview-eyebrow"><Sparkles size={16} />{t("overview.eyebrow")}</span>
            <h1>{t("overview.title")}</h1>
            <p>{t("overview.body")}</p>
            <div className="overview-actions">
              <button type="button" className="overview-primary" onClick={() => onNavigate("evidence")}>
                <PlayCircle size={18} />{t("overview.primary")}<ArrowRight size={17} />
              </button>
              <button type="button" className="overview-secondary" onClick={() => onNavigate("product")}>
                <FileCheck2 size={18} />{t("overview.secondary")}
              </button>
            </div>
            <div className="overview-trust" aria-label={t("overview.trustLabel")}>
              <span><Route size={15} />{t("overview.trust.trace")}</span>
              <span><ShieldCheck size={15} />{t("overview.trust.approval")}</span>
              <span><FlaskConical size={15} />{t("overview.trust.eval")}</span>
            </div>
          </div>

          <article className="overview-study-card">
            <div className="overview-study-head">
              <div>
                <span>{t("overview.currentStudy")}</span>
                <h2 title={study?.title}>{studyTitle}</h2>
              </div>
              <span className={`overview-live-state ${live ? "live" : "preview"}`}>
                <span aria-hidden="true" />{t(live ? "overview.live" : "overview.preview")}
              </span>
            </div>
            <div className="overview-question">
              <span>{t("overview.question")}</span>
              <p>{study?.decisionQuestion ?? t("overview.noStudyQuestion")}</p>
            </div>
            <dl className="overview-study-metrics">
              <div><dt>{t("overview.sourcesLabel")}</dt><dd>{study?.sourceCount ?? 0}</dd></div>
              <div><dt>{t("overview.evidenceLabel")}</dt><dd>{study?.evidenceCount ?? 0}</dd></div>
              <div><dt>{t("overview.workflowLabel")}</dt><dd>5</dd></div>
            </dl>
            <button type="button" className="overview-study-link" onClick={() => onNavigate("evidence")}>
              {t("overview.openWorkspace")}<ArrowRight size={16} />
            </button>
          </article>
        </header>

        <section className="overview-workflow" aria-labelledby="overview-how-title">
          <div className="overview-section-heading">
            <div>
              <span>{t("overview.howEyebrow")}</span>
              <h2 id="overview-how-title">{t("overview.howTitle")}</h2>
            </div>
            <p>{t("overview.howBody")}</p>
          </div>
          <ol className="overview-step-grid">
            {workflowSteps.map((step, index) => {
              const Icon = step.icon;
              return (
                <li key={step.target} data-testid="overview-step">
                  <div className="overview-step-top">
                    <span className="overview-step-icon"><Icon size={19} /></span>
                    <span className="overview-step-number">{String(index + 1).padStart(2, "0")}</span>
                  </div>
                  <h3>{t(step.title)}</h3>
                  <p>{t(step.body)}</p>
                  <button type="button" onClick={() => onNavigate(step.target)}>
                    {t(step.action)}<ArrowRight size={15} />
                  </button>
                </li>
              );
            })}
          </ol>
        </section>

        <section className="overview-capabilities" aria-labelledby="overview-capabilities-title">
          <div className="overview-section-heading compact">
            <div>
              <span>{t("overview.capabilitiesEyebrow")}</span>
              <h2 id="overview-capabilities-title">{t("overview.capabilitiesTitle")}</h2>
            </div>
          </div>
          <div className="overview-capability-grid">
            {capabilities.map((capability) => {
              const Icon = capability.icon;
              return (
                <article key={capability.title}>
                  <span className="overview-capability-icon"><Icon size={21} /></span>
                  <div><h3>{t(capability.title)}</h3><p>{t(capability.body)}</p></div>
                </article>
              );
            })}
          </div>
          <div className="overview-architecture-note">
            <Layers3 size={18} />
            <p><strong>{t("overview.architectureTitle")}</strong>{t("overview.architectureBody")}</p>
          </div>
        </section>
      </div>
    </section>
  );
}
