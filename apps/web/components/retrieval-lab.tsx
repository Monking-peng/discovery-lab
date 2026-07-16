"use client";

import {
  AlertCircle,
  ArrowUpRight,
  Braces,
  CheckCircle2,
  DatabaseZap,
  Fingerprint,
  LoaderCircle,
  LockKeyhole,
  SearchCheck,
  ShieldCheck,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  api,
  type ContextManifest,
  type ContextManifestItem,
  type RetrievalPurpose,
} from "@/lib/api";
import type { MessageKey, TranslationVars } from "@/lib/i18n";

type Translator = (key: MessageKey, vars?: TranslationVars) => string;

type RetrievalLabProps = {
  studyId: string;
  live: boolean;
  t: Translator;
  onOpenEvidenceRevision: (
    evidenceId: string,
    evidenceRevisionId: string,
    sourceRevisionId: string,
  ) => void | Promise<void>;
};

type IdempotentAttempt = {
  fingerprint: string;
  clientRequestId: string;
};

function requestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `retrieval-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function safeMessage(error: unknown, t: Translator): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return t("general.unknownError");
}

function score(value: number): string {
  return value.toFixed(4);
}

function shortId(value: string): string {
  if (value.length <= 22) return value;
  return `${value.slice(0, 10)}…${value.slice(-8)}`;
}

function purposeLabel(purpose: RetrievalPurpose, t: Translator): string {
  return t(`retrieval.purpose.${purpose}` as MessageKey);
}

function RetrievalResult({
  item,
  t,
  replaying,
  onOpen,
}: {
  item: ContextManifestItem;
  t: Translator;
  replaying: boolean;
  onOpen: () => Promise<void>;
}) {
  return (
    <article className="retrieval-result">
      <div className="retrieval-result-head">
        <span className="retrieval-rank">#{item.rank}</span>
        <div>
          <strong>{item.sourceName}</strong>
          <span>{item.evidence.evidenceType}</span>
        </div>
        <span className="retrieval-accepted"><ShieldCheck size={11} />ACCEPT</span>
      </div>

      <blockquote>{item.evidence.quote}</blockquote>
      {item.evidence.observation && <p>{item.evidence.observation}</p>}

      <div className="retrieval-scores" aria-label={t("retrieval.scores")}>
        <span><small>{t("retrieval.bm25Score")}</small><strong>{score(item.lexicalScore)}</strong><em>r{item.lexicalRank}</em></span>
        <span><small>{t("retrieval.hashScore")}</small><strong>{score(item.vectorScore)}</strong><em>r{item.vectorRank}</em></span>
        <span><small>{t("retrieval.rrfScore")}</small><strong>{score(item.hybridScore)}</strong><em>#{item.rank}</em></span>
      </div>

      <dl className="retrieval-lineage">
        <div><dt>{t("retrieval.evidenceRevision")}</dt><dd><code title={item.evidenceRevisionId}>{shortId(item.evidenceRevisionId)}</code></dd></div>
        <div><dt>{t("retrieval.sourceRevision")}</dt><dd><code title={item.sourceRevisionId}>{shortId(item.sourceRevisionId)}</code></dd></div>
        <div><dt>{t("retrieval.reviewRevision")}</dt><dd><code title={item.evidenceReviewId}>{shortId(item.evidenceReviewId)}</code></dd></div>
      </dl>

      <div className="retrieval-result-foot">
        <span>{t("retrieval.reviewedBy", { reviewer: item.review.reviewer })}</span>
        <button
          type="button"
          className="text-button"
          disabled={replaying}
          onClick={() => void onOpen()}
        >
          {replaying ? <LoaderCircle className="spin" size={12} /> : <ArrowUpRight size={12} />}
          {replaying ? t("retrieval.replaying") : t("retrieval.openExact")}
        </button>
      </div>
    </article>
  );
}

export function RetrievalLab({ studyId, live, t, onOpenEvidenceRevision }: RetrievalLabProps) {
  const [query, setQuery] = useState("");
  const [purpose, setPurpose] = useState<RetrievalPurpose>("explore");
  const [limitInput, setLimitInput] = useState("10");
  const [manifest, setManifest] = useState<ContextManifest | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [replayingItemId, setReplayingItemId] = useState<string | null>(null);
  const requestSerialRef = useRef(0);
  const studyRef = useRef(studyId);
  const attemptRef = useRef<IdempotentAttempt | null>(null);
  const parsedLimit = Number(limitInput);
  const limitIsValid = Number.isInteger(parsedLimit) && parsedLimit >= 1 && parsedLimit <= 50;

  useEffect(() => {
    studyRef.current = studyId;
    requestSerialRef.current += 1;
    attemptRef.current = null;
  }, [studyId]);

  useEffect(() => () => {
    requestSerialRef.current += 1;
  }, []);

  const visibleManifest = manifest?.studyId === studyId ? manifest : null;
  const purposeOptions = useMemo<RetrievalPurpose[]>(
    () => ["support", "counterevidence", "explore"],
    [],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!live || submitting || !query.trim() || !limitIsValid) return;

    const capturedStudyId = studyId;
    const fingerprint = JSON.stringify({
      studyId: capturedStudyId,
      query,
      purpose,
      limit: parsedLimit,
    });
    const previousAttempt = attemptRef.current;
    const clientRequestId = previousAttempt?.fingerprint === fingerprint
      ? previousAttempt.clientRequestId
      : requestId();
    attemptRef.current = { fingerprint, clientRequestId };

    const serial = ++requestSerialRef.current;
    setSubmitting(true);
    setError("");
    try {
      const nextManifest = await api.createContextManifest(capturedStudyId, {
        query,
        purpose,
        limit: parsedLimit,
        clientRequestId,
      });
      if (requestSerialRef.current !== serial || studyRef.current !== capturedStudyId) return;
      setManifest(nextManifest);
      attemptRef.current = null;
    } catch (nextError) {
      if (requestSerialRef.current === serial && studyRef.current === capturedStudyId) {
        setError(safeMessage(nextError, t));
      }
    } finally {
      if (requestSerialRef.current === serial && studyRef.current === capturedStudyId) {
        setSubmitting(false);
      }
    }
  }

  async function openExact(item: ContextManifestItem) {
    if (replayingItemId) return;
    setReplayingItemId(item.id);
    setError("");
    try {
      await onOpenEvidenceRevision(
        item.evidenceId,
        item.evidenceRevisionId,
        item.sourceRevisionId,
      );
    } catch (nextError) {
      setError(safeMessage(nextError, t));
    } finally {
      setReplayingItemId(null);
    }
  }

  return (
    <section className="retrieval-lab" aria-labelledby="retrieval-lab-title">
      <div className="retrieval-lab-heading">
        <div className="retrieval-lab-icon"><DatabaseZap size={16} /></div>
        <div>
          <span>{t("retrieval.eyebrow")}</span>
          <h3 id="retrieval-lab-title">{t("retrieval.title")}</h3>
          <p>{t("retrieval.body")}</p>
        </div>
        <span className="retrieval-live-badge"><LockKeyhole size={10} />{t("retrieval.immutable")}</span>
      </div>

      <form className="retrieval-form" onSubmit={(event) => void submit(event)}>
        <label className="retrieval-query">
          <span>{t("retrieval.query")}</span>
          <textarea
            rows={2}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("retrieval.queryPlaceholder")}
            disabled={!live || submitting}
            required
          />
        </label>
        <label>
          <span>{t("retrieval.purpose")}</span>
          <select
            value={purpose}
            onChange={(event) => setPurpose(event.target.value as RetrievalPurpose)}
            disabled={!live || submitting}
          >
            {purposeOptions.map((item) => (
              <option value={item} key={item}>{purposeLabel(item, t)}</option>
            ))}
          </select>
        </label>
        <label>
          <span>{t("retrieval.limit")}</span>
          <input
            type="number"
            min={1}
            max={50}
            value={limitInput}
            onChange={(event) => setLimitInput(event.target.value)}
            onBlur={() => {
              if (limitIsValid) setLimitInput(String(parsedLimit));
            }}
            disabled={!live || submitting}
          />
        </label>
        <button
          className="primary-button retrieval-submit"
          disabled={!live || submitting || !query.trim() || !limitIsValid}
        >
          {submitting ? <LoaderCircle className="spin" size={13} /> : <SearchCheck size={13} />}
          {submitting ? t("retrieval.running") : t("retrieval.run")}
        </button>
      </form>

      {!live && (
        <div className="retrieval-live-only"><AlertCircle size={13} />{t("retrieval.liveOnly")}</div>
      )}
      {error && (
        <div className="inline-error compact" role="alert">
          <AlertCircle size={14} />
          <div><strong>{t("retrieval.failed")}</strong><span>{error}</span></div>
        </div>
      )}

      {visibleManifest && (
        <div className="retrieval-manifest" aria-label={t("retrieval.manifest")}>
          <div className="retrieval-manifest-head">
            <div>
              <CheckCircle2 size={14} />
              <span>{t("retrieval.manifest")}</span>
              <code title={visibleManifest.contextManifestId}>{shortId(visibleManifest.contextManifestId)}</code>
            </div>
            <span>{t("retrieval.resultCount", { count: visibleManifest.items.length })}</span>
          </div>

          <div className="retrieval-query-data">
            <div><Braces size={12} /><span>{t("retrieval.queryData")}</span><em>{visibleManifest.queryHandling}</em></div>
            <pre>{visibleManifest.query}</pre>
          </div>

          <div className="retrieval-profile">
            <div><span>{t("retrieval.profile")}</span><strong>{visibleManifest.profileName} · v{visibleManifest.profileVersion}</strong></div>
            <div><span>BM25</span><code>{visibleManifest.lexicalAlgorithm}</code></div>
            <div><span>{t("retrieval.hashVector")}</span><code>{visibleManifest.vectorAlgorithm}</code></div>
            <div><span>RRF</span><code>{visibleManifest.fusionAlgorithm}</code></div>
          </div>
          <div className="retrieval-vector-note">
            <Fingerprint size={14} />
            <div><strong>{t("retrieval.hashDisclaimer")}</strong><span>{visibleManifest.vectorAlgorithmDescription}</span></div>
          </div>

          <div className="retrieval-results">
            {visibleManifest.items.map((item) => (
              <RetrievalResult
                key={item.id}
                item={item}
                t={t}
                replaying={replayingItemId === item.id}
                onOpen={() => openExact(item)}
              />
            ))}
            {visibleManifest.items.length === 0 && (
              <div className="retrieval-empty"><SearchCheck size={17} /><span>{t("retrieval.empty")}</span></div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
