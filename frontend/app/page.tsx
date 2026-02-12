import AnalyticsDeck from '@/components/AnalyticsDeck';
import ErrorState from '@/components/ErrorState';
import FiltersBar from '@/components/FiltersBar';
import HintLabel from '@/components/HintLabel';
import PullControlPanel from '@/components/PullControlPanel';
import QualityPanel from '@/components/QualityPanel';
import TickerTable from '@/components/TickerTable';
import { apiGet, readableApiError } from '@/lib/api';
import { formatPct, formatScore } from '@/lib/format';
import type { AnalyticsResponse, PullStatusOverview, QualityResponse, ResultsResponse, SubredditsResponse } from '@/lib/types';
import Link from 'next/link';

type SearchParams = {
  analytics_days?: string;
  date?: string;
  subreddit?: string;
  window?: string;
};

function berlinTodayIsoDate(): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Europe/Berlin',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());

  const year = parts.find((p) => p.type === 'year')?.value ?? '1970';
  const month = parts.find((p) => p.type === 'month')?.value ?? '01';
  const day = parts.find((p) => p.type === 'day')?.value ?? '01';
  return `${year}-${month}-${day}`;
}

export default async function Home({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  let subreddits: SubredditsResponse;
  try {
    subreddits = await apiGet<SubredditsResponse>('/api/subreddits');
  } catch (error) {
    return (
      <main className='space-y-6 py-4'>
        <ErrorState title='Backend API Error' message={readableApiError(error)} />
      </main>
    );
  }
  let pullStatus: PullStatusOverview | null = null;
  try {
    pullStatus = await apiGet<PullStatusOverview>('/api/pull/status');
  } catch {
    pullStatus = null;
  }

  const selectedDate = params.date || berlinTodayIsoDate();
  const selectedResultsWindow: '24h' | '7d' = (params.window || '').toLowerCase() === '7d' ? '7d' : '24h';
  const parsedAnalyticsDays = Number.parseInt(params.analytics_days || '21', 10);
  const analyticsDays =
    Number.isFinite(parsedAnalyticsDays) && parsedAnalyticsDays >= 7 && parsedAnalyticsDays <= 120
      ? parsedAnalyticsDays
      : 21;
  const requestedSubreddit = (params.subreddit || '').trim();
  const selectedSubreddit =
    !requestedSubreddit || requestedSubreddit.toUpperCase() === 'ALL'
      ? 'ALL'
      : (subreddits.subreddits.find((s) => s.toLowerCase() === requestedSubreddit.toLowerCase()) ?? 'ALL');

  if (!selectedSubreddit) {
    return (
      <main className='space-y-6 py-4'>
        <section className='error-state'>
          No configured subreddits found in backend settings.
        </section>
      </main>
    );
  }

  let results24: ResultsResponse;
  let results7: ResultsResponse;
  let results: ResultsResponse;
  try {
    const subredditParam =
      selectedSubreddit === 'ALL' ? '' : `&subreddit=${encodeURIComponent(selectedSubreddit)}`;
    [results24, results7] = await Promise.all([
      apiGet<ResultsResponse>(`/api/results?date=${encodeURIComponent(selectedDate)}&window=24h${subredditParam}`),
      apiGet<ResultsResponse>(`/api/results?date=${encodeURIComponent(selectedDate)}&window=7d${subredditParam}`),
    ]);
    results = selectedResultsWindow === '7d' ? results7 : results24;
  } catch (error) {
    return (
      <main className='space-y-6 py-4'>
        <FiltersBar
          subreddits={subreddits.subreddits}
          selectedSubreddit={selectedSubreddit}
          selectedDate={selectedDate}
          selectedResultsWindow={selectedResultsWindow}
          selectedAnalyticsDays={analyticsDays}
        />
        <ErrorState title='Results Unavailable' message={readableApiError(error)} />
      </main>
    );
  }
  let quality: QualityResponse | null = null;
  try {
    const subredditParam =
      selectedSubreddit === 'ALL' ? '' : `&subreddit=${encodeURIComponent(selectedSubreddit)}`;
    quality = await apiGet<QualityResponse>(`/api/quality?date=${encodeURIComponent(selectedDate)}${subredditParam}`);
  } catch {
    quality = null;
  }
  let analytics: AnalyticsResponse | null = null;
  try {
    const subredditParam =
      selectedSubreddit === 'ALL' ? '' : `&subreddit=${encodeURIComponent(selectedSubreddit)}`;
    analytics = await apiGet<AnalyticsResponse>(
      `/api/analytics?days=${analyticsDays}&date=${encodeURIComponent(selectedDate)}${subredditParam}`,
    );
  } catch {
    analytics = null;
  }
  const totalMentions = results.rows.reduce((sum, row) => sum + row.mention_count, 0);
  const mentions24 = results24.rows.reduce((sum, row) => sum + row.mention_count, 0);
  const mentions7 = results7.rows.reduce((sum, row) => sum + row.mention_count, 0);
  const windowDeltaMentions = mentions7 - mentions24;
  const hasAnyWindowData = mentions24 > 0 || mentions7 > 0;
  const windowAddsData = windowDeltaMentions > 0;
  const showNoExtraDataFlag = hasAnyWindowData && !windowAddsData;
  const weightedScore =
    totalMentions > 0
      ? results.rows.reduce((sum, row) => sum + row.score_weighted * row.mention_count, 0) / totalMentions
      : 0;
  const overallUnclearRate =
    totalMentions > 0
      ? results.rows.reduce((sum, row) => sum + row.unclear_rate * row.mention_count, 0) / totalMentions
      : 0;
  const loudestTicker = results.rows[0]?.ticker ?? 'N/A';
  const strongestDirectional = [...results.rows]
    .sort((a, b) => Math.abs(b.score_weighted) - Math.abs(a.score_weighted))
    .at(0);
  const hasLegacyAggregationFields = results.rows.some(
    (row) => !Number.isFinite(row.valid_count) || !Number.isFinite(row.ci95_low_unweighted) || !Number.isFinite(row.ci95_high_unweighted),
  );
  const scoreBiasLabel = weightedScore > 0.15 ? 'risk-on' : weightedScore < -0.15 ? 'risk-off' : 'balanced';
  const scoreBarPct = Math.min(Math.max(((weightedScore + 1) / 2) * 100, 0), 100);
  const scopeLabel = selectedSubreddit === 'ALL' ? 'all configured subreddits' : `r/${selectedSubreddit}`;
  const selectedSubredditWithoutSuccess =
    selectedSubreddit !== 'ALL'
      ? (pullStatus?.subreddits_without_success.includes(selectedSubreddit) ?? false)
      : false;
  const highUnclearWarning = quality ? quality.unclear_rate >= 0.35 : false;

  return (
    <main className='space-y-5'>
      <section className='panel fade-up'>
        <div className='grid gap-6 lg:grid-cols-[1.3fr_0.7fr]'>
          <div>
            <p className='eyebrow'>Market Pulse</p>
            <h1 className='display mt-2 text-3xl font-bold text-slate-900 sm:text-4xl'>
              {scopeLabel} market tone
            </h1>
            <p className='mt-3 max-w-2xl text-sm leading-relaxed text-slate-600 sm:text-base'>
              Live snapshot from ticker mentions, stance probabilities, and interaction-weighted aggregation for the
              selected time window.
            </p>

            <div className='mt-5 grid gap-3 sm:grid-cols-3'>
              <article className='metric-card'>
                <p className='eyebrow'>
                  <HintLabel label='Mentions' hint='Anzahl aller erkannten Ticker-Mentions (inklusive UNCLEAR).' />
                </p>
                <p className='display mt-1 text-3xl font-bold text-slate-900'>{totalMentions}</p>
              </article>
              <article className='metric-card'>
                <p className='eyebrow'>
                  <HintLabel label='Weighted Mood' hint='Gesamt-Score, gewichtet nach Interaktion und Decays.' />
                </p>
                <p className='display mt-1 text-3xl font-bold text-slate-900'>{formatScore(weightedScore)}</p>
              </article>
              <article className='metric-card'>
                <p className='eyebrow'>
                  <HintLabel label='Unclear Share' hint='Anteil der Mentions, die als UNCLEAR klassifiziert wurden.' />
                </p>
                <p className='display mt-1 text-3xl font-bold text-slate-900'>{formatPct(overallUnclearRate)}</p>
              </article>
            </div>
          </div>

          <aside className='metric-card space-y-4'>
            <p className='eyebrow'>Quick Read</p>
            <div className='space-y-2 text-sm text-slate-700'>
              <p>
                Time window:{' '}
                <span className='font-semibold'>{results.window === '7d' ? 'Last 7 days' : 'Last 24h'}</span>
              </p>
              <p>
                Date range: <span className='font-semibold'>{results.date_from} to {results.date_to}</span>
              </p>
              <p>
                Highest volume ticker: <span className='font-semibold'>{loudestTicker}</span>
              </p>
              <p>
                Strongest directional move:{' '}
                <span className='font-semibold'>
                  {strongestDirectional ? `${strongestDirectional.ticker} (${formatScore(strongestDirectional.score_weighted)})` : 'N/A'}
                </span>
              </p>
              <p>
                Regime: <span className='font-semibold'>{scoreBiasLabel}</span>
              </p>
            </div>

            <div className='pt-2'>
              <p className='mb-2 text-xs font-semibold uppercase tracking-[0.1em] text-slate-500'>Mood Scale</p>
              <div className='h-1.5 rounded-full bg-slate-200'>
                <div
                  className='h-1.5 rounded-full bg-gradient-to-r from-rose-500 via-slate-400 to-emerald-500'
                  style={{ width: `${scoreBarPct}%` }}
                />
              </div>
            </div>
          </aside>
        </div>
      </section>

      <PullControlPanel
        subreddits={subreddits.subreddits}
        selectedSubreddit={selectedSubreddit}
        initialOverview={pullStatus}
      />

      <FiltersBar
        subreddits={subreddits.subreddits}
        selectedSubreddit={selectedSubreddit}
        selectedDate={selectedDate}
        selectedResultsWindow={selectedResultsWindow}
        selectedAnalyticsDays={analyticsDays}
      />

      <section className='line-section fade-up flex flex-wrap items-center gap-2 pb-3 text-xs text-slate-600'>
        {hasAnyWindowData ? (
          <>
            <span className='score-pill score-pill-neutral'>24h mentions: {mentions24}</span>
            <span className='score-pill score-pill-neutral'>| 7d mentions: {mentions7}</span>
            <span className='score-pill score-pill-neutral'>
              | 7d delta: {windowDeltaMentions >= 0 ? `+${windowDeltaMentions}` : windowDeltaMentions}
            </span>
            {showNoExtraDataFlag ? (
              <span
                className='score-pill score-pill-negative'
                title='Wenn 7d nicht mehr liefert, gibt es fuer diesen Filter aktuell kaum/keine aelteren Inhalte im Datensatz. Erhoehe Pull-Historie (z.B. PULL_T_PARAM=week, hoehere PULL_LIMIT, regelmaessige Pulls).'
              >
                7d adds no extra data
              </span>
            ) : null}
          </>
        ) : (
          <>
            <span className='score-pill score-pill-negative'>No data for current filter yet</span>
            {selectedSubreddit !== 'ALL' ? (
              <span className='score-pill score-pill-neutral'>Try pulling r/{selectedSubreddit}</span>
            ) : null}
            {selectedSubredditWithoutSuccess ? (
              <span className='score-pill score-pill-neutral'>
                No successful pull recorded yet for r/{selectedSubreddit}
              </span>
            ) : null}
          </>
        )}
      </section>

      {quality ? <QualityPanel quality={quality} /> : null}
      {quality && highUnclearWarning ? (
        <section className='error-state fade-up text-sm text-slate-700'>
          UNCLEAR ist aktuell hoch ({formatPct(quality.unclear_rate)}).
          <span className='ml-1'>
            Kontext-Mentions liegen bei {formatPct(quality.context_mention_rate)} und koennen die UNCLEAR-Rate stark
            erhoehen.
          </span>
        </section>
      ) : null}
      {analytics ? <AnalyticsDeck analytics={analytics} /> : null}

      {hasLegacyAggregationFields ? (
        <section className='error-state fade-up text-sm text-slate-700'>
          Einige Zeilen stammen aus Legacy-Aggregationen ohne exakte CI/Valid-N Felder.
          <span
            className='ml-2 underline decoration-dotted'
            title='Die UI zeigt in diesem Fall vernuenftige Fallbacks an. Fuer exakte Werte: Backend neu starten, Migrationen anwenden und die Daten fuer den Tag neu aggregieren.'
          >
            mehr Infos
          </span>
        </section>
      ) : null}

      <section className='fade-up space-y-3'>
        <div className='flex flex-wrap items-end justify-between gap-3'>
          <div>
            <h2 className='display text-2xl font-bold text-slate-900'>Top Tickers</h2>
            <p className='text-sm text-slate-600'>
              Sorted by mention volume and weighted stance for {scopeLabel} in the selected time window.
            </p>
          </div>
          <div className='flex flex-wrap items-center gap-2'>
            <span className='score-pill score-pill-neutral'>{results.rows.length} ticker rows</span>
            <Link href='/research' className='score-pill score-pill-neutral'>Open Research Lab</Link>
          </div>
        </div>
        <TickerTable rows={results.rows} />
      </section>
    </main>
  );
}
