import type { SubredditsResponse } from '@/lib/types';

type Props = {
  subreddits: SubredditsResponse['subreddits'];
  selectedSubreddit: string;
  selectedDate: string;
};

export default function FiltersBar({ subreddits, selectedSubreddit, selectedDate }: Props) {
  return (
    <form method='GET' className='panel fade-up mb-2 grid gap-4 p-4 sm:p-5 md:grid-cols-[1fr_1fr_auto] md:items-end'>
      <label className='space-y-1 text-sm'>
        <span className='eyebrow'>Date</span>
        <input type='date' name='date' defaultValue={selectedDate} className='field' />
      </label>

      <label className='space-y-1 text-sm'>
        <span className='eyebrow'>Subreddit</span>
        <select name='subreddit' defaultValue={selectedSubreddit} className='field'>
          <option value='ALL'>All subreddits</option>
          {subreddits.map((s) => (
            <option key={s} value={s}>
              r/{s}
            </option>
          ))}
        </select>
      </label>

      <div className='flex md:justify-end'>
        <button type='submit' className='btn-main w-full md:w-auto'>
          Refresh View
        </button>
      </div>
    </form>
  );
}
