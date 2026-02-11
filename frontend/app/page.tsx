import ErrorState from '@/components/ErrorState';
import FiltersBar from '@/components/FiltersBar';
import TickerTable from '@/components/TickerTable';
import { apiGet, readableApiError } from '@/lib/api';
import { formatPct, formatScore } from '@/lib/format';
import type { ResultsResponse, SubredditsResponse } from '@/lib/types';

type SearchParams = {
  date?: string;
  subreddit?: string;
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

  const selectedDate = params.date || berlinTodayIsoDate();
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

  let results: ResultsResponse;
  try {
    const subredditParam =
      selectedSubreddit === 'ALL' ? '' : `&subreddit=${encodeURIComponent(selectedSubreddit)}`;
    results = await apiGet<ResultsResponse>(`/api/results?date=${encodeURIComponent(selectedDate)}${subredditParam}`);
  } catch (error) {
    return (
      <main className='space-y-6 py-4'>
        <FiltersBar
          subreddits={subreddits.subreddits}
          selectedSubreddit={selectedSubreddit}
          selectedDate={selectedDate}
        />
        <ErrorState title='Results Unavailable' message={readableApiError(error)} />
      </main>
    );
  }
  const totalMentions = results.rows.reduce((sum, row) => sum + row.mention_count, 0);
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
  const scoreBiasLabel = weightedScore > 0.15 ? 'risk-on' : weightedScore < -0.15 ? 'risk-off' : 'balanced';
  const scoreBarPct = Math.min(Math.max(((weightedScore + 1) / 2) * 100, 0), 100);
  const scopeLabel = selectedSubreddit === 'ALL' ? 'all configured subreddits' : `r/${selectedSubreddit}`;

  return (
    <main className='space-y-5'>
      <section className='panel fade-up'>
        <div className='grid gap-6 lg:grid-cols-[1.3fr_0.7fr]'>
          <div>
            <p className='eyebrow'>Daily Pulse</p>
            <h1 className='display mt-2 text-3xl font-bold text-slate-900 sm:text-4xl'>
              {scopeLabel} market tone
            </h1>
            <p className='mt-3 max-w-2xl text-sm leading-relaxed text-slate-600 sm:text-base'>
              Live snapshot from ticker mentions, stance probabilities, and interaction-weighted aggregation for the
              selected Berlin calendar day.
            </p>

            <div className='mt-5 grid gap-3 sm:grid-cols-3'>
              <article className='metric-card'>
                <p className='eyebrow'>Mentions</p>
                <p className='display mt-1 text-3xl font-bold text-slate-900'>{totalMentions}</p>
              </article>
              <article className='metric-card'>
                <p className='eyebrow'>Weighted Mood</p>
                <p className='display mt-1 text-3xl font-bold text-slate-900'>{formatScore(weightedScore)}</p>
              </article>
              <article className='metric-card'>
                <p className='eyebrow'>Unclear Share</p>
                <p className='display mt-1 text-3xl font-bold text-slate-900'>{formatPct(overallUnclearRate)}</p>
              </article>
            </div>
          </div>

          <aside className='metric-card space-y-4'>
            <p className='eyebrow'>Quick Read</p>
            <div className='space-y-2 text-sm text-slate-700'>
              <p>
                Date bucket: <span className='font-semibold'>{results.date_bucket_berlin}</span>
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

      <FiltersBar
        subreddits={subreddits.subreddits}
        selectedSubreddit={selectedSubreddit}
        selectedDate={selectedDate}
      />

      <section className='fade-up space-y-3'>
        <div className='flex flex-wrap items-end justify-between gap-3'>
          <div>
            <h2 className='display text-2xl font-bold text-slate-900'>Top Tickers</h2>
            <p className='text-sm text-slate-600'>
              Sorted by mention volume and weighted stance for {scopeLabel}.
            </p>
          </div>
          <span className='score-pill score-pill-neutral'>{results.rows.length} ticker rows</span>
        </div>
        <TickerTable rows={results.rows} />
      </section>
    </main>
  );
}
