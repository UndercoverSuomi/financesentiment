type Props = {
  label: string;
  hint: string;
  className?: string;
};

export default function HintLabel({ label, hint, className }: Props) {
  return (
    <span className={className ?? ''}>
      {label}
      <span
        className='ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full border border-slate-300 text-[10px] text-slate-500'
        title={hint}
        aria-label={hint}
      >
        i
      </span>
    </span>
  );
}
