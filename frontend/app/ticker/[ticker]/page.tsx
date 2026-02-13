import Link from 'next/link';

import ErrorState from '@/components/ErrorState';
import HintLabel from '@/components/HintLabel';
import ScoreChart from '@/components/ScoreChart';
import VolumeChart from '@/components/VolumeChart';
import { apiGet, readableApiError } from '@/lib/api';
import { formatPct, formatScore } from '@/lib/format';
import type { TickerPriceResponse, TickerSeriesResponse } from '@/lib/types';

type SearchParams = {
  days?: string;
  subreddit?: string;
};

export default async function TickerPage({
  params,
  searchParams,
}: {
  params: Promise<{ ticker: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { ticker } = await params;
  const qp = await searchParams;

  const parsedDays = Number.parseInt(qp.days ?? '30', 10);
  const days = Number.isFinite(parsedDays) && parsedDays >= 1 && parsedDays <= 365 ? parsedDays : 30;
  const subreddit = qp.subreddit || '';

  const tickerCode = ticker.toUpperCase();
  const seriesPath = `/api/ticker/${encodeURIComponent(tickerCode)}?days=${days}${
    subreddit ? `&subreddit=${encodeURIComponent(subreddit)}` : ''
  }`;
  const pricePath = `/api/ticker/${encodeURIComponent(tickerCode)}/price?days=${days}&interval=1d`;

  const [seriesResult, priceResult] = await Promise.allSettled([
    apiGet<TickerSeriesResponse>(seriesPath),
    apiGet<TickerPriceResponse>(pricePath),
  ]);

  if (seriesResult.status === 'rejected') {
    return (
      <main className='space-y-6 py-4'>
        <section className='line-section'>
          <Link href={subreddit ? `/?subreddit=${encodeURIComponent(subreddit)}` : '/'} className='text-link'>
            back to dashboard
          </Link>
        </section>
        <ErrorState title='Ticker Data Unavailable' message={readableApiError(seriesResult.reason)} />
      </main>
    );
  }

  const data = seriesResult.value;
  const priceSeries = priceResult.status === 'fulfilled' ? priceResult.value.series : [];
  const priceFetchError = priceResult.status === 'rejected' ? readableApiError(priceResult.reason) : null;

  const dayOptions = [7, 14, 30, 90];
  const latestPoint = data.series.at(-1);
  const maxMentions = data.series.length ? Math.max(...data.series.map((p) => p.mention_count)) : 0;
  const avgUnclearRate = data.series.length
    ? data.series.reduce((sum, p) => sum + p.unclear_rate, 0) / data.series.length
    : 0;

  const makeDayHref = (option: number) =>
    `/ticker/${data.ticker}?days=${option}${subreddit ? `&subreddit=${encodeURIComponent(subreddit)}` : ''}`;

  return (
    <main className='space-y-5'>
      <section className='panel fade-up p-5 sm:p-6'>
        <div className='flex flex-wrap items-center justify-between gap-2'>
          <Link
            href={subreddit ? `/?subreddit=${encodeURIComponent(subreddit)}` : '/'}
            className='score-pill score-pill-neutral'
          >
            back to dashboard
          </Link>
          <span className='score-pill score-pill-neutral'>{data.series.length} data points</span>
        </div>

        <h1 className='display mt-4 text-3xl font-bold text-slate-900 sm:text-4xl'>Ticker {data.ticker}</h1>
        <p className='mt-2 text-sm text-slate-600 sm:text-base'>
          Trend window: {data.days} days{subreddit ? ` in r/${subreddit}` : ' across all configured subreddits'}.
        </p>

        <div className='mt-4 flex flex-wrap gap-2'>
          {dayOptions.map((option) => (
            <Link
              key={option}
              href={makeDayHref(option)}
              className={option === data.days ? 'score-pill score-pill-positive' : 'score-pill score-pill-neutral'}
            >
              {option}d
            </Link>
          ))}
        </div>

        <div className='mt-5 grid gap-3 sm:grid-cols-3'>
          <article className='metric-card'>
            <p className='eyebrow'>
              <HintLabel label='Latest Score' hint='Aktueller gewichteter Stance-Score im gewaehlten Zeitfenster.' />
            </p>
            <p className='display mt-1 text-3xl font-bold text-slate-900'>
              {latestPoint ? formatScore(latestPoint.score_weighted) : '0.000'}
            </p>
          </article>
          <article className='metric-card'>
            <p className='eyebrow'>
              <HintLabel label='Avg Unclear' hint='Mittlere UNCLEAR-Rate ueber alle gezeigten Buckets.' />
            </p>
            <p className='display mt-1 text-3xl font-bold text-slate-900'>{formatPct(avgUnclearRate)}</p>
          </article>
          <article className='metric-card'>
            <p className='eyebrow'>
              <HintLabel label='Peak Mentions' hint='Hoechste Mention-Anzahl in einem einzelnen Zeitbucket.' />
            </p>
            <p className='display mt-1 text-3xl font-bold text-slate-900'>{maxMentions}</p>
          </article>
        </div>
      </section>

      <div className='grid gap-4 lg:grid-cols-2'>
        <ScoreChart points={data.series} pricePoints={priceSeries} priceFetchError={priceFetchError} />
        <VolumeChart points={data.series} />
      </div>

      <section className='grid gap-4 xl:grid-cols-2'>
        <div className='panel p-4 sm:p-5'>
          <h2 className='display mb-3 text-xl font-semibold text-slate-900'>
            <HintLabel label='Bullish Examples' hint='Beispielkommentare, die fuer diesen Ticker bullish klassifiziert wurden.' />
          </h2>
          <div className='space-y-3'>
            {data.bullish_examples.map((ex, idx) => (
              <article key={`${ex.id}-${idx}`} className='metric-card space-y-2'>
                <p className='text-sm text-slate-800'>{ex.body}</p>
                <div className='flex flex-wrap gap-2 text-xs'>
                  <span className='score-pill score-pill-neutral'>score {ex.score}</span>
                  <span className='score-pill score-pill-positive'>stance {formatScore(ex.stance_score)}</span>
                  <Link href={`/thread/${ex.submission_id}`} className='score-pill score-pill-neutral'>
                    Thread drilldown
                  </Link>
                </div>
              </article>
            ))}
            {!data.bullish_examples.length ? <p className='text-sm text-slate-500'>No bullish examples yet.</p> : null}
          </div>
        </div>

        <div className='panel p-4 sm:p-5'>
          <h2 className='display mb-3 text-xl font-semibold text-slate-900'>
            <HintLabel label='Bearish Examples' hint='Beispielkommentare, die fuer diesen Ticker bearish klassifiziert wurden.' />
          </h2>
          <div className='space-y-3'>
            {data.bearish_examples.map((ex, idx) => (
              <article key={`${ex.id}-${idx}`} className='metric-card space-y-2'>
                <p className='text-sm text-slate-800'>{ex.body}</p>
                <div className='flex flex-wrap gap-2 text-xs'>
                  <span className='score-pill score-pill-neutral'>score {ex.score}</span>
                  <span className='score-pill score-pill-negative'>stance {formatScore(ex.stance_score)}</span>
                  <Link href={`/thread/${ex.submission_id}`} className='score-pill score-pill-neutral'>
                    Thread drilldown
                  </Link>
                </div>
              </article>
            ))}
            {!data.bearish_examples.length ? <p className='text-sm text-slate-500'>No bearish examples yet.</p> : null}
          </div>
        </div>
      </section>
    </main>
  );
}
