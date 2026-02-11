import Link from 'next/link';

import ErrorState from '@/components/ErrorState';
import EvaluationPanel from '@/components/EvaluationPanel';
import QualityPanel from '@/components/QualityPanel';
import { apiGet, readableApiError } from '@/lib/api';
import type { EvaluationResponse, QualityResponse, SubredditsResponse } from '@/lib/types';

type SearchParams = {
  dataset_path?: string;
  max_rows?: string;
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

export default async function ResearchPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const selectedDate = params.date || berlinTodayIsoDate();
  const datasetPath = (params.dataset_path || 'gold_labels_sample.csv').trim();
  const parsedMaxRows = Number.parseInt(params.max_rows || '5000', 10);
  const maxRows = Number.isFinite(parsedMaxRows) && parsedMaxRows > 0 ? Math.min(parsedMaxRows, 100000) : 5000;

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

  const requestedSubreddit = (params.subreddit || '').trim();
  const selectedSubreddit =
    !requestedSubreddit || requestedSubreddit.toUpperCase() === 'ALL'
      ? 'ALL'
      : (subreddits.subreddits.find((s) => s.toLowerCase() === requestedSubreddit.toLowerCase()) ?? 'ALL');

  let evaluation: EvaluationResponse;
  try {
    evaluation = await apiGet<EvaluationResponse>(
      `/api/evaluate?dataset_path=${encodeURIComponent(datasetPath)}&max_rows=${maxRows}`,
    );
  } catch (error) {
    return (
      <main className='space-y-6 py-4'>
        <section className='line-section'>
          <Link href='/' className='text-link'>back to dashboard</Link>
        </section>
        <ErrorState title='Evaluation Unavailable' message={readableApiError(error)} />
      </main>
    );
  }

  let quality: QualityResponse | null = null;
  try {
    const subredditParam = selectedSubreddit === 'ALL' ? '' : `&subreddit=${encodeURIComponent(selectedSubreddit)}`;
    quality = await apiGet<QualityResponse>(`/api/quality?date=${encodeURIComponent(selectedDate)}${subredditParam}`);
  } catch {
    quality = null;
  }

  return (
    <main className='space-y-5'>
      <section className='panel fade-up p-5 sm:p-6'>
        <div className='mb-3 flex flex-wrap items-center justify-between gap-2'>
          <Link href='/' className='score-pill score-pill-neutral'>back to dashboard</Link>
          <span className='score-pill score-pill-neutral'>Research mode</span>
        </div>
        <h1 className='display text-3xl font-bold text-slate-900 sm:text-4xl'>Scientific Evaluation Lab</h1>
        <p className='mt-2 text-sm text-slate-600'>
          Run gold-label evaluation and inspect operational data quality in one place.
        </p>

        <form method='GET' className='mt-4 grid gap-3 md:grid-cols-4 md:items-end'>
          <label className='space-y-1 text-sm'>
            <span className='eyebrow'>Dataset Path</span>
            <input type='text' name='dataset_path' defaultValue={datasetPath} className='field' />
          </label>
          <label className='space-y-1 text-sm'>
            <span className='eyebrow'>Max Rows</span>
            <input type='number' name='max_rows' min={1} max={100000} defaultValue={maxRows} className='field' />
          </label>
          <label className='space-y-1 text-sm'>
            <span className='eyebrow'>Date</span>
            <input type='date' name='date' defaultValue={selectedDate} className='field' />
          </label>
          <label className='space-y-1 text-sm'>
            <span className='eyebrow'>Subreddit</span>
            <select name='subreddit' defaultValue={selectedSubreddit} className='field'>
              <option value='ALL'>All subreddits</option>
              {subreddits.subreddits.map((s) => (
                <option key={s} value={s}>
                  r/{s}
                </option>
              ))}
            </select>
          </label>
          <div>
            <button type='submit' className='btn-main'>Run Evaluation</button>
          </div>
        </form>
      </section>

      <EvaluationPanel evaluation={evaluation} />
      {quality ? <QualityPanel quality={quality} /> : null}
    </main>
  );
}
