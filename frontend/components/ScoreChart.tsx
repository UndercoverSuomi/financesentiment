import HintLabel from '@/components/HintLabel';
import { formatScore } from '@/lib/format';
import type { TickerPoint } from '@/lib/types';

const CHART_WIDTH = 520;
const CHART_TOP = 10;
const CHART_BOTTOM = 170;

function yFromScore(score: number): number {
  const clamped = Math.max(-1, Math.min(1, score));
  return CHART_TOP + ((1 - (clamped + 1) / 2) * (CHART_BOTTOM - CHART_TOP));
}

function linePath(values: number[]): string {
  if (!values.length) return '';

  return values
    .map((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * CHART_WIDTH;
      const y = yFromScore(v);
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
    })
    .join(' ');
}

function areaPath(values: number[]): string {
  if (!values.length) return '';
  const topLine = linePath(values);
  return `${topLine} L ${CHART_WIDTH} ${CHART_BOTTOM} L 0 ${CHART_BOTTOM} Z`;
}

type Props = {
  points: TickerPoint[];
};

export default function ScoreChart({ points }: Props) {
  if (!points.length) return <div className='line-section py-4 text-sm text-slate-600'>No score history yet.</div>;

  const values = points.map((p) => p.score_weighted);
  const path = linePath(values);
  const area = areaPath(values);
  const latest = values[values.length - 1];
  const toneClass =
    latest >= 0.15 ? 'score-pill-positive' : latest <= -0.15 ? 'score-pill-negative' : 'score-pill-neutral';
  const grid = [-1, -0.5, 0, 0.5, 1];
  const latestX = ((values.length - 1) / Math.max(values.length - 1, 1)) * CHART_WIDTH;
  const latestY = yFromScore(latest);

  return (
    <div className='panel pb-4'>
      <div className='mb-3 flex items-center justify-between gap-2'>
        <h3 className='display text-lg font-semibold text-slate-900'>
          <HintLabel label='Weighted Stance' hint='Zeitreihe des gewichteten Stance-Scores (Range -1 bis 1).' />
        </h3>
        <span
          className={`score-pill ${toneClass}`}
          title='Neuester Punkt in der dargestellten Zeitreihe.'
        >
          latest {formatScore(latest)}
        </span>
      </div>

      <svg viewBox={`0 0 ${CHART_WIDTH} 180`} className='h-48 w-full'>
        <defs>
          <linearGradient id='scoreArea' x1='0' y1='0' x2='0' y2='1'>
            <stop offset='0%' stopColor='rgba(23,105,229,0.24)' />
            <stop offset='100%' stopColor='rgba(23,105,229,0.03)' />
          </linearGradient>
        </defs>
        {grid.map((level) => {
          const y = yFromScore(level);
          return (
            <g key={level}>
              <line x1='0' y1={y} x2={CHART_WIDTH} y2={y} stroke='rgba(15,23,32,0.13)' strokeDasharray='5 6' />
              <text x='4' y={y - 4} fontSize='10' fill='rgba(17,33,45,0.55)'>
                {level.toFixed(1)}
              </text>
            </g>
          );
        })}
        <path d={area} fill='url(#scoreArea)' />
        <path d={path} stroke='#1769e5' strokeWidth='3' fill='none' strokeLinecap='round' />
        {values.map((v, i) => {
          const x = (i / Math.max(values.length - 1, 1)) * CHART_WIDTH;
          const y = yFromScore(v);
          return <circle key={`${points[i].date_bucket_berlin}-${i}`} cx={x} cy={y} r='2.4' fill='#1769e5' />;
        })}
        <circle cx={latestX} cy={latestY} r='5' fill='white' stroke='#1769e5' strokeWidth='2' />
      </svg>
      <p className='mt-2 text-xs text-slate-500'>Window: last {points.length} bucket(s), normalized to score range [-1, 1].</p>
    </div>
  );
}
