import type { TickerPoint } from '@/lib/types';

type Props = {
  points: TickerPoint[];
};

export default function VolumeChart({ points }: Props) {
  if (!points.length) return <div className='line-section py-4 text-sm text-slate-600'>No volume history yet.</div>;

  const max = Math.max(...points.map((p) => p.mention_count), 1);
  const total = points.reduce((sum, p) => sum + p.mention_count, 0);

  return (
    <div className='panel pb-4'>
      <div className='mb-3 flex items-center justify-between gap-2'>
        <h3 className='display text-lg font-semibold text-slate-900'>Mention Volume</h3>
        <span className='score-pill score-pill-neutral'>total {total}</span>
      </div>

      <div className='space-y-2.5'>
        {points.map((p, idx) => (
          <div
            key={`${p.date_bucket_berlin}-${idx}`}
            className='grid grid-cols-[102px_1fr_54px] items-center gap-2 text-xs'
          >
            <span className='font-medium text-slate-600'>{p.date_bucket_berlin}</span>
            <div className='h-2.5 rounded-full bg-slate-200/75'>
              <div
                className='h-2.5 rounded-full bg-gradient-to-r from-blue-500 to-cyan-400'
                style={{ width: `${Math.max((p.mention_count / max) * 100, 3)}%` }}
              />
            </div>
            <span className='text-right font-semibold text-slate-800'>{p.mention_count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
