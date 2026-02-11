import type { SubredditsResponse } from '@/lib/types';

type Props = {
  subreddits: SubredditsResponse['subreddits'];
  selectedSubreddit: string;
  selectedDate: string;
  selectedResultsWindow: '24h' | '7d';
  selectedAnalyticsDays: number;
};

export default function FiltersBar({
  subreddits,
  selectedSubreddit,
  selectedDate,
  selectedResultsWindow,
  selectedAnalyticsDays,
}: Props) {
  return (
    <form method='GET' className='panel fade-up mb-2 grid gap-4 p-4 sm:p-5 md:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_1fr_auto] md:items-end'>
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

      <label className='space-y-1 text-sm'>
        <span className='eyebrow'>Data Window</span>
        <select name='window' defaultValue={selectedResultsWindow} className='field'>
          <option value='24h'>Last 24h</option>
          <option value='7d'>Last 7 days</option>
        </select>
      </label>

      <label className='space-y-1 text-sm'>
        <span className='eyebrow'>Analytics Window</span>
        <select name='analytics_days' defaultValue={String(selectedAnalyticsDays)} className='field'>
          <option value='14'>14 days</option>
          <option value='21'>21 days</option>
          <option value='30'>30 days</option>
          <option value='60'>60 days</option>
          <option value='90'>90 days</option>
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
