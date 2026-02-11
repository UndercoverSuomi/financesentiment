type Props = {
  title: string;
  message: string;
};

export default function ErrorState({ title, message }: Props) {
  return (
    <section className='error-state fade-up'>
      <p className='eyebrow'>{title}</p>
      <p className='mt-2 text-sm leading-relaxed text-slate-700 sm:text-base'>{message}</p>
    </section>
  );
}
