export type DailyScore = {
  date_bucket_berlin: string;
  subreddit: string;
  ticker: string;
  score_unweighted: number;
  score_weighted: number;
  score_stddev_unweighted: number;
  ci95_low_unweighted: number;
  ci95_high_unweighted: number;
  valid_count: number;
  mention_count: number;
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
  unclear_count: number;
  unclear_rate: number;
};

export type ResultsResponse = {
  date_bucket_berlin: string;
  date_from: string;
  date_to: string;
  window: '24h' | '7d';
  subreddit: string;
  rows: DailyScore[];
};

export type ModelVersionCount = {
  model_version: string;
  count: number;
};

export type MentionSourceCount = {
  source: string;
  count: number;
};

export type EvaluationLabelMetrics = {
  label: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNCLEAR';
  support: number;
  precision: number;
  recall: number;
  f1: number;
  tp: number;
  fp: number;
  fn: number;
};

export type EvaluationConfusionCell = {
  actual: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNCLEAR';
  predicted: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNCLEAR';
  count: number;
};

export type EvaluationErrorExample = {
  row_id: number;
  ticker: string;
  actual: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNCLEAR';
  predicted: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNCLEAR';
  confidence: number;
  source: string;
  text: string;
};

export type EvaluationResponse = {
  dataset_path: string;
  rows_evaluated: number;
  accuracy: number;
  macro_f1: number;
  weighted_f1: number;
  expected_calibration_error: number;
  direct_detection_rate: number;
  context_inference_rate: number;
  missing_prediction_rate: number;
  model_versions: ModelVersionCount[];
  per_label: EvaluationLabelMetrics[];
  confusion: EvaluationConfusionCell[];
  error_examples: EvaluationErrorExample[];
};

export type QualityResponse = {
  date_bucket_berlin: string;
  subreddit: string;
  pulls_total: number;
  pulls_success: number;
  pulls_failed: number;
  submissions: number;
  reddit_reported_comments: number;
  parsed_comments: number;
  parsed_comment_coverage: number | null;
  mentions_total: number;
  context_mentions: number;
  context_mention_rate: number;
  unclear_count: number;
  unclear_rate: number;
  model_versions: ModelVersionCount[];
  mention_sources: MentionSourceCount[];
};

export type AnalyticsDayPoint = {
  date_bucket_berlin: string;
  weighted_score: number;
  unweighted_score: number;
  mention_count: number;
  valid_count: number;
  unclear_rate: number;
  bullish_share: number;
  bearish_share: number;
  neutral_share: number;
  concentration_hhi: number;
  top_ticker_share: number;
};

export type AnalyticsMarketSummary = {
  avg_weighted_score: number;
  score_volatility: number;
  avg_unclear_rate: number;
  avg_valid_ratio: number;
  avg_bullish_share: number;
  avg_bearish_share: number;
  avg_neutral_share: number;
  avg_concentration_hhi: number;
  avg_top_ticker_share: number;
  effective_ticker_count: number;
  active_days: number;
  total_mentions: number;
  score_trend_slope: number;
  mention_trend_slope: number;
};

export type AnalyticsRollingPoint = {
  date_bucket_berlin: string;
  weighted_score: number;
  weighted_ma7: number;
  weighted_ma14: number;
  mention_count: number;
  mentions_ma7: number;
  unclear_rate: number;
  unclear_ma7: number;
  volatility_ma7: number;
  momentum_7d: number;
};

export type AnalyticsMover = {
  ticker: string;
  current_mentions: number;
  current_weighted_score: number;
  previous_weighted_score: number;
  score_delta: number;
  mention_delta: number;
};

export type AnalyticsSubredditPoint = {
  subreddit: string;
  mention_count: number;
  weighted_score: number;
  unclear_rate: number;
  bullish_share: number;
  bearish_share: number;
  neutral_share: number;
};

export type AnalyticsRegimeBreakdown = {
  risk_on_days: number;
  balanced_days: number;
  risk_off_days: number;
  risk_on_share: number;
  balanced_share: number;
  risk_off_share: number;
  regime_switches: number;
  current_regime: string;
};

export type AnalyticsCorrelation = {
  mentions_vs_abs_score: number;
  unclear_vs_abs_score: number;
  concentration_vs_unclear: number;
};

export type AnalyticsTickerInsight = {
  ticker: string;
  mention_count: number;
  mention_share: number;
  avg_weighted_score: number;
  score_volatility: number;
  latest_score: number;
  previous_score: number;
  momentum: number;
  active_days: number;
  unclear_rate: number;
};

export type AnalyticsWeekdayPoint = {
  weekday: number;
  label: string;
  avg_weighted_score: number;
  avg_mentions: number;
  avg_unclear_rate: number;
  samples: number;
};

export type AnalyticsResponse = {
  subreddit: string;
  days: number;
  date_from: string;
  date_to: string;
  trend: AnalyticsDayPoint[];
  rolling_trend: AnalyticsRollingPoint[];
  market_summary: AnalyticsMarketSummary;
  regime_breakdown: AnalyticsRegimeBreakdown;
  correlations: AnalyticsCorrelation;
  top_movers_up: AnalyticsMover[];
  top_movers_down: AnalyticsMover[];
  ticker_insights: AnalyticsTickerInsight[];
  weekday_profile: AnalyticsWeekdayPoint[];
  subreddit_snapshot: AnalyticsSubredditPoint[];
};

export type SubredditsResponse = {
  subreddits: string[];
  default_sort: string;
  default_t_param: string;
  default_limit: number;
};

export type PullSummary = {
  pull_run_id: number;
  subreddit: string;
  date_bucket_berlin: string;
  status: string;
  submissions: number;
  comments: number;
  mentions: number;
  stance_rows: number;
  error: string | null;
};

export type PullRunStatus = {
  subreddit: string;
  status: string;
  pulled_at_utc: string;
  date_bucket_berlin: string;
  error: string | null;
};

export type PullStatusOverview = {
  generated_at_utc: string;
  overall_last_success_utc: string | null;
  running_subreddits: string[];
  failed_subreddits: string[];
  subreddits_without_success: string[];
  latest_by_subreddit: PullRunStatus[];
  last_success_by_subreddit: PullRunStatus[];
};

export type PullJobStatus = {
  job_id: string;
  mode: string;
  requested_subreddit: string | null;
  status: string;
  started_at_utc: string;
  finished_at_utc: string | null;
  total_steps: number;
  completed_steps: number;
  progress: number;
  current_subreddit: string | null;
  current_phase: string | null;
  current_subreddit_progress: number;
  current_total_submissions: number | null;
  current_processed_submissions: number;
  current_submission_id: string | null;
  current_submissions: number;
  current_comments: number;
  current_mentions: number;
  current_stance_rows: number;
  current_partial_errors: number;
  heartbeat_utc: string | null;
  summaries: PullSummary[];
  error: string | null;
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
