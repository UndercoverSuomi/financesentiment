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


class DailyScoreOut(BaseModel):
    date_bucket_berlin: date
    subreddit: str
    ticker: str
    score_unweighted: float
    score_weighted: float
    mention_count: int
    bullish_count: int
    bearish_count: int
    neutral_count: int
    unclear_count: int
    unclear_rate: float


class ResultsResponse(BaseModel):
    date_bucket_berlin: date
    subreddit: str
    rows: list[DailyScoreOut]


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
