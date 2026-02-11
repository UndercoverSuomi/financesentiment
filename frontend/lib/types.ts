export type DailyScore = {
  date_bucket_berlin: string;
  subreddit: string;
  ticker: string;
  score_unweighted: number;
  score_weighted: number;
  mention_count: number;
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
  unclear_count: number;
  unclear_rate: number;
};

export type ResultsResponse = {
  date_bucket_berlin: string;
  subreddit: string;
  rows: DailyScore[];
};

export type SubredditsResponse = {
  subreddits: string[];
  default_sort: string;
  default_t_param: string;
  default_limit: number;
};

export type TickerPoint = {
  date_bucket_berlin: string;
  score_unweighted: number;
  score_weighted: number;
  mention_count: number;
  unclear_rate: number;
};

export type CommentExample = {
  id: string;
  submission_id: string;
  body: string;
  score: number;
  permalink: string;
  stance_label: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNCLEAR';
  stance_score: number;
};

export type TickerSeriesResponse = {
  ticker: string;
  subreddit: string | null;
  days: number;
  series: TickerPoint[];
  bullish_examples: CommentExample[];
  bearish_examples: CommentExample[];
};

export type Mention = {
  ticker: string;
  confidence: number;
  source: string;
  span_start: number;
  span_end: number;
};

export type Stance = {
  ticker: string;
  stance_label: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNCLEAR';
  stance_score: number;
  confidence: number;
  model_version: string;
  context_text: string;
};

export type ThreadComment = {
  id: string;
  submission_id: string;
  parent_id: string | null;
  depth: number;
  author: string | null;
  created_utc: string;
  score: number;
  body: string;
  permalink: string;
  mentions: Mention[];
  stance: Stance[];
};

export type ThreadResponse = {
  submission: {
    id: string;
    subreddit: string;
    created_utc: string;
    title: string;
    selftext: string;
    url: string;
    score: number;
    num_comments: number;
    permalink: string;
    mentions: Mention[];
    stance: Stance[];
  };
  comments: ThreadComment[];
};
