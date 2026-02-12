from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.common import StanceLabel


class SubredditsResponse(BaseModel):
    subreddits: list[str]
    default_sort: str
    default_t_param: str
    default_limit: int


class PullSummary(BaseModel):
    pull_run_id: int
    subreddit: str
    date_bucket_berlin: date
    status: str
    submissions: int
    comments: int
    mentions: int
    stance_rows: int
    error: str | None = None


class PullRunStatusOut(BaseModel):
    subreddit: str
    status: str
    pulled_at_utc: datetime
    date_bucket_berlin: date
    error: str | None = None


class PullStatusOverview(BaseModel):
    generated_at_utc: datetime
    overall_last_success_utc: datetime | None
    running_subreddits: list[str]
    failed_subreddits: list[str]
    subreddits_without_success: list[str]
    latest_by_subreddit: list[PullRunStatusOut]
    last_success_by_subreddit: list[PullRunStatusOut]


class PullJobStatus(BaseModel):
    job_id: str
    mode: str
    requested_subreddit: str | None
    status: str
    started_at_utc: datetime
    finished_at_utc: datetime | None
    total_steps: int
    completed_steps: int
    progress: float
    current_subreddit: str | None
    current_phase: str | None = None
    current_subreddit_progress: float = 0.0
    current_total_submissions: int | None = None
    current_processed_submissions: int = 0
    current_submission_id: str | None = None
    current_submissions: int = 0
    current_comments: int = 0
    current_mentions: int = 0
    current_stance_rows: int = 0
    current_partial_errors: int = 0
    heartbeat_utc: datetime | None = None
    summaries: list[PullSummary]
    error: str | None = None


class DailyScoreOut(BaseModel):
    date_bucket_berlin: date
    subreddit: str
    ticker: str
    score_unweighted: float
    score_weighted: float
    score_stddev_unweighted: float
    ci95_low_unweighted: float
    ci95_high_unweighted: float
    valid_count: int
    mention_count: int
    bullish_count: int
    bearish_count: int
    neutral_count: int
    unclear_count: int
    unclear_rate: float


class ResultsResponse(BaseModel):
    date_bucket_berlin: date
    date_from: date
    date_to: date
    window: str
    subreddit: str
    rows: list[DailyScoreOut]


class ModelVersionCount(BaseModel):
    model_version: str
    count: int


class MentionSourceCount(BaseModel):
    source: str
    count: int


class QualityResponse(BaseModel):
    date_bucket_berlin: date
    subreddit: str
    pulls_total: int
    pulls_success: int
    pulls_failed: int
    submissions: int
    reddit_reported_comments: int
    parsed_comments: int
    parsed_comment_coverage: float | None
    mentions_total: int
    context_mentions: int
    context_mention_rate: float
    unclear_count: int
    unclear_rate: float
    model_versions: list[ModelVersionCount]
    mention_sources: list[MentionSourceCount]


class AnalyticsMarketSummary(BaseModel):
    avg_weighted_score: float
    score_volatility: float
    avg_unclear_rate: float
    avg_valid_ratio: float
    avg_bullish_share: float
    avg_bearish_share: float
    avg_neutral_share: float
    avg_concentration_hhi: float
    avg_top_ticker_share: float
    effective_ticker_count: float
    active_days: int
    total_mentions: int
    score_trend_slope: float
    mention_trend_slope: float


class AnalyticsDayPoint(BaseModel):
    date_bucket_berlin: date
    weighted_score: float
    unweighted_score: float
    mention_count: int
    valid_count: int
    unclear_rate: float
    bullish_share: float
    bearish_share: float
    neutral_share: float
    concentration_hhi: float
    top_ticker_share: float


class AnalyticsRollingPoint(BaseModel):
    date_bucket_berlin: date
    weighted_score: float
    weighted_ma7: float
    weighted_ma14: float
    mention_count: int
    mentions_ma7: float
    unclear_rate: float
    unclear_ma7: float
    volatility_ma7: float
    momentum_7d: float


class AnalyticsMover(BaseModel):
    ticker: str
    current_mentions: int
    current_weighted_score: float
    previous_weighted_score: float
    score_delta: float
    mention_delta: int


class AnalyticsSubredditPoint(BaseModel):
    subreddit: str
    mention_count: int
    weighted_score: float
    unclear_rate: float
    bullish_share: float
    bearish_share: float
    neutral_share: float


class AnalyticsRegimeBreakdown(BaseModel):
    risk_on_days: int
    balanced_days: int
    risk_off_days: int
    risk_on_share: float
    balanced_share: float
    risk_off_share: float
    regime_switches: int
    current_regime: str


class AnalyticsCorrelation(BaseModel):
    mentions_vs_abs_score: float
    unclear_vs_abs_score: float
    concentration_vs_unclear: float


class AnalyticsTickerInsight(BaseModel):
    ticker: str
    mention_count: int
    mention_share: float
    avg_weighted_score: float
    score_volatility: float
    latest_score: float
    previous_score: float
    momentum: float
    active_days: int
    unclear_rate: float


class AnalyticsWeekdayPoint(BaseModel):
    weekday: int
    label: str
    avg_weighted_score: float
    avg_mentions: float
    avg_unclear_rate: float
    samples: int


class AnalyticsResponse(BaseModel):
    subreddit: str
    days: int
    date_from: date
    date_to: date
    trend: list[AnalyticsDayPoint]
    rolling_trend: list[AnalyticsRollingPoint]
    market_summary: AnalyticsMarketSummary
    regime_breakdown: AnalyticsRegimeBreakdown
    correlations: AnalyticsCorrelation
    top_movers_up: list[AnalyticsMover]
    top_movers_down: list[AnalyticsMover]
    ticker_insights: list[AnalyticsTickerInsight]
    weekday_profile: list[AnalyticsWeekdayPoint]
    subreddit_snapshot: list[AnalyticsSubredditPoint]


class EvaluationLabelMetrics(BaseModel):
    label: StanceLabel
    support: int
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int


class EvaluationConfusionCell(BaseModel):
    actual: StanceLabel
    predicted: StanceLabel
    count: int


class EvaluationErrorExample(BaseModel):
    row_id: int
    ticker: str
    actual: StanceLabel
    predicted: StanceLabel
    confidence: float
    source: str
    text: str


class EvaluationResponse(BaseModel):
    dataset_path: str
    rows_evaluated: int
    accuracy: float
    macro_f1: float
    weighted_f1: float
    expected_calibration_error: float
    direct_detection_rate: float
    context_inference_rate: float
    missing_prediction_rate: float
    model_versions: list[ModelVersionCount]
    per_label: list[EvaluationLabelMetrics]
    confusion: list[EvaluationConfusionCell]
    error_examples: list[EvaluationErrorExample]


class TickerPoint(BaseModel):
    date_bucket_berlin: date
    score_unweighted: float
    score_weighted: float
    mention_count: int
    unclear_rate: float


class CommentExample(BaseModel):
    id: str
    submission_id: str
    body: str
    score: int
    permalink: str
    stance_label: StanceLabel
    stance_score: float


class TickerSeriesResponse(BaseModel):
    ticker: str
    subreddit: str | None
    days: int
    series: list[TickerPoint]
    bullish_examples: list[CommentExample]
    bearish_examples: list[CommentExample]


class MentionOut(BaseModel):
    ticker: str
    confidence: float
    source: str
    span_start: int
    span_end: int


class StanceOut(BaseModel):
    ticker: str
    stance_label: StanceLabel
    stance_score: float
    confidence: float
    model_version: str
    context_text: str


class CommentThreadOut(BaseModel):
    id: str
    submission_id: str
    parent_id: str | None
    depth: int
    author: str | None
    created_utc: datetime
    score: int
    body: str
    permalink: str
    mentions: list[MentionOut]
    stance: list[StanceOut]


class SubmissionOut(BaseModel):
    id: str
    subreddit: str
    created_utc: datetime
    title: str
    selftext: str
    url: str
    score: int
    num_comments: int
    permalink: str
    mentions: list[MentionOut]
    stance: list[StanceOut]


class ThreadResponse(BaseModel):
    submission: SubmissionOut
    comments: list[CommentThreadOut]
