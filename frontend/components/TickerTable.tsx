import Link from 'next/link';

import { formatPct, formatScore } from '@/lib/format';
import type { DailyScore } from '@/lib/types';

type Props = {
  rows: DailyScore[];
};

function scoreTone(value: number): string {
  if (value >= 0.2) return 'score-pill score-pill-positive';
  if (value <= -0.2) return 'score-pill score-pill-negative';
  return 'score-pill score-pill-neutral';
}

export default function TickerTable({ rows }: Props) {
  if (!rows.length) {
    return <div className='line-section py-4 text-sm text-slate-600'>No rows for this selection.</div>;
  }

  return (
    <div className='panel py-0'>
      <div className='overflow-x-auto'>
        <table className='min-w-full text-sm'>
          <thead className='bg-slate-50/80 text-left text-slate-600'>
            <tr>
              <th className='px-4 py-3 font-semibold'>#</th>
              <th className='px-4 py-3 font-semibold'>Ticker</th>
              <th className='px-4 py-3 font-semibold'>Weighted</th>
              <th className='px-4 py-3 font-semibold'>Unweighted</th>
              <th className='px-4 py-3 font-semibold'>Mentions</th>
              <th className='px-4 py-3 font-semibold'>Unclear Rate</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr
                key={`${row.subreddit}-${row.ticker}`}
                className='border-t border-slate-200/80 transition-colors hover:bg-slate-50/70'
              >
                <td className='px-4 py-3 text-slate-500'>{idx + 1}</td>
                <td className='px-4 py-3'>
                  <Link
                    href={
                      row.subreddit.toUpperCase() === 'ALL'
                        ? `/ticker/${row.ticker}`
                        : `/ticker/${row.ticker}?subreddit=${encodeURIComponent(row.subreddit)}`
                    }
                    className='display inline-flex items-center gap-2 text-base font-semibold text-slate-900 transition hover:text-blue-700'
                  >
                    {row.ticker}
                    <span aria-hidden='true' className='text-[10px] text-slate-500'>open</span>
                  </Link>
                </td>
                <td className='px-4 py-3'>
                  <span className={scoreTone(row.score_weighted)}>{formatScore(row.score_weighted)}</span>
                </td>
                <td className='px-4 py-3'>
                  <span className={scoreTone(row.score_unweighted)}>{formatScore(row.score_unweighted)}</span>
                </td>
                <td className='px-4 py-3 font-semibold text-slate-800'>{row.mention_count}</td>
                <td className='px-4 py-3'>
                  <span className='score-pill score-pill-neutral'>{formatPct(row.unclear_rate)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className='border-t border-slate-200/80 px-4 py-2 text-xs text-slate-500'>
        Click a ticker to open trend charts and representative comments.
      </div>
    </div>
  );
}
