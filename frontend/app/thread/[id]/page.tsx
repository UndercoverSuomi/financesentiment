import Link from 'next/link';

import CommentList from '@/components/CommentList';
import ErrorState from '@/components/ErrorState';
import { apiGet, readableApiError } from '@/lib/api';
import type { ThreadResponse } from '@/lib/types';

export default async function ThreadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let data: ThreadResponse;
  try {
    data = await apiGet<ThreadResponse>(`/api/thread/${encodeURIComponent(id)}`);
  } catch (error) {
    return (
      <main className='space-y-6 py-4'>
        <section className='line-section'>
          <Link href='/' className='text-link'>
            back to dashboard
          </Link>
        </section>
        <ErrorState title='Thread Unavailable' message={readableApiError(error)} />
      </main>
    );
  }
  const submissionStanceCount = data.submission.stance.length;

  return (
    <main className='space-y-5'>
      <section className='panel fade-up p-5 sm:p-6'>
        <div className='mb-3 flex flex-wrap items-center justify-between gap-2'>
          <Link href='/' className='score-pill score-pill-neutral'>
            back to dashboard
          </Link>
          <span className='score-pill score-pill-neutral'>{submissionStanceCount} submission stance rows</span>
        </div>

        <h1 className='display text-2xl font-semibold leading-tight text-slate-900 sm:text-3xl'>{data.submission.title}</h1>
        {data.submission.selftext ? (
          <p className='mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-700 sm:text-base'>{data.submission.selftext}</p>
        ) : null}

        <div className='mt-4 flex flex-wrap items-center gap-2 text-xs'>
          <span className='score-pill score-pill-neutral'>r/{data.submission.subreddit}</span>
          <span className='score-pill score-pill-neutral'>score {data.submission.score}</span>
          <span className='score-pill score-pill-neutral'>{data.submission.num_comments} comments</span>
          <span className='score-pill score-pill-neutral'>id {data.submission.id}</span>
        </div>
      </section>

      <section className='space-y-3'>
        <h2 className='display text-2xl font-semibold text-slate-900'>Comments + Ticker Stance</h2>
        <CommentList comments={data.comments} />
      </section>
    </main>
  );
}
