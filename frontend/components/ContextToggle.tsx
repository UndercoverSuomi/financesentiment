'use client';

import { useState } from 'react';

type Props = {
  context: string;
};

export default function ContextToggle({ context }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button
        type='button'
        onClick={() => setOpen((v) => !v)}
        className='score-pill score-pill-neutral border border-slate-200 transition hover:bg-slate-100'
      >
        {open ? 'Hide context' : 'Show context'}
      </button>
      {open ? <pre className='context-box mt-2 whitespace-pre-wrap'>{context}</pre> : null}
    </div>
  );
}
