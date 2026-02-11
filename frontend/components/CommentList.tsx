import ContextToggle from '@/components/ContextToggle';
import type { ThreadComment } from '@/lib/types';

type Props = {
  comments: ThreadComment[];
};

function badgeClass(label: ThreadComment['stance'][number]['stance_label']): string {
  if (label === 'BULLISH') return 'score-pill score-pill-positive';
  if (label === 'BEARISH') return 'score-pill score-pill-negative';
  if (label === 'NEUTRAL') return 'score-pill score-pill-neutral';
  return 'score-pill score-pill-neutral';
}

export default function CommentList({ comments }: Props) {
  if (!comments.length) {
    return <div className='line-section py-4 text-sm text-slate-600'>No comments parsed.</div>;
  }

  return (
    <div className='thread-lane space-y-3 pl-3 sm:pl-4'>
      {comments.map((comment) => (
        <article
          key={comment.id}
          className='fade-up space-y-3 border-b border-slate-200 pb-4'
          style={{ marginLeft: `${Math.min(comment.depth, 6) * 14}px` }}
        >
          <div className='flex flex-wrap items-center gap-2 text-xs'>
            <span className='score-pill score-pill-neutral' title='Comment-Autor (falls nicht geloescht).'>
              {comment.author || '[deleted]'}
            </span>
            <span className='score-pill score-pill-neutral' title='Reddit-Score fuer diesen Kommentar.'>score {comment.score}</span>
            <span className='score-pill score-pill-neutral' title='Tiefe im Kommentarbaum (0 = Top-Level).'>depth {comment.depth}</span>
            {comment.stance.map((s, idx) => (
              <span
                key={`${comment.id}-${s.ticker}-${s.stance_label}-${idx}`}
                className={badgeClass(s.stance_label)}
                title='Ticker + klassifiziertes Stance-Label fuer diesen Kommentar.'
              >
                {s.ticker} {s.stance_label}
              </span>
            ))}
          </div>

          <p className='whitespace-pre-wrap text-sm leading-relaxed text-slate-800'>{comment.body}</p>

          <div className='flex flex-wrap items-center gap-2 text-xs text-slate-500'>
            {comment.stance.map((s, idx) => (
              <ContextToggle key={`${comment.id}-${s.ticker}-ctx-${idx}`} context={s.context_text} />
            ))}
            {comment.permalink ? <span className='truncate'>permalink: {comment.permalink}</span> : null}
          </div>
        </article>
      ))}
    </div>
  );
}
