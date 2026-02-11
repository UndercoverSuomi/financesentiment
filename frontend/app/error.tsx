'use client';

type Props = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function GlobalError({ error, reset }: Props) {
  return (
    <main className='space-y-4 py-8'>
      <section className='error-state'>
        <p className='eyebrow'>Unexpected Error</p>
        <p className='mt-2 text-sm text-slate-700 sm:text-base'>{error.message || 'Etwas ist schiefgelaufen.'}</p>
        <button type='button' onClick={() => reset()} className='btn-main mt-4'>
          Retry
        </button>
      </section>
    </main>
  );
}
