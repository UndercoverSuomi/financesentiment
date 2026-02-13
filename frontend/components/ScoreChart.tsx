import HintLabel from '@/components/HintLabel';
import { formatScore, formatUsd } from '@/lib/format';
import type { TickerPoint, TickerPricePoint } from '@/lib/types';

const SVG_WIDTH = 560;
const SVG_HEIGHT = 200;
const PLOT_LEFT = 30;
const PLOT_RIGHT = 500;
const PLOT_TOP = 12;
const PLOT_BOTTOM = 172;
const PLOT_WIDTH = PLOT_RIGHT - PLOT_LEFT;
const PLOT_HEIGHT = PLOT_BOTTOM - PLOT_TOP;

function yFromScore(score: number): number {
  const clamped = Math.max(-1, Math.min(1, score));
  return PLOT_TOP + ((1 - (clamped + 1) / 2) * PLOT_HEIGHT);
}

function xFromIndex(index: number, total: number): number {
  if (total <= 1) return PLOT_LEFT + PLOT_WIDTH / 2;
  return PLOT_LEFT + (index / (total - 1)) * PLOT_WIDTH;
}

function alignPricesToPoints(points: TickerPoint[], pricePoints: TickerPricePoint[]): Array<number | null> {
  if (!points.length || !pricePoints.length) {
    return points.map(() => null);
  }

  const sortedPrices = [...pricePoints].sort((a, b) => a.date_bucket_berlin.localeCompare(b.date_bucket_berlin));

  let cursor = 0;
  let latestSeen: number | null = null;
  return points.map((point) => {
    while (cursor < sortedPrices.length && sortedPrices[cursor].date_bucket_berlin <= point.date_bucket_berlin) {
      latestSeen = sortedPrices[cursor].close_price;
      cursor += 1;
    }
    return latestSeen;
  });
}

function buildLinePath(values: Array<number | null>, yFromValue: (value: number) => number, total: number): string {
  let path = '';
  let drawing = false;
  values.forEach((value, index) => {
    if (value === null) {
      drawing = false;
      return;
    }
    const x = xFromIndex(index, total);
    const y = yFromValue(value);
    path += `${drawing ? ' L' : 'M'} ${x} ${y}`;
    drawing = true;
  });
  return path.trim();
}

function buildLinearTicks(minValue: number, maxValue: number, tickCount: number): number[] {
  if (tickCount <= 1) return [maxValue];
  const step = (maxValue - minValue) / (tickCount - 1);
  return Array.from({ length: tickCount }, (_, index) => minValue + step * index);
}

type Props = {
  points: TickerPoint[];
  pricePoints?: TickerPricePoint[];
  priceFetchError?: string | null;
};

export default function ScoreChart({ points, pricePoints = [], priceFetchError = null }: Props) {
  if (!points.length) return <div className='line-section py-4 text-sm text-slate-600'>No score history yet.</div>;

  const values = points.map((p) => p.score_weighted);
  const latest = values[values.length - 1];
  const toneClass =
    latest >= 0.15 ? 'score-pill-positive' : latest <= -0.15 ? 'score-pill-negative' : 'score-pill-neutral';
  const gridLevels = [-1, -0.5, 0, 0.5, 1];
  const baselineY = yFromScore(0);
  const latestX = xFromIndex(values.length - 1, values.length);
  const latestY = yFromScore(latest);
  const slotWidth = PLOT_WIDTH / Math.max(points.length, 1);
  const barWidth = Math.max(4, Math.min(slotWidth * 0.62, 18));

  const alignedPrices = alignPricesToPoints(points, pricePoints);
  const validPrices = alignedPrices.filter((value): value is number => value !== null);
  const hasPriceOverlay = validPrices.length > 0;

  let priceMin = 0;
  let priceMax = 1;
  if (hasPriceOverlay) {
    const rawMin = Math.min(...validPrices);
    const rawMax = Math.max(...validPrices);
    if (rawMax === rawMin) {
      const pad = Math.max(rawMin * 0.01, 1);
      priceMin = Math.max(rawMin - pad, 0);
      priceMax = rawMax + pad;
    } else {
      const pad = (rawMax - rawMin) * 0.08;
      priceMin = Math.max(rawMin - pad, 0);
      priceMax = rawMax + pad;
    }
  }

  const yFromPrice = (value: number): number => {
    if (priceMax <= priceMin) return PLOT_TOP + PLOT_HEIGHT / 2;
    const normalized = (value - priceMin) / (priceMax - priceMin);
    return PLOT_BOTTOM - normalized * PLOT_HEIGHT;
  };

  const pricePath = hasPriceOverlay ? buildLinePath(alignedPrices, yFromPrice, alignedPrices.length) : '';
  const priceTicks = hasPriceOverlay ? buildLinearTicks(priceMin, priceMax, 5) : [];

  let latestPriceIndex = -1;
  for (let idx = alignedPrices.length - 1; idx >= 0; idx -= 1) {
    if (alignedPrices[idx] !== null) {
      latestPriceIndex = idx;
      break;
    }
  }
  const latestPrice = latestPriceIndex >= 0 ? alignedPrices[latestPriceIndex] : null;

  return (
    <div className='panel pb-4'>
      <div className='mb-3 flex items-center justify-between gap-2'>
        <h3 className='display text-lg font-semibold text-slate-900'>
          <HintLabel label='Stance vs Price' hint='Sentiment-Balken (links) plus Close-Preis-Linie (rechts).' />
        </h3>
        <div className='flex flex-wrap items-center justify-end gap-2'>
          <span className={`score-pill ${toneClass}`} title='Neuester Stance-Punkt in der dargestellten Zeitreihe.'>
            score {formatScore(latest)}
          </span>
          {latestPrice !== null ? (
            <span className='score-pill score-pill-neutral' title='Neuester verfuegbarer Close-Preis (USD).'>
              close {formatUsd(latestPrice)}
            </span>
          ) : null}
        </div>
      </div>

      <svg viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} className='h-48 w-full'>
        {gridLevels.map((level) => {
          const y = yFromScore(level);
          return (
            <g key={level}>
              <line x1={PLOT_LEFT} y1={y} x2={PLOT_RIGHT} y2={y} stroke='rgba(15,23,32,0.13)' strokeDasharray='4 5' />
              <text x='3' y={y - 4} fontSize='10' fill='rgba(17,33,45,0.55)'>
                {level.toFixed(1)}
              </text>
            </g>
          );
        })}
        <line x1={PLOT_LEFT} y1={PLOT_TOP} x2={PLOT_LEFT} y2={PLOT_BOTTOM} stroke='rgba(15,23,32,0.22)' />
        <line x1={PLOT_LEFT} y1={baselineY} x2={PLOT_RIGHT} y2={baselineY} stroke='rgba(15,23,32,0.32)' />
        <line x1={PLOT_RIGHT} y1={PLOT_TOP} x2={PLOT_RIGHT} y2={PLOT_BOTTOM} stroke='rgba(15,23,32,0.22)' />

        {values.map((v, i) => {
          const x = xFromIndex(i, values.length);
          const y = yFromScore(v);
          const height = Math.max(Math.abs(baselineY - y), 1.5);
          const yTop = Math.min(baselineY, y);
          const fill = v >= 0 ? 'rgba(23,105,229,0.72)' : 'rgba(220, 38, 38, 0.68)';
          return (
            <rect
              key={`${points[i].date_bucket_berlin}-${i}`}
              x={x - barWidth / 2}
              y={yTop}
              width={barWidth}
              height={height}
              rx='2'
              fill={fill}
            />
          );
        })}

        {hasPriceOverlay ? (
          <g>
            <path d={pricePath} stroke='#0f766e' strokeWidth='2.4' fill='none' strokeLinecap='round' />
            {alignedPrices.map((value, idx) => {
              if (value === null) return null;
              return (
                <circle
                  key={`price-${points[idx].date_bucket_berlin}-${idx}`}
                  cx={xFromIndex(idx, points.length)}
                  cy={yFromPrice(value)}
                  r='2'
                  fill='#0f766e'
                />
              );
            })}
          </g>
        ) : null}

        {priceTicks.map((value) => (
          <text key={value} x={PLOT_RIGHT + 6} y={yFromPrice(value) + 4} fontSize='10' fill='rgba(17,33,45,0.6)'>
            {formatUsd(value)}
          </text>
        ))}

        <circle cx={latestX} cy={latestY} r='5' fill='white' stroke='#1769e5' strokeWidth='2' />
        {latestPrice !== null && latestPriceIndex >= 0 ? (
          <circle
            cx={xFromIndex(latestPriceIndex, points.length)}
            cy={yFromPrice(latestPrice)}
            r='4'
            fill='white'
            stroke='#0f766e'
            strokeWidth='2'
          />
        ) : null}
      </svg>
      <p className='mt-2 text-xs text-slate-500'>
        Window: last {points.length} bucket(s). Score uses left axis [-1, 1], close price uses right USD axis.
      </p>
      {!hasPriceOverlay ? (
        <p className='mt-1 text-xs text-amber-700' title={priceFetchError || undefined}>
          Price overlay unavailable for this range.
        </p>
      ) : null}
    </div>
  );
}
