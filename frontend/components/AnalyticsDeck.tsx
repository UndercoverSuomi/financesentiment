import HintLabel from '@/components/HintLabel';
import { formatPct, formatScore } from '@/lib/format';
import type { AnalyticsResponse } from '@/lib/types';

type Props = {
  analytics: AnalyticsResponse;
};

const CHART_W = 620;
const CHART_H = 220;
const PAD_X = 36;
const PAD_TOP = 14;
const PAD_BOTTOM = 28;
const PLOT_W = CHART_W - PAD_X * 2;
const PLOT_H = CHART_H - PAD_TOP - PAD_BOTTOM;

function xAt(idx: number, total: number): number {
  if (total <= 1) return PAD_X;
  return PAD_X + (idx / (total - 1)) * PLOT_W;
}

function yScore(score: number): number {
  const clamped = Math.max(-1, Math.min(1, score));
  return PAD_TOP + (1 - (clamped + 1) / 2) * PLOT_H;
}

function yShare(value: number): number {
  const clamped = Math.max(0, Math.min(1, value));
  return PAD_TOP + (1 - clamped) * PLOT_H;
}

function linePath(values: number[], mapper: (v: number) => number): string {
  if (!values.length) return '';
  return values
    .map((v, idx) => `${idx === 0 ? 'M' : 'L'} ${xAt(idx, values.length)} ${mapper(v)}`)
    .join(' ');
}

function tone(delta: number): string {
  if (delta >= 0.08) return 'score-pill score-pill-positive';
  if (delta <= -0.08) return 'score-pill score-pill-negative';
  return 'score-pill score-pill-neutral';
}

function corrTone(value: number): string {
  if (value >= 0.35) return 'score-pill score-pill-positive';
  if (value <= -0.35) return 'score-pill score-pill-negative';
  return 'score-pill score-pill-neutral';
}

function regimeTone(regime: string): string {
  if (regime === 'risk-on') return 'score-pill score-pill-positive';
  if (regime === 'risk-off') return 'score-pill score-pill-negative';
  return 'score-pill score-pill-neutral';
}

function regimeColor(score: number): string {
  if (score >= 0.15) return 'rgba(13,148,104,0.74)';
  if (score <= -0.15) return 'rgba(194,72,72,0.74)';
  return 'rgba(95,111,128,0.65)';
}

function shortDate(isoDate: string): string {
  if (!isoDate || isoDate.length < 10) return isoDate;
  return isoDate.slice(5);
}

function dayCircleColor(unclearRate: number): string {
  const clamped = Math.max(0, Math.min(1, unclearRate));
  const alpha = 0.3 + clamped * 0.55;
  return `rgba(245, 158, 11, ${alpha.toFixed(3)})`;
}

export default function AnalyticsDeck({ analytics }: Props) {
  const trend = analytics.trend;
  if (!trend.length) {
    return <section className='line-section py-4 text-sm text-slate-600'>No analytics history yet.</section>;
  }

  const rolling = analytics.rolling_trend.length ? analytics.rolling_trend : trend.map((p) => ({
    ...p,
    weighted_ma7: p.weighted_score,
    weighted_ma14: p.weighted_score,
    mentions_ma7: p.mention_count,
    unclear_ma7: p.unclear_rate,
    volatility_ma7: 0,
    momentum_7d: 0,
  }));

  const weighted = trend.map((p) => p.weighted_score);
  const unweighted = trend.map((p) => p.unweighted_score);
  const mentions = trend.map((p) => p.mention_count);
  const unclear = trend.map((p) => p.unclear_rate);
  const topShare = trend.map((p) => p.top_ticker_share);
  const concentration = trend.map((p) => p.concentration_hhi);
  const weightedMa7 = rolling.map((p) => p.weighted_ma7);
  const weightedMa14 = rolling.map((p) => p.weighted_ma14);
  const momentum7d = rolling.map((p) => p.momentum_7d);
  const maxMentions = Math.max(...mentions, 1);

  const weightedPath = linePath(weighted, yScore);
  const unweightedPath = linePath(unweighted, yScore);
  const weightedMa7Path = linePath(weightedMa7, yScore);
  const weightedMa14Path = linePath(weightedMa14, yScore);
  const unclearPath = linePath(unclear, yShare);
  const topSharePath = linePath(topShare, yShare);
  const hhiPath = linePath(concentration, yShare);

  const latest = trend[trend.length - 1];
  const prev = trend.length > 1 ? trend[trend.length - 2] : latest;
  const delta = latest.weighted_score - prev.weighted_score;

  const positiveMomentumDays = momentum7d.filter((value) => value > 0).length;
  const negativeMomentumDays = momentum7d.filter((value) => value < 0).length;

  const maxSubredditMentions = Math.max(...analytics.subreddit_snapshot.map((x) => x.mention_count), 1);
  const maxWeekdayMentions = Math.max(...analytics.weekday_profile.map((x) => x.avg_mentions), 1);

  const corrMentions = analytics.correlations.mentions_vs_abs_score;
  const corrUnclear = analytics.correlations.unclear_vs_abs_score;
  const corrConc = analytics.correlations.concentration_vs_unclear;

  return (
    <section className='fade-up space-y-5'>
      <div className='panel p-5 sm:p-6'>
        <div className='mb-4 flex flex-wrap items-center justify-between gap-2'>
          <h2 className='display text-2xl font-bold text-slate-900'>
            <HintLabel
              label='Deep Analytics'
              hint='Mehrfenster-Analyse fuer Trends, Regime, Korrelationen, Konzentration und Ticker-Dynamik.'
            />
          </h2>
          <span className='score-pill score-pill-neutral'>
            {analytics.date_from} to {analytics.date_to}
          </span>
        </div>

        <div className='grid gap-3 sm:grid-cols-3 xl:grid-cols-6'>
          <article className='metric-card'>
            <p className='eyebrow'>
              <HintLabel label='Avg Mood' hint='Mittlerer gewichteter Score im Analysefenster.' />
            </p>
            <p className='display mt-1 text-2xl font-bold text-slate-900'>{formatScore(analytics.market_summary.avg_weighted_score)}</p>
          </article>
          <article className='metric-card'>
            <p className='eyebrow'>
              <HintLabel label='Volatility' hint='Standardabweichung des gewichteten Tages-Scores.' />
            </p>
            <p className='display mt-1 text-2xl font-bold text-slate-900'>{formatScore(analytics.market_summary.score_volatility)}</p>
          </article>
          <article className='metric-card'>
            <p className='eyebrow'>
              <HintLabel label='Avg Unclear' hint='Durchschnittliche UNCLEAR-Rate pro aktivem Tag.' />
            </p>
            <p className='display mt-1 text-2xl font-bold text-slate-900'>{formatPct(analytics.market_summary.avg_unclear_rate)}</p>
          </article>
          <article className='metric-card'>
            <p className='eyebrow'>
              <HintLabel label='Valid Share' hint='Durchschnittlicher Anteil validierter (nicht-UNCLEAR) Mentions.' />
            </p>
            <p className='display mt-1 text-2xl font-bold text-slate-900'>{formatPct(analytics.market_summary.avg_valid_ratio)}</p>
          </article>
          <article className='metric-card'>
            <p className='eyebrow'>
              <HintLabel label='Eff. Tickers' hint='1 / HHI. Hoeher bedeutet breitere Verteilung ueber Ticker.' />
            </p>
            <p className='display mt-1 text-2xl font-bold text-slate-900'>{analytics.market_summary.effective_ticker_count.toFixed(2)}</p>
          </article>
          <article className='metric-card'>
            <p className='eyebrow'>
              <HintLabel label='Active Days' hint='Tage mit mindestens einer Mention im gewaehlten Fenster.' />
            </p>
            <p className='display mt-1 text-2xl font-bold text-slate-900'>{analytics.market_summary.active_days}</p>
          </article>
        </div>

        <div className='mt-4 flex flex-wrap items-center gap-2 text-xs'>
          <span className={regimeTone(analytics.regime_breakdown.current_regime)}>
            regime {analytics.regime_breakdown.current_regime}
          </span>
          <span className='score-pill score-pill-neutral' title='Lineare Trend-Steigung des weighted Scores pro Tag.'>
            score slope {formatScore(analytics.market_summary.score_trend_slope)} / day
          </span>
          <span className='score-pill score-pill-neutral' title='Lineare Trend-Steigung der Mention-Anzahl pro Tag.'>
            mentions slope {analytics.market_summary.mention_trend_slope.toFixed(1)} / day
          </span>
          <span className={corrTone(corrMentions)} title='Pearson Korrelation: Mention-Volumen vs. absolute Marktstimmung.'>
            corr(vol, |mood|) {corrMentions.toFixed(2)}
          </span>
          <span className={corrTone(corrUnclear)} title='Pearson Korrelation: UNCLEAR-Rate vs. absolute Marktstimmung.'>
            corr(unclear, |mood|) {corrUnclear.toFixed(2)}
          </span>
          <span className={corrTone(corrConc)} title='Pearson Korrelation: HHI-Konzentration vs. UNCLEAR-Rate.'>
            corr(HHI, unclear) {corrConc.toFixed(2)}
          </span>
        </div>
      </div>

      <div className='grid gap-4 xl:grid-cols-2'>
        <div className='panel p-4'>
          <div className='mb-3 flex flex-wrap items-center justify-between gap-2'>
            <h3 className='display text-lg font-semibold text-slate-900'>
              <HintLabel label='Market Trend + Rolling Means' hint='Tages-Score mit 7d/14d gleitenden Mittelwerten und Mention-Balken.' />
            </h3>
            <span className={tone(delta)}>latest delta {formatScore(delta)}</span>
          </div>
          <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} className='h-56 w-full'>
            {[-1, -0.5, 0, 0.5, 1].map((level) => {
              const y = yScore(level);
              return (
                <g key={level}>
                  <line x1={PAD_X} y1={y} x2={CHART_W - PAD_X} y2={y} stroke='rgba(15,23,32,0.1)' strokeDasharray='4 5' />
                  <text x='4' y={y - 2} fontSize='10' fill='rgba(17,33,45,0.55)'>{level.toFixed(1)}</text>
                </g>
              );
            })}
            {trend.map((point, idx) => {
              const x = xAt(idx, trend.length);
              const height = (point.mention_count / maxMentions) * 34;
              const y = CHART_H - PAD_BOTTOM - height;
              return (
                <rect
                  key={`m-${point.date_bucket_berlin}-${idx}`}
                  x={x - 3}
                  y={y}
                  width='6'
                  height={height}
                  fill='rgba(15,23,32,0.16)'
                >
                  <title>{`${point.date_bucket_berlin}: ${point.mention_count} mentions`}</title>
                </rect>
              );
            })}
            <path d={weightedMa14Path} stroke='rgba(3,105,161,0.58)' strokeWidth='2' fill='none' strokeLinecap='round' strokeDasharray='6 5' />
            <path d={weightedMa7Path} stroke='rgba(2,132,199,0.8)' strokeWidth='2.3' fill='none' strokeLinecap='round' />
            <path d={unweightedPath} stroke='rgba(23,105,229,0.42)' strokeWidth='2' fill='none' strokeLinecap='round' />
            <path d={weightedPath} stroke='#1769e5' strokeWidth='3' fill='none' strokeLinecap='round' />
          </svg>
          <div className='mt-2 flex flex-wrap gap-2 text-xs text-slate-600'>
            <span className='score-pill score-pill-neutral'>blue: weighted</span>
            <span className='score-pill score-pill-neutral'>light blue: unweighted</span>
            <span className='score-pill score-pill-neutral'>cyan: MA7</span>
            <span className='score-pill score-pill-neutral'>teal dashed: MA14</span>
            <span className='score-pill score-pill-neutral'>gray bars: mentions</span>
          </div>
        </div>

        <div className='panel p-4'>
          <div className='mb-3 flex flex-wrap items-center justify-between gap-2'>
            <h3 className='display text-lg font-semibold text-slate-900'>
              <HintLabel label='Risk x Noise Quadrant' hint='Jeder Punkt ist ein Tag: x = UNCLEAR-Rate, y = weighted Score, Radius = Mention-Volumen.' />
            </h3>
            <span className='score-pill score-pill-neutral'>{trend.length} days</span>
          </div>
          <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} className='h-56 w-full'>
            {[0, 0.25, 0.5, 0.75, 1].map((level) => {
              const x = PAD_X + level * PLOT_W;
              return <line key={`sx-${level}`} x1={x} y1={PAD_TOP} x2={x} y2={CHART_H - PAD_BOTTOM} stroke='rgba(15,23,32,0.08)' strokeDasharray='4 5' />;
            })}
            {[-1, -0.5, 0, 0.5, 1].map((level) => {
              const y = yScore(level);
              return <line key={`sy-${level}`} x1={PAD_X} y1={y} x2={CHART_W - PAD_X} y2={y} stroke='rgba(15,23,32,0.08)' strokeDasharray='4 5' />;
            })}
            <line x1={PAD_X} y1={yScore(0)} x2={CHART_W - PAD_X} y2={yScore(0)} stroke='rgba(15,23,32,0.25)' />
            {trend.map((point, idx) => {
              const x = PAD_X + Math.max(0, Math.min(1, point.unclear_rate)) * PLOT_W;
              const y = yScore(point.weighted_score);
              const radius = 3 + (point.mention_count / maxMentions) * 9;
              return (
                <circle
                  key={`q-${point.date_bucket_berlin}-${idx}`}
                  cx={x}
                  cy={y}
                  r={radius}
                  fill={dayCircleColor(point.unclear_rate)}
                  stroke='rgba(15,23,32,0.45)'
                  strokeWidth='1'
                >
                  <title>{`${point.date_bucket_berlin}: score ${formatScore(point.weighted_score)}, unclear ${formatPct(point.unclear_rate)}, mentions ${point.mention_count}`}</title>
                </circle>
              );
            })}
            <text x={PAD_X} y={CHART_H - 6} fontSize='10' fill='rgba(17,33,45,0.6)'>low unclear</text>
            <text x={CHART_W - PAD_X - 42} y={CHART_H - 6} fontSize='10' fill='rgba(17,33,45,0.6)'>high unclear</text>
          </svg>
          <div className='mt-2 flex flex-wrap gap-2 text-xs text-slate-600'>
            <span className='score-pill score-pill-positive'>above zero: risk-on tendency</span>
            <span className='score-pill score-pill-negative'>below zero: risk-off tendency</span>
            <span className='score-pill score-pill-neutral'>more opaque = noisier day</span>
          </div>
        </div>
      </div>

      <div className='grid gap-4 xl:grid-cols-2'>
        <div className='panel p-4'>
          <div className='mb-3 flex flex-wrap items-center justify-between gap-2'>
            <h3 className='display text-lg font-semibold text-slate-900'>
              <HintLabel label='Breadth & Uncertainty' hint='Label-Anteile pro Tag als gestapelte Balken, plus UNCLEAR-Linie.' />
            </h3>
            <span className='score-pill score-pill-neutral'>{trend.length} days</span>
          </div>
          <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} className='h-56 w-full'>
            {[0, 0.25, 0.5, 0.75, 1].map((level) => {
              const y = yShare(level);
              return (
                <g key={`b-${level}`}>
                  <line x1={PAD_X} y1={y} x2={CHART_W - PAD_X} y2={y} stroke='rgba(15,23,32,0.1)' strokeDasharray='4 5' />
                  <text x='4' y={y - 2} fontSize='10' fill='rgba(17,33,45,0.55)'>{Math.round(level * 100)}%</text>
                </g>
              );
            })}
            {trend.map((point, idx) => {
              const x = xAt(idx, trend.length);
              const width = Math.max((PLOT_W / Math.max(trend.length, 1)) * 0.55, 4);
              const yNeutralTop = yShare(point.bullish_share + point.neutral_share);
              const yBullTop = yShare(point.bullish_share);
              const yBase = yShare(0);
              return (
                <g key={`s-${point.date_bucket_berlin}-${idx}`}>
                  <rect x={x - width / 2} y={yNeutralTop} width={width} height={yBase - yNeutralTop} fill='rgba(200,72,72,0.4)'>
                    <title>{`${point.date_bucket_berlin}: bearish ${formatPct(point.bearish_share)}`}</title>
                  </rect>
                  <rect x={x - width / 2} y={yBullTop} width={width} height={yNeutralTop - yBullTop} fill='rgba(95,111,128,0.45)'>
                    <title>{`${point.date_bucket_berlin}: neutral ${formatPct(point.neutral_share)}`}</title>
                  </rect>
                  <rect x={x - width / 2} y={yShare(1)} width={width} height={yBullTop - yShare(1)} fill='rgba(13,148,104,0.45)'>
                    <title>{`${point.date_bucket_berlin}: bullish ${formatPct(point.bullish_share)}`}</title>
                  </rect>
                </g>
              );
            })}
            <path d={unclearPath} stroke='#f59e0b' strokeWidth='2.2' fill='none' strokeLinecap='round' />
          </svg>
          <div className='mt-2 flex flex-wrap gap-2 text-xs text-slate-600'>
            <span className='score-pill score-pill-positive'>bullish share</span>
            <span className='score-pill score-pill-neutral'>neutral share</span>
            <span className='score-pill score-pill-negative'>bearish share</span>
            <span className='score-pill score-pill-neutral'>orange line: unclear</span>
          </div>
        </div>

        <div className='panel p-4'>
          <div className='mb-3 flex flex-wrap items-center justify-between gap-2'>
            <h3 className='display text-lg font-semibold text-slate-900'>
              <HintLabel label='Concentration & Momentum' hint='Top-Ticker-Share, HHI und 7d Momentum des Markt-Scores.' />
            </h3>
            <span className='score-pill score-pill-neutral'>
              avg top share {formatPct(analytics.market_summary.avg_top_ticker_share)}
            </span>
          </div>
          <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} className='h-56 w-full'>
            {[0, 0.25, 0.5, 0.75, 1].map((level) => {
              const y = yShare(level);
              return (
                <g key={`c-${level}`}>
                  <line x1={PAD_X} y1={y} x2={CHART_W - PAD_X} y2={y} stroke='rgba(15,23,32,0.1)' strokeDasharray='4 5' />
                  <text x='4' y={y - 2} fontSize='10' fill='rgba(17,33,45,0.55)'>{Math.round(level * 100)}%</text>
                </g>
              );
            })}
            <path d={topSharePath} stroke='#0ea5e9' strokeWidth='2.8' fill='none' strokeLinecap='round' />
            <path d={hhiPath} stroke='#0f1720' strokeWidth='2' fill='none' strokeLinecap='round' strokeDasharray='6 5' />
            <path d={linePath(momentum7d.map((value) => Math.max(0, Math.min(1, (value + 1) / 2))), yShare)} stroke='#7c3aed' strokeWidth='2' fill='none' strokeLinecap='round' />
          </svg>
          <div className='mt-2 flex flex-wrap gap-2 text-xs text-slate-600'>
            <span className='score-pill score-pill-neutral'>cyan: top ticker share</span>
            <span className='score-pill score-pill-neutral'>black dashed: HHI</span>
            <span className='score-pill score-pill-neutral'>violet: 7d momentum (rescaled)</span>
            <span className='score-pill score-pill-neutral'>+momentum days {positiveMomentumDays}, -momentum days {negativeMomentumDays}</span>
          </div>
        </div>
      </div>

      <div className='grid gap-4 xl:grid-cols-[1.15fr_0.85fr]'>
        <div className='panel p-4'>
          <h3 className='display mb-3 text-lg font-semibold text-slate-900'>
            <HintLabel label='Regime Timeline' hint='Tag-fuer-Tag Regimeklassifikation anhand weighted Score: >= 0.15 risk-on, <= -0.15 risk-off.' />
          </h3>
          <div className='space-y-3'>
            <svg viewBox={`0 0 ${CHART_W} 82`} className='h-20 w-full'>
              {trend.map((point, idx) => {
                const width = PLOT_W / Math.max(trend.length, 1);
                const x = PAD_X + idx * width;
                return (
                  <rect
                    key={`rg-${point.date_bucket_berlin}-${idx}`}
                    x={x}
                    y='18'
                    width={Math.max(width - 1.2, 1)}
                    height='24'
                    fill={regimeColor(point.weighted_score)}
                  >
                    <title>{`${point.date_bucket_berlin}: ${formatScore(point.weighted_score)}`}</title>
                  </rect>
                );
              })}
              <text x={PAD_X} y='58' fontSize='10' fill='rgba(17,33,45,0.6)'>{shortDate(trend[0]?.date_bucket_berlin || '')}</text>
              <text x={CHART_W - PAD_X - 28} y='58' fontSize='10' fill='rgba(17,33,45,0.6)'>{shortDate(trend[trend.length - 1]?.date_bucket_berlin || '')}</text>
            </svg>

            <div className='grid gap-2 sm:grid-cols-3'>
              <div className='metric-card'>
                <p className='eyebrow'>risk-on</p>
                <p className='display mt-1 text-xl font-bold text-slate-900'>
                  {analytics.regime_breakdown.risk_on_days} ({formatPct(analytics.regime_breakdown.risk_on_share)})
                </p>
              </div>
              <div className='metric-card'>
                <p className='eyebrow'>balanced</p>
                <p className='display mt-1 text-xl font-bold text-slate-900'>
                  {analytics.regime_breakdown.balanced_days} ({formatPct(analytics.regime_breakdown.balanced_share)})
                </p>
              </div>
              <div className='metric-card'>
                <p className='eyebrow'>risk-off</p>
                <p className='display mt-1 text-xl font-bold text-slate-900'>
                  {analytics.regime_breakdown.risk_off_days} ({formatPct(analytics.regime_breakdown.risk_off_share)})
                </p>
              </div>
            </div>

            <div className='flex flex-wrap gap-2 text-xs text-slate-600'>
              <span className='score-pill score-pill-neutral'>regime switches: {analytics.regime_breakdown.regime_switches}</span>
              <span className={regimeTone(analytics.regime_breakdown.current_regime)}>current: {analytics.regime_breakdown.current_regime}</span>
            </div>
          </div>
        </div>

        <div className='panel p-4'>
          <h3 className='display mb-3 text-lg font-semibold text-slate-900'>
            <HintLabel label='Weekday Fingerprint' hint='Mittlere Marktstimmung und Volumen nach Wochentag (nur aktive Tage).' />
          </h3>
          <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} className='h-56 w-full'>
            {[0, 1, 2, 3, 4, 5, 6].map((idx) => {
              const x = xAt(idx, 7);
              return <line key={`wf-${idx}`} x1={x} y1={PAD_TOP} x2={x} y2={CHART_H - PAD_BOTTOM} stroke='rgba(15,23,32,0.06)' />;
            })}
            <line x1={PAD_X} y1={yScore(0)} x2={CHART_W - PAD_X} y2={yScore(0)} stroke='rgba(15,23,32,0.2)' />
            {analytics.weekday_profile.map((row, idx) => {
              const x = xAt(idx, 7);
              const y = yScore(row.avg_weighted_score);
              const zeroY = yScore(0);
              const barY = Math.min(y, zeroY);
              const barH = Math.abs(zeroY - y);
              const mentionY = yShare(row.avg_mentions / maxWeekdayMentions);
              return (
                <g key={`wd-${row.weekday}`}>
                  <rect
                    x={x - 13}
                    y={barY}
                    width='26'
                    height={Math.max(barH, 2)}
                    fill={row.avg_weighted_score >= 0 ? 'rgba(13,148,104,0.6)' : 'rgba(194,72,72,0.6)'}
                  >
                    <title>{`${row.label}: score ${formatScore(row.avg_weighted_score)}, avg mentions ${row.avg_mentions.toFixed(1)}, samples ${row.samples}`}</title>
                  </rect>
                  <circle cx={x} cy={mentionY} r='3.2' fill='rgba(23,105,229,0.9)' />
                  <text x={x - 8} y={CHART_H - 8} fontSize='10' fill='rgba(17,33,45,0.66)'>{row.label}</text>
                </g>
              );
            })}
            <path d={linePath(analytics.weekday_profile.map((row) => row.avg_mentions / maxWeekdayMentions), yShare)} stroke='rgba(23,105,229,0.7)' strokeWidth='2' fill='none' />
          </svg>
          <div className='mt-2 flex flex-wrap gap-2 text-xs text-slate-600'>
            <span className='score-pill score-pill-positive'>green/red bars: avg score</span>
            <span className='score-pill score-pill-neutral'>blue line: normalized avg mentions</span>
          </div>
        </div>
      </div>

      <div className='grid gap-4 xl:grid-cols-[1.1fr_0.9fr]'>
        <div className='panel p-4'>
          <h3 className='display mb-3 text-lg font-semibold text-slate-900'>
            <HintLabel label='Ticker Leadership Matrix' hint='Dominante Ticker im Fenster mit Anteil, Momentum und Unsicherheit.' />
          </h3>
          <div className='overflow-x-auto'>
            <table className='min-w-full text-xs'>
              <thead className='text-left text-slate-600'>
                <tr>
                  <th className='px-2 py-1.5 font-semibold'>Ticker</th>
                  <th className='px-2 py-1.5 font-semibold'>Share</th>
                  <th className='px-2 py-1.5 font-semibold'>Avg Score</th>
                  <th className='px-2 py-1.5 font-semibold'>Momentum</th>
                  <th className='px-2 py-1.5 font-semibold'>Vol</th>
                  <th className='px-2 py-1.5 font-semibold'>Unclear</th>
                </tr>
              </thead>
              <tbody>
                {analytics.ticker_insights.slice(0, 12).map((row) => (
                  <tr key={`ti-${row.ticker}`} className='border-t border-slate-200/80'>
                    <td className='px-2 py-1.5 font-semibold text-slate-800'>
                      {row.ticker}
                      <span className='ml-1 text-[10px] text-slate-500'>({row.mention_count})</span>
                    </td>
                    <td className='px-2 py-1.5'>
                      <div className='h-2.5 w-24 rounded-full bg-slate-200/80'>
                        <div className='h-2.5 rounded-full bg-gradient-to-r from-cyan-500 to-blue-600' style={{ width: `${Math.max(row.mention_share * 100, 3)}%` }} />
                      </div>
                    </td>
                    <td className='px-2 py-1.5'><span className={tone(row.avg_weighted_score)}>{formatScore(row.avg_weighted_score)}</span></td>
                    <td className='px-2 py-1.5'><span className={tone(row.momentum)}>{formatScore(row.momentum)}</span></td>
                    <td className='px-2 py-1.5 text-slate-700'>{formatScore(row.score_volatility)}</td>
                    <td className='px-2 py-1.5 text-slate-700'>{formatPct(row.unclear_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!analytics.ticker_insights.length ? (
            <p className='pt-2 text-sm text-slate-500'>No ticker insight data yet.</p>
          ) : null}
        </div>

        <div className='panel p-4'>
          <h3 className='display mb-3 text-lg font-semibold text-slate-900'>
            <HintLabel label='Subreddit Snapshot' hint='Vergleich der Subreddits am letzten Tag im Analysefenster.' />
          </h3>
          <div className='space-y-2.5'>
            {analytics.subreddit_snapshot.slice(0, 10).map((row) => (
              <div key={row.subreddit} className='grid grid-cols-[110px_1fr_72px_72px] items-center gap-2 text-xs'>
                <span className='font-semibold text-slate-700'>r/{row.subreddit}</span>
                <div className='h-2.5 rounded-full bg-slate-200/75'>
                  <div
                    className='h-2.5 rounded-full bg-gradient-to-r from-blue-500 to-cyan-400'
                    style={{ width: `${Math.max((row.mention_count / maxSubredditMentions) * 100, 3)}%` }}
                  />
                </div>
                <span className='text-right font-semibold text-slate-800'>{row.mention_count}</span>
                <span className={tone(row.weighted_score)}>{formatScore(row.weighted_score)}</span>
              </div>
            ))}
            {!analytics.subreddit_snapshot.length ? (
              <p className='text-sm text-slate-500'>No subreddit snapshot available.</p>
            ) : null}
          </div>
        </div>
      </div>

      <div className='grid gap-4 xl:grid-cols-2'>
        <div className='panel p-4'>
          <h3 className='display mb-3 text-lg font-semibold text-slate-900'>
            <HintLabel label='Top Movers Up' hint='Ticker mit der staerksten Verbesserung des weighted Scores vs. Vortag.' />
          </h3>
          <div className='space-y-2'>
            {analytics.top_movers_up.map((row) => (
              <div key={`up-${row.ticker}`} className='grid grid-cols-[72px_64px_64px_64px] items-center gap-2 text-xs'>
                <span className='font-semibold text-slate-800'>{row.ticker}</span>
                <span className={tone(row.score_delta)}>{formatScore(row.score_delta)}</span>
                <span className='text-slate-700'>{row.current_mentions} m</span>
                <span className='text-slate-600'>dM {row.mention_delta >= 0 ? `+${row.mention_delta}` : row.mention_delta}</span>
              </div>
            ))}
            {!analytics.top_movers_up.length ? <p className='text-sm text-slate-500'>No mover data yet.</p> : null}
          </div>
        </div>

        <div className='panel p-4'>
          <h3 className='display mb-3 text-lg font-semibold text-slate-900'>
            <HintLabel label='Top Movers Down' hint='Ticker mit der staerksten Verschlechterung des weighted Scores vs. Vortag.' />
          </h3>
          <div className='space-y-2'>
            {analytics.top_movers_down.map((row) => (
              <div key={`down-${row.ticker}`} className='grid grid-cols-[72px_64px_64px_64px] items-center gap-2 text-xs'>
                <span className='font-semibold text-slate-800'>{row.ticker}</span>
                <span className={tone(row.score_delta)}>{formatScore(row.score_delta)}</span>
                <span className='text-slate-700'>{row.current_mentions} m</span>
                <span className='text-slate-600'>dM {row.mention_delta >= 0 ? `+${row.mention_delta}` : row.mention_delta}</span>
              </div>
            ))}
            {!analytics.top_movers_down.length ? <p className='text-sm text-slate-500'>No mover data yet.</p> : null}
          </div>
        </div>
      </div>
    </section>
  );
}
