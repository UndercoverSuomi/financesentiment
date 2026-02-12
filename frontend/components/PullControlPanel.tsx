'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import type { PullJobStatus, PullStatusOverview } from '@/lib/types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

type Props = {
  subreddits: string[];
  selectedSubreddit: string;
  initialOverview: PullStatusOverview | null;
};

function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'n/a';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('de-DE', {
    dateStyle: 'medium',
    timeStyle: 'short',
    hour12: false,
  });
}

function statusTone(status: string): string {
  if (status === 'success') return 'score-pill score-pill-positive';
  if (status === 'partial_success') return 'score-pill score-pill-neutral';
  if (status === 'failed') return 'score-pill score-pill-negative';
  if (status === 'running' || status === 'queued') return 'score-pill score-pill-neutral';
  return 'score-pill score-pill-neutral';
}

function progressWidth(progress: number, minPct = 2): string {
  const normalized = Math.max(Math.min(progress, 1), 0);
  if (normalized <= 0) return '0%';
  const pct = normalized * 100;
  return `${Math.max(pct, minPct)}%`;
}

function formatProgress(progress: number): string {
  const normalized = Math.max(Math.min(progress, 1), 0);
  return `${Math.round(normalized * 100)}%`;
}

function heartbeatAgeSeconds(heartbeatUtc: string | null | undefined): number | null {
  if (!heartbeatUtc) return null;
  const parsed = new Date(heartbeatUtc);
  const parsedMs = parsed.getTime();
  if (Number.isNaN(parsedMs)) return null;
  return Math.max(Math.round((Date.now() - parsedMs) / 1000), 0);
}

function heartbeatTone(ageSeconds: number | null): string {
  if (ageSeconds === null) return 'score-pill score-pill-neutral';
  if (ageSeconds <= 12) return 'score-pill score-pill-positive';
  if (ageSeconds <= 35) return 'score-pill score-pill-neutral';
  return 'score-pill score-pill-negative';
}

function heartbeatLabel(ageSeconds: number | null): string {
  if (ageSeconds === null) return 'heartbeat n/a';
  if (ageSeconds <= 12) return `heartbeat active (${ageSeconds}s ago)`;
  if (ageSeconds <= 35) return `heartbeat slow (${ageSeconds}s ago)`;
  return `heartbeat stale (${ageSeconds}s ago)`;
}

function resolvedApiBase(): string {
  if (typeof window === 'undefined') return API_BASE;
  try {
    const envUrl = new URL(API_BASE);
    const frontendHost = window.location.hostname;
    const isLoopbackFrontend = frontendHost === 'localhost' || frontendHost === '127.0.0.1';
    const isLoopbackApiHost = envUrl.hostname === 'localhost' || envUrl.hostname === '127.0.0.1';
    if (isLoopbackFrontend && isLoopbackApiHost && envUrl.hostname !== frontendHost) {
      envUrl.hostname = frontendHost;
      return envUrl.toString().replace(/\/$/, '');
    }
  } catch {
    return API_BASE;
  }
  return API_BASE;
}

async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${resolvedApiBase()}${path}`, {
    cache: 'no-store',
    ...init,
    headers: {
      ...(init?.headers || {}),
    },
  });
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && payload !== null && 'detail' in payload
        ? String((payload as { detail: unknown }).detail)
        : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}

export default function PullControlPanel({ subreddits, selectedSubreddit, initialOverview }: Props) {
  const [overview, setOverview] = useState<PullStatusOverview | null>(initialOverview);
  const [job, setJob] = useState<PullJobStatus | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refreshOverview = useCallback(async () => {
    try {
      const next = await fetchApi<PullStatusOverview>('/api/pull/status');
      setOverview(next);
    } catch {
      // Keep current overview on transient fetch errors.
    }
  }, []);

  useEffect(() => {
    if (overview) return;
    void refreshOverview();
  }, [overview, refreshOverview]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshOverview();
    }, 15000);
    return () => window.clearInterval(timer);
  }, [refreshOverview]);

  const isJobRunning = job ? ['queued', 'running'].includes(job.status) : false;
  const activeJobId = job?.job_id ?? null;

  useEffect(() => {
    if (!activeJobId || !isJobRunning) return;

    let cancelled = false;
    const poll = async () => {
      try {
        const next = await fetchApi<PullJobStatus>(`/api/pull/jobs/${encodeURIComponent(activeJobId)}`);
        if (cancelled) return;
        setJob(next);
        if (!['queued', 'running'].includes(next.status)) {
          void refreshOverview();
        }
      } catch (error) {
        if (!cancelled && error instanceof Error) {
          setActionError(error.message);
        }
      }
    };

    void poll();
    const timer = window.setInterval(() => {
      void poll();
    }, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeJobId, isJobRunning, refreshOverview]);

  const startPull = useCallback(
    async (mode: 'selected' | 'all') => {
      if (mode === 'selected' && selectedSubreddit === 'ALL') return;
      setIsStarting(true);
      setActionError(null);
      try {
        const query =
          mode === 'selected'
            ? `?subreddit=${encodeURIComponent(selectedSubreddit)}`
            : '';
        const started = await fetchApi<PullJobStatus>(`/api/pull/start${query}`, {
          method: 'POST',
        });
        setJob(started);
        void refreshOverview();
      } catch (error) {
        if (error instanceof TypeError) {
          setActionError('Backend API nicht erreichbar. Pruefe Backend-Server, Hostname (localhost/127.0.0.1) und CORS.');
        } else {
          setActionError(error instanceof Error ? error.message : 'pull start failed');
        }
      } finally {
        setIsStarting(false);
      }
    },
    [refreshOverview, selectedSubreddit],
  );

  const runningSubreddits = overview?.running_subreddits ?? [];
  const failedSubreddits = overview?.failed_subreddits ?? [];
  const missingSuccessSubreddits = overview?.subreddits_without_success ?? [];
  const selectedHasSuccess =
    selectedSubreddit === 'ALL' ? true : !missingSuccessSubreddits.includes(selectedSubreddit);
  const selectedMissingHint =
    selectedSubreddit !== 'ALL' && !selectedHasSuccess
      ? `Fuer r/${selectedSubreddit} gibt es noch keinen erfolgreichen Pull.`
      : null;

  const latestBySubreddit = useMemo(() => {
    if (!overview) return [];
    const bySub = new Map(overview.latest_by_subreddit.map((row) => [row.subreddit, row]));
    return subreddits
      .map((subreddit) => bySub.get(subreddit))
      .filter((row): row is NonNullable<typeof row> => Boolean(row));
  }, [overview, subreddits]);
  const overallProgress = Math.max(Math.min(job?.progress ?? 0, 1), 0);
  const currentSubredditProgress = Math.max(Math.min(job?.current_subreddit_progress ?? 0, 1), 0);
  const currentSubmissionTotal = job?.current_total_submissions;
  const hasCurrentTotal = typeof currentSubmissionTotal === 'number' && currentSubmissionTotal >= 0;
  const currentProcessed = Math.max(job?.current_processed_submissions ?? 0, 0);
  const heartbeatAge = heartbeatAgeSeconds(job?.heartbeat_utc);

  return (
    <section className='panel fade-up space-y-4 p-5 sm:p-6'>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <h2 className='display text-2xl font-bold text-slate-900'>Data Pull Control</h2>
        <span className='score-pill score-pill-neutral'>
          last success {formatDateTime(overview?.overall_last_success_utc)}
        </span>
      </div>

      {runningSubreddits.length ? (
        <section className='error-state text-sm text-slate-700'>
          Pull laeuft gerade fuer: {runningSubreddits.map((s) => `r/${s}`).join(', ')}.
        </section>
      ) : null}
      {failedSubreddits.length ? (
        <section className='error-state text-sm text-slate-700'>
          Letzter Pull fehlgeschlagen fuer: {failedSubreddits.map((s) => `r/${s}`).join(', ')}.
        </section>
      ) : null}
      {selectedMissingHint ? (
        <section className='error-state text-sm text-slate-700'>{selectedMissingHint}</section>
      ) : null}

      <div className='flex flex-wrap gap-2'>
        <button
          type='button'
          className='btn-main'
          disabled={isStarting || isJobRunning || selectedSubreddit === 'ALL'}
          onClick={() => void startPull('selected')}
          title={
            selectedSubreddit === 'ALL'
              ? 'Waehle erst ein einzelnes Subreddit fuer einen gezielten Pull.'
              : `Startet Pull fuer r/${selectedSubreddit}.`
          }
        >
          Pull selected subreddit
        </button>
        <button
          type='button'
          className='btn-main'
          disabled={isStarting || isJobRunning}
          onClick={() => void startPull('all')}
          title='Startet Pull fuer alle konfigurierten Subreddits.'
        >
          Pull all subreddits
        </button>
      </div>

      {actionError ? <section className='error-state text-sm text-slate-700'>{actionError}</section> : null}

      {job ? (
        <section className='line-section space-y-3'>
          <div className='flex flex-wrap items-center gap-2 text-xs'>
            <span className={statusTone(job.status)}>job {job.status}</span>
            <span className='score-pill score-pill-neutral'>
              progress {job.completed_steps}/{job.total_steps} ({formatProgress(overallProgress)})
            </span>
            {job.current_subreddit ? (
              <span className='score-pill score-pill-neutral'>current r/{job.current_subreddit}</span>
            ) : null}
            <span className={heartbeatTone(heartbeatAge)}>{heartbeatLabel(heartbeatAge)}</span>
            <span className='score-pill score-pill-neutral'>started {formatDateTime(job.started_at_utc)}</span>
            {job.finished_at_utc ? (
              <span className='score-pill score-pill-neutral'>finished {formatDateTime(job.finished_at_utc)}</span>
            ) : null}
          </div>

          <div className='space-y-1'>
            <div className='flex items-center justify-between text-[11px] text-slate-600'>
              <span>Overall job progress</span>
              <span>{formatProgress(overallProgress)}</span>
            </div>
            <div className='h-2 rounded-full bg-slate-200/75'>
              <div
                className='h-2 rounded-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all duration-300'
                style={{ width: progressWidth(overallProgress) }}
              />
            </div>
          </div>

          <div className='space-y-1'>
            <div className='flex items-center justify-between text-[11px] text-slate-600'>
              <span>Current subreddit progress</span>
              <span>
                {hasCurrentTotal
                  ? `${currentProcessed}/${Math.max(currentSubmissionTotal ?? 0, 0)} (${formatProgress(currentSubredditProgress)})`
                  : `discovering submissions (${currentProcessed} processed)`}
              </span>
            </div>
            <div className='h-2 rounded-full bg-slate-200/75'>
              {hasCurrentTotal ? (
                <div
                  className='h-2 rounded-full bg-gradient-to-r from-cyan-500 to-emerald-500 transition-all duration-300'
                  style={{ width: progressWidth(currentSubredditProgress) }}
                />
              ) : (
                <div className='h-2 w-1/3 animate-pulse rounded-full bg-gradient-to-r from-cyan-500/70 to-emerald-500/70' />
              )}
            </div>
          </div>

          <div className='flex flex-wrap gap-2 text-xs'>
            <span className='score-pill score-pill-neutral'>phase {job.current_phase ?? 'n/a'}</span>
            <span className='score-pill score-pill-neutral'>posts {job.current_submissions}</span>
            <span className='score-pill score-pill-neutral'>comments {job.current_comments}</span>
            <span className='score-pill score-pill-neutral'>mentions {job.current_mentions}</span>
            <span className='score-pill score-pill-neutral'>stances {job.current_stance_rows}</span>
            <span className='score-pill score-pill-neutral'>partial errors {job.current_partial_errors}</span>
          </div>
          {job.current_submission_id ? (
            <p className='text-xs text-slate-600'>current submission id: {job.current_submission_id}</p>
          ) : null}
          {job.error ? <p className='text-xs text-slate-600'>job note: {job.error}</p> : null}
          <div className='space-y-1 text-xs text-slate-700'>
            {job.summaries.map((row) => (
              <div key={`${row.pull_run_id}-${row.subreddit}`} className='flex flex-wrap items-center gap-2'>
                <span className={statusTone(row.status)}>
                  r/{row.subreddit} {row.status}
                </span>
                <span className='score-pill score-pill-neutral'>
                  posts {row.submissions} comments {row.comments} mentions {row.mentions}
                </span>
                {row.error ? <span className='score-pill score-pill-neutral'>{row.error}</span> : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {latestBySubreddit.length ? (
        <section className='line-section space-y-2'>
          <p className='eyebrow'>Latest pull per subreddit</p>
          <div className='grid gap-2 sm:grid-cols-2 xl:grid-cols-3'>
            {latestBySubreddit.map((row) => (
              <article key={`${row.subreddit}-${row.pulled_at_utc}`} className='metric-card space-y-1'>
                <p className='text-sm font-semibold text-slate-800'>r/{row.subreddit}</p>
                <p className='text-xs text-slate-600'>{formatDateTime(row.pulled_at_utc)}</p>
                <p><span className={statusTone(row.status)}>{row.status}</span></p>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}
