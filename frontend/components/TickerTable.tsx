import Link from 'next/link';

import HintLabel from '@/components/HintLabel';
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
              <th className='px-4 py-3 font-semibold'>
                <HintLabel label='Weighted' hint='Interaktionsgewichteter Stance-Score (Upvotes + optionale Decays).' />
              </th>
              <th className='px-4 py-3 font-semibold'>
                <HintLabel label='Unweighted' hint='Einfacher Mittelwert der nicht-UNCLEAR Stance-Scores.' />
              </th>
              <th className='px-4 py-3 font-semibold'>
                <HintLabel label='95% CI' hint='95%-Konfidenzintervall des ungewichteten Mittelwerts. Bei Legacy-Daten ggf. als Punktintervall angenaehert.' />
              </th>
              <th className='px-4 py-3 font-semibold'>
                <HintLabel label='Valid N' hint='Anzahl der nicht-UNCLEAR Beobachtungen fuer den Ticker.' />
              </th>
              <th className='px-4 py-3 font-semibold'>
                <HintLabel label='Mentions' hint='Alle Mentions inklusive UNCLEAR.' />
              </th>
              <th className='px-4 py-3 font-semibold'>
                <HintLabel label='Unclear Rate' hint='Anteil UNCLEAR an allen Mentions.' />
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => {
              const mentionCount = Number.isFinite(row.mention_count) ? row.mention_count : 0;
              const unclearCount = Number.isFinite(row.unclear_count) ? row.unclear_count : 0;
              const fallbackValidN = Math.max(mentionCount - unclearCount, 0);
              const validN = Number.isFinite(row.valid_count) ? row.valid_count : fallbackValidN;

              const hasExactCi = Number.isFinite(row.ci95_low_unweighted) && Number.isFinite(row.ci95_high_unweighted);
              const ciLow = hasExactCi ? row.ci95_low_unweighted : row.score_unweighted;
              const ciHigh = hasExactCi ? row.ci95_high_unweighted : row.score_unweighted;

              const unclearRate = Number.isFinite(row.unclear_rate)
                ? row.unclear_rate
                : (mentionCount > 0 ? unclearCount / mentionCount : 0);

              return (
                <tr
                  key={`${row.subreddit}-${row.ticker}`}
                  className='border-t border-slate-200/80 transition-colors hover:bg-slate-50/70'
                >
                  <td className='px-4 py-3 text-slate-500'>{idx + 1}</td>
                  <td className='px-4 py-3'>
                    <Link
                      href={
                        (row.subreddit || 'ALL').toUpperCase() === 'ALL'
                          ? `/ticker/${row.ticker}`
                          : `/ticker/${row.ticker}?subreddit=${encodeURIComponent(row.subreddit || 'ALL')}`
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
                  <td
                    className='px-4 py-3 text-xs text-slate-700'
                    title={
                      hasExactCi
                        ? 'Exaktes 95%-Konfidenzintervall aus den aktuellen Aggregationsstatistiken.'
                        : 'Legacy-Fallback: exaktes CI fuer diese Zeile nicht verfuegbar, daher Punktintervall um den Mittelwert.'
                    }
                  >
                    [{formatScore(ciLow)}, {formatScore(ciHigh)}]
                  </td>
                  <td
                    className='px-4 py-3 font-semibold text-slate-800'
                    title={
                      Number.isFinite(row.valid_count)
                        ? 'Direkt aus Aggregation.'
                        : 'Legacy-Fallback: aus Mentions minus UNCLEAR angenaehert.'
                    }
                  >
                    {validN}
                  </td>
                  <td className='px-4 py-3 font-semibold text-slate-800'>{mentionCount}</td>
                  <td className='px-4 py-3'>
                    <span className='score-pill score-pill-neutral'>{formatPct(unclearRate)}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className='border-t border-slate-200/80 px-4 py-2 text-xs text-slate-500'>
        Click a ticker to open trend charts and representative comments.
      </div>
    </div>
  );
}
