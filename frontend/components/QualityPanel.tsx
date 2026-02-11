import { formatPct } from '@/lib/format';
import HintLabel from '@/components/HintLabel';
import type { QualityResponse } from '@/lib/types';

type Props = {
  quality: QualityResponse;
};

export default function QualityPanel({ quality }: Props) {
  const coverageLabel =
    quality.parsed_comment_coverage === null ? 'n/a' : formatPct(quality.parsed_comment_coverage);

  return (
    <section className='panel fade-up p-5 sm:p-6'>
      <div className='mb-4 flex flex-wrap items-center justify-between gap-2'>
        <h2 className='display text-2xl font-bold text-slate-900'>Data Quality</h2>
        <span className='score-pill score-pill-neutral'>{quality.subreddit}</span>
      </div>

      <div className='grid gap-3 sm:grid-cols-3'>
        <article className='metric-card'>
          <p className='eyebrow'>
            <HintLabel label='Pull Success' hint='Erfolgreiche Pull-Runs / alle Pull-Runs fuer den Filter.' />
          </p>
          <p className='display mt-1 text-2xl font-bold text-slate-900'>
            {quality.pulls_success}/{quality.pulls_total}
          </p>
        </article>
        <article className='metric-card'>
          <p className='eyebrow'>
            <HintLabel label='Comment Coverage' hint='Geparste Kommentare / von Reddit gemeldete Kommentaranzahl.' />
          </p>
          <p className='display mt-1 text-2xl font-bold text-slate-900'>{coverageLabel}</p>
        </article>
        <article className='metric-card'>
          <p className='eyebrow'>
            <HintLabel label='Context Share' hint='Anteil Mentions, die nur aus Kontext-Vererbung stammen.' />
          </p>
          <p className='display mt-1 text-2xl font-bold text-slate-900'>{formatPct(quality.context_mention_rate)}</p>
        </article>
      </div>

      <div className='mt-4 grid gap-3 sm:grid-cols-2'>
        <div className='line-section'>
          <p className='eyebrow mb-2'>Model Versions</p>
          <div className='flex flex-wrap gap-2'>
            {quality.model_versions.map((row) => (
              <span key={row.model_version} className='score-pill score-pill-neutral'>
                {row.model_version}: {row.count}
              </span>
            ))}
          </div>
        </div>
        <div className='line-section'>
          <p className='eyebrow mb-2'>Mention Sources</p>
          <div className='flex flex-wrap gap-2'>
            {quality.mention_sources.map((row) => (
              <span key={row.source} className='score-pill score-pill-neutral'>
                {row.source}: {row.count}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
