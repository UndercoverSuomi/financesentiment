import { formatPct } from '@/lib/format';
import HintLabel from '@/components/HintLabel';
import type { EvaluationResponse } from '@/lib/types';

type Props = {
  evaluation: EvaluationResponse;
};

const LABELS: Array<'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNCLEAR'> = ['BULLISH', 'BEARISH', 'NEUTRAL', 'UNCLEAR'];

function confusionCount(
  evaluation: EvaluationResponse,
  actual: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNCLEAR',
  predicted: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNCLEAR',
): number {
  return evaluation.confusion.find((c) => c.actual === actual && c.predicted === predicted)?.count ?? 0;
}

export default function EvaluationPanel({ evaluation }: Props) {
  return (
    <section className='panel fade-up space-y-5 p-5 sm:p-6'>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <h2 className='display text-2xl font-bold text-slate-900'>Model Evaluation</h2>
        <span className='score-pill score-pill-neutral'>{evaluation.rows_evaluated} labeled rows</span>
      </div>

      <div className='grid gap-3 sm:grid-cols-3'>
        <article className='metric-card'>
          <p className='eyebrow'>
            <HintLabel label='Accuracy' hint='Anteil korrekter Vorhersagen ueber alle Labels.' />
          </p>
          <p className='display mt-1 text-2xl font-bold text-slate-900'>{formatPct(evaluation.accuracy)}</p>
        </article>
        <article className='metric-card'>
          <p className='eyebrow'>
            <HintLabel label='Macro F1' hint='F1 je Label, dann ungewichteter Mittelwert.' />
          </p>
          <p className='display mt-1 text-2xl font-bold text-slate-900'>{evaluation.macro_f1.toFixed(3)}</p>
        </article>
        <article className='metric-card'>
          <p className='eyebrow'>
            <HintLabel label='ECE' hint='Expected Calibration Error: Abweichung zwischen Konfidenz und realer Trefferquote.' />
          </p>
          <p className='display mt-1 text-2xl font-bold text-slate-900'>{evaluation.expected_calibration_error.toFixed(3)}</p>
        </article>
      </div>

      <div className='grid gap-4 lg:grid-cols-2'>
        <div className='panel p-4'>
          <p className='eyebrow mb-2'>Per Label Metrics</p>
          <div className='overflow-x-auto'>
            <table className='min-w-full text-xs'>
              <thead className='text-left text-slate-600'>
                <tr>
                  <th className='px-2 py-1.5 font-semibold'>Label</th>
                  <th className='px-2 py-1.5 font-semibold'>Support</th>
                  <th className='px-2 py-1.5 font-semibold'>Precision</th>
                  <th className='px-2 py-1.5 font-semibold'>Recall</th>
                  <th className='px-2 py-1.5 font-semibold'>F1</th>
                </tr>
              </thead>
              <tbody>
                {evaluation.per_label.map((row) => (
                  <tr key={row.label} className='border-t border-slate-200/80'>
                    <td className='px-2 py-1.5 font-semibold text-slate-800'>{row.label}</td>
                    <td className='px-2 py-1.5 text-slate-700'>{row.support}</td>
                    <td className='px-2 py-1.5 text-slate-700'>{row.precision.toFixed(3)}</td>
                    <td className='px-2 py-1.5 text-slate-700'>{row.recall.toFixed(3)}</td>
                    <td className='px-2 py-1.5 text-slate-700'>{row.f1.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className='panel p-4'>
          <p className='eyebrow mb-2'>Confusion Matrix (Actual x Predicted)</p>
          <div className='overflow-x-auto'>
            <table className='min-w-full text-xs'>
              <thead className='text-left text-slate-600'>
                <tr>
                  <th className='px-2 py-1.5 font-semibold'>Actual \\ Pred</th>
                  {LABELS.map((label) => (
                    <th key={label} className='px-2 py-1.5 font-semibold'>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {LABELS.map((actual) => (
                  <tr key={actual} className='border-t border-slate-200/80'>
                    <td className='px-2 py-1.5 font-semibold text-slate-800'>{actual}</td>
                    {LABELS.map((predicted) => (
                      <td key={`${actual}-${predicted}`} className='px-2 py-1.5 text-slate-700'>
                        {confusionCount(evaluation, actual, predicted)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className='grid gap-3 sm:grid-cols-3'>
        <article className='metric-card'>
          <p className='eyebrow'>Direct Detection</p>
          <p className='display mt-1 text-2xl font-bold text-slate-900'>{formatPct(evaluation.direct_detection_rate)}</p>
        </article>
        <article className='metric-card'>
          <p className='eyebrow'>Context Inference</p>
          <p className='display mt-1 text-2xl font-bold text-slate-900'>{formatPct(evaluation.context_inference_rate)}</p>
        </article>
        <article className='metric-card'>
          <p className='eyebrow'>Missing Prediction</p>
          <p className='display mt-1 text-2xl font-bold text-slate-900'>{formatPct(evaluation.missing_prediction_rate)}</p>
        </article>
      </div>

      {evaluation.error_examples.length ? (
        <div className='space-y-2'>
          <p className='eyebrow'>Sample Misclassifications</p>
          {evaluation.error_examples.slice(0, 8).map((row) => (
            <article key={row.row_id} className='metric-card space-y-1'>
              <p className='text-xs text-slate-600'>
                row {row.row_id} | {row.ticker} | {row.actual} {'->'} {row.predicted} | conf {row.confidence.toFixed(3)} | {row.source}
              </p>
              <p className='text-sm text-slate-800'>{row.text}</p>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}
