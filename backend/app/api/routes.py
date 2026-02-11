from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_evaluation_service, get_ingestion_service
from app.core.config import get_settings
from app.models.comment import Comment
from app.models.daily_score import DailyScore
from app.models.mention import Mention
from app.models.pull_run import PullRun
from app.models.stance import Stance
from app.models.submission import Submission
from app.schemas.api import (
    AnalyticsCorrelation,
    AnalyticsDayPoint,
    AnalyticsMarketSummary,
    AnalyticsMover,
    AnalyticsRegimeBreakdown,
    AnalyticsResponse,
    AnalyticsRollingPoint,
    AnalyticsSubredditPoint,
    AnalyticsTickerInsight,
    AnalyticsWeekdayPoint,
    CommentExample,
    CommentThreadOut,
    DailyScoreOut,
    EvaluationResponse,
    MentionSourceCount,
    ModelVersionCount,
    PullSummary,
    QualityResponse,
    ResultsResponse,
    StanceOut,
    SubredditsResponse,
    SubmissionOut,
    ThreadResponse,
    TickerPoint,
    TickerSeriesResponse,
)
from app.services.ingestion_service import IngestionService
from app.services.aggregation_service import AggregationRecord, compute_daily_scores
from app.services.evaluation_service import EvaluationService
from app.utils.timezone import BERLIN, to_berlin_date, utc_now

router = APIRouter(prefix='/api', tags=['api'])
settings = get_settings()


@router.get('/subreddits', response_model=SubredditsResponse)
def list_subreddits() -> SubredditsResponse:
    return SubredditsResponse(
        subreddits=settings.subreddits,
        default_sort=settings.pull_sort,
        default_t_param=settings.pull_t_param,
        default_limit=settings.pull_limit,
    )


@router.post('/pull', response_model=PullSummary)
async def pull_subreddit(
    subreddit: str = Query(...),
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> PullSummary:
    if subreddit not in settings.subreddits:
        raise HTTPException(status_code=400, detail=f'Subreddit {subreddit} is not in configured list')
    result = await ingestion_service.pull_subreddit(db, subreddit=subreddit)
    return PullSummary(**result.__dict__)


@router.post('/pull_all', response_model=list[PullSummary])
async def pull_all(
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> list[PullSummary]:
    results = await ingestion_service.pull_all(db)
    return [PullSummary(**r.__dict__) for r in results]


@router.get('/evaluate', response_model=EvaluationResponse)
def evaluate_model(
    dataset_path: str | None = Query(default=None),
    max_rows: int | None = Query(default=None, ge=1, le=100000),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationResponse:
    try:
        report = evaluation_service.evaluate(dataset_path=dataset_path, max_rows=max_rows)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EvaluationResponse.model_validate(report)


@router.get('/results', response_model=ResultsResponse)
def get_results(
    date: str | None = Query(default=None),
    subreddit: str | None = Query(default=None),
    window: str = Query(default='24h'),
    db: Session = Depends(get_db),
) -> ResultsResponse:
    selected_subreddit: str | None = None
    if subreddit and subreddit.strip():
        requested = subreddit.strip()
        if requested.lower() not in {'all', '*'}:
            selected_subreddit = next((s for s in settings.subreddits if s.lower() == requested.lower()), None)
            if selected_subreddit is None:
                raise HTTPException(status_code=400, detail=f'Subreddit {subreddit} is not in configured list')

    if date:
        try:
            end_date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail='date must be YYYY-MM-DD') from exc
    else:
        end_date = to_berlin_date(utc_now())

    normalized_window = (window or '24h').strip().lower()
    if normalized_window not in {'24h', '7d'}:
        raise HTTPException(status_code=400, detail="window must be '24h' or '7d'")
    lookback_days = 1 if normalized_window == '24h' else 7
    start_date = end_date - timedelta(days=lookback_days - 1)
    start_utc, end_utc_exclusive = _berlin_date_range_to_utc(
        start_date=start_date,
        end_date=end_date,
    )

    response_subreddit = selected_subreddit or 'ALL'
    window_rows = _build_results_from_created_window(
        db=db,
        start_utc=start_utc,
        end_utc_exclusive=end_utc_exclusive,
        selected_subreddit=selected_subreddit,
    )
    if window_rows:
        out_rows = window_rows
    else:
        query = select(DailyScore).where(
            DailyScore.date_bucket_berlin >= start_date,
            DailyScore.date_bucket_berlin <= end_date,
        )
        if selected_subreddit:
            query = query.where(DailyScore.subreddit == selected_subreddit)
        elif settings.subreddits:
            query = query.where(DailyScore.subreddit.in_(settings.subreddits))

        rows = db.execute(query).scalars().all()

        if selected_subreddit and lookback_days == 1:
            out_rows = sorted(rows, key=lambda r: (r.mention_count, r.score_weighted), reverse=True)
        else:
            out_rows = _aggregate_daily_rows(
                rows,
                date_bucket=end_date,
                subreddit_label=response_subreddit,
            )

    return ResultsResponse(
        date_bucket_berlin=end_date,
        date_from=start_date,
        date_to=end_date,
        window=normalized_window,
        subreddit=response_subreddit,
        rows=[
            (DailyScoreOut.model_validate(r.__dict__) if isinstance(r, DailyScore) else r)
            for r in out_rows
        ],
    )


@router.get('/quality', response_model=QualityResponse)
def get_quality(
    date: str | None = Query(default=None),
    subreddit: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> QualityResponse:
    selected_subreddit: str | None = None
    if subreddit and subreddit.strip():
        requested = subreddit.strip()
        if requested.lower() not in {'all', '*'}:
            selected_subreddit = next((s for s in settings.subreddits if s.lower() == requested.lower()), None)
            if selected_subreddit is None:
                raise HTTPException(status_code=400, detail=f'Subreddit {subreddit} is not in configured list')

    if date:
        try:
            date_bucket = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail='date must be YYYY-MM-DD') from exc
    else:
        date_bucket = to_berlin_date(utc_now())

    pull_query = select(PullRun.status).where(PullRun.date_bucket_berlin == date_bucket)
    if selected_subreddit:
        pull_query = pull_query.where(PullRun.subreddit == selected_subreddit)
    elif settings.subreddits:
        pull_query = pull_query.where(PullRun.subreddit.in_(settings.subreddits))
    pull_statuses = db.execute(pull_query).scalars().all()

    submission_query = (
        select(Submission.id, Submission.num_comments)
        .join(PullRun, PullRun.id == Submission.pull_run_id)
        .where(PullRun.date_bucket_berlin == date_bucket)
    )
    if selected_subreddit:
        submission_query = submission_query.where(PullRun.subreddit == selected_subreddit)
    elif settings.subreddits:
        submission_query = submission_query.where(PullRun.subreddit.in_(settings.subreddits))

    submission_rows = db.execute(submission_query).all()
    submission_ids = [row[0] for row in submission_rows]
    reddit_reported_comments = sum(int(row[1] or 0) for row in submission_rows)

    if submission_ids:
        parsed_comments = int(
            db.execute(
                select(func.count(Comment.id)).where(Comment.submission_id.in_(submission_ids))
            ).scalar_one()
        )
        comment_ids = db.execute(
            select(Comment.id).where(Comment.submission_id.in_(submission_ids))
        ).scalars().all()
    else:
        parsed_comments = 0
        comment_ids = []

    submission_filter_ids = submission_ids or ['__none__']
    comment_filter_ids = comment_ids or ['__none__']

    stance_scope = or_(
        and_(Stance.target_type == 'submission', Stance.target_id.in_(submission_filter_ids)),
        and_(Stance.target_type == 'comment', Stance.target_id.in_(comment_filter_ids)),
    )
    mention_scope = or_(
        and_(Mention.target_type == 'submission', Mention.target_id.in_(submission_filter_ids)),
        and_(Mention.target_type == 'comment', Mention.target_id.in_(comment_filter_ids)),
    )

    mentions_total = int(db.execute(select(func.count(Mention.id)).where(mention_scope)).scalar_one())
    context_mentions = int(
        db.execute(
            select(func.count(Mention.id)).where(and_(mention_scope, Mention.source == 'context'))
        ).scalar_one()
    )
    unclear_count = int(
        db.execute(
            select(func.count(Stance.id)).where(and_(stance_scope, Stance.stance_label == 'UNCLEAR'))
        ).scalar_one()
    )

    model_version_rows = db.execute(
        select(Stance.model_version, func.count(Stance.id))
        .where(stance_scope)
        .group_by(Stance.model_version)
        .order_by(desc(func.count(Stance.id)))
    ).all()
    mention_source_rows = db.execute(
        select(Mention.source, func.count(Mention.id))
        .where(mention_scope)
        .group_by(Mention.source)
        .order_by(desc(func.count(Mention.id)))
    ).all()

    pulls_total = len(pull_statuses)
    pulls_success = sum(1 for status in pull_statuses if status == 'success')
    pulls_failed = sum(1 for status in pull_statuses if status == 'failed')

    return QualityResponse(
        date_bucket_berlin=date_bucket,
        subreddit=selected_subreddit or 'ALL',
        pulls_total=pulls_total,
        pulls_success=pulls_success,
        pulls_failed=pulls_failed,
        submissions=len(submission_ids),
        reddit_reported_comments=reddit_reported_comments,
        parsed_comments=parsed_comments,
        parsed_comment_coverage=(parsed_comments / reddit_reported_comments if reddit_reported_comments > 0 else None),
        mentions_total=mentions_total,
        context_mentions=context_mentions,
        context_mention_rate=(context_mentions / mentions_total if mentions_total > 0 else 0.0),
        unclear_count=unclear_count,
        unclear_rate=(unclear_count / mentions_total if mentions_total > 0 else 0.0),
        model_versions=[
            ModelVersionCount(model_version=str(model_version), count=int(count))
            for model_version, count in model_version_rows
        ],
        mention_sources=[
            MentionSourceCount(source=str(source), count=int(count))
            for source, count in mention_source_rows
        ],
    )


@router.get('/analytics', response_model=AnalyticsResponse)
def get_analytics(
    days: int = Query(default=30, ge=3, le=365),
    date: str | None = Query(default=None),
    subreddit: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AnalyticsResponse:
    selected_subreddit: str | None = None
    if subreddit and subreddit.strip():
        requested = subreddit.strip()
        if requested.lower() not in {'all', '*'}:
            selected_subreddit = next((s for s in settings.subreddits if s.lower() == requested.lower()), None)
            if selected_subreddit is None:
                raise HTTPException(status_code=400, detail=f'Subreddit {subreddit} is not in configured list')

    if date:
        try:
            end_date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail='date must be YYYY-MM-DD') from exc
    else:
        end_date = to_berlin_date(utc_now())
    start_date = end_date - timedelta(days=days - 1)

    query = select(DailyScore).where(
        DailyScore.date_bucket_berlin >= start_date,
        DailyScore.date_bucket_berlin <= end_date,
    )
    if selected_subreddit:
        query = query.where(DailyScore.subreddit == selected_subreddit)
    elif settings.subreddits:
        query = query.where(DailyScore.subreddit.in_(settings.subreddits))
    rows = db.execute(query).scalars().all()

    day_ticker = _aggregate_day_ticker(rows=rows, start_date=start_date, end_date=end_date)
    trend = _build_analytics_trend(day_ticker=day_ticker, start_date=start_date, end_date=end_date)
    rolling_trend = _build_rolling_trend(trend)
    market_summary = _build_market_summary(trend)
    regime_breakdown = _build_regime_breakdown(trend)
    correlations = _build_correlations(trend)
    movers_up, movers_down = _build_movers(day_ticker=day_ticker, trend=trend)
    ticker_insights = _build_ticker_insights(day_ticker=day_ticker, trend=trend)
    weekday_profile = _build_weekday_profile(trend)
    subreddit_snapshot = _build_subreddit_snapshot(
        rows=rows,
        target_date=end_date,
        selected_subreddit=selected_subreddit,
    )

    return AnalyticsResponse(
        subreddit=selected_subreddit or 'ALL',
        days=days,
        date_from=start_date,
        date_to=end_date,
        trend=trend,
        rolling_trend=rolling_trend,
        market_summary=market_summary,
        regime_breakdown=regime_breakdown,
        correlations=correlations,
        top_movers_up=movers_up,
        top_movers_down=movers_down,
        ticker_insights=ticker_insights,
        weekday_profile=weekday_profile,
        subreddit_snapshot=subreddit_snapshot,
    )


@router.get('/ticker/{ticker}', response_model=TickerSeriesResponse)
def get_ticker_series(
    ticker: str,
    days: int = Query(default=30, ge=1, le=365),
    subreddit: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> TickerSeriesResponse:
    selected_subreddit: str | None = None
    if subreddit and subreddit.strip():
        requested = subreddit.strip()
        if requested.lower() not in {'all', '*'}:
            selected_subreddit = next((s for s in settings.subreddits if s.lower() == requested.lower()), None)
            if selected_subreddit is None:
                raise HTTPException(status_code=400, detail=f'Subreddit {subreddit} is not in configured list')

    ticker = ticker.upper()
    end_date = to_berlin_date(utc_now())
    start_date = end_date - timedelta(days=days - 1)

    query = select(DailyScore).where(
        DailyScore.ticker == ticker,
        DailyScore.date_bucket_berlin >= start_date,
        DailyScore.date_bucket_berlin <= end_date,
    )
    if selected_subreddit:
        query = query.where(DailyScore.subreddit == selected_subreddit)

    rows = db.execute(query.order_by(DailyScore.date_bucket_berlin.asc())).scalars().all()
    series = _build_ticker_series(rows, collapse_subreddits=(selected_subreddit is None))

    bullish_examples = _comment_examples(
        db,
        ticker=ticker,
        label='BULLISH',
        subreddit=selected_subreddit,
        start_date=start_date,
        end_date=end_date,
    )
    bearish_examples = _comment_examples(
        db,
        ticker=ticker,
        label='BEARISH',
        subreddit=selected_subreddit,
        start_date=start_date,
        end_date=end_date,
    )

    return TickerSeriesResponse(
        ticker=ticker,
        subreddit=selected_subreddit,
        days=days,
        series=series,
        bullish_examples=bullish_examples,
        bearish_examples=bearish_examples,
    )


@router.get('/thread/{submission_id}', response_model=ThreadResponse)
def get_thread(submission_id: str, db: Session = Depends(get_db)) -> ThreadResponse:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail='submission not found')

    comments = db.execute(
        select(Comment).where(Comment.submission_id == submission_id).order_by(Comment.depth.asc(), Comment.created_utc.asc())
    ).scalars().all()

    submission_mentions = _mentions_for_target(db, 'submission', submission_id)
    submission_stance = _stance_for_target(db, 'submission', submission_id)

    comment_ids = [c.id for c in comments]
    mentions_by_comment = _mentions_for_comments(db, comment_ids)
    stance_by_comment = _stance_for_comments(db, comment_ids)

    return ThreadResponse(
        submission=SubmissionOut(
            id=submission.id,
            subreddit=submission.subreddit,
            created_utc=submission.created_utc,
            title=submission.title,
            selftext=submission.selftext,
            url=submission.url,
            score=submission.score,
            num_comments=submission.num_comments,
            permalink=submission.permalink,
            mentions=submission_mentions,
            stance=submission_stance,
        ),
        comments=[
            CommentThreadOut(
                id=c.id,
                submission_id=c.submission_id,
                parent_id=c.parent_id,
                depth=c.depth,
                author=c.author,
                created_utc=c.created_utc,
                score=c.score,
                body=c.body,
                permalink=c.permalink,
                mentions=mentions_by_comment.get(c.id, []),
                stance=stance_by_comment.get(c.id, []),
            )
            for c in comments
        ],
    )


def _mentions_for_target(db: Session, target_type: str, target_id: str):
    rows = db.execute(
        select(Mention).where(and_(Mention.target_type == target_type, Mention.target_id == target_id))
    ).scalars().all()
    return [
        {
            'ticker': r.ticker,
            'confidence': r.confidence,
            'source': r.source,
            'span_start': r.span_start,
            'span_end': r.span_end,
        }
        for r in rows
    ]


def _stance_for_target(db: Session, target_type: str, target_id: str):
    rows = db.execute(
        select(Stance).where(and_(Stance.target_type == target_type, Stance.target_id == target_id))
    ).scalars().all()
    return [
        StanceOut(
            ticker=r.ticker,
            stance_label=r.stance_label,
            stance_score=r.stance_score,
            confidence=r.confidence,
            model_version=r.model_version,
            context_text=r.context_text,
        )
        for r in rows
    ]


def _mentions_for_comments(db: Session, comment_ids: list[str]) -> dict[str, list]:
    if not comment_ids:
        return {}
    rows = db.execute(
        select(Mention).where(and_(Mention.target_type == 'comment', Mention.target_id.in_(comment_ids)))
    ).scalars().all()
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r.target_id, []).append(
            {
                'ticker': r.ticker,
                'confidence': r.confidence,
                'source': r.source,
                'span_start': r.span_start,
                'span_end': r.span_end,
            }
        )
    return out


def _stance_for_comments(db: Session, comment_ids: list[str]) -> dict[str, list[StanceOut]]:
    if not comment_ids:
        return {}
    rows = db.execute(
        select(Stance).where(and_(Stance.target_type == 'comment', Stance.target_id.in_(comment_ids)))
    ).scalars().all()
    out: dict[str, list[StanceOut]] = {}
    for r in rows:
        out.setdefault(r.target_id, []).append(
            StanceOut(
                ticker=r.ticker,
                stance_label=r.stance_label,
                stance_score=r.stance_score,
                confidence=r.confidence,
                model_version=r.model_version,
                context_text=r.context_text,
            )
        )
    return out


def _comment_examples(
    db: Session,
    ticker: str,
    label: str,
    subreddit: str | None,
    start_date: date,
    end_date: date,
) -> list[CommentExample]:
    query = (
        select(Comment, Stance)
        .join(Stance, and_(Stance.target_type == 'comment', Stance.target_id == Comment.id))
        .join(Submission, Submission.id == Comment.submission_id)
        .join(PullRun, PullRun.id == Submission.pull_run_id)
        .where(
            Stance.ticker == ticker,
            Stance.stance_label == label,
            PullRun.date_bucket_berlin >= start_date,
            PullRun.date_bucket_berlin <= end_date,
        )
        .order_by(desc(Comment.score), desc(Stance.confidence))
        .limit(100)
    )
    if subreddit:
        query = query.where(PullRun.subreddit == subreddit)

    rows = db.execute(query).all()

    examples: list[CommentExample] = []
    seen_comments: set[str] = set()
    for comment, stance in rows:
        if comment.id in seen_comments:
            continue
        seen_comments.add(comment.id)

        examples.append(
            CommentExample(
                id=comment.id,
                submission_id=comment.submission_id,
                body=comment.body,
                score=comment.score,
                permalink=comment.permalink,
                stance_label=stance.stance_label,
                stance_score=stance.stance_score,
            )
        )
        if len(examples) >= 5:
            break
    return examples


def _berlin_date_range_to_utc(*, start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start_berlin = datetime(start_date.year, start_date.month, start_date.day, tzinfo=BERLIN)
    end_next_day = end_date + timedelta(days=1)
    end_berlin_exclusive = datetime(end_next_day.year, end_next_day.month, end_next_day.day, tzinfo=BERLIN)
    return start_berlin.astimezone(timezone.utc), end_berlin_exclusive.astimezone(timezone.utc)


def _build_results_from_created_window(
    *,
    db: Session,
    start_utc: datetime,
    end_utc_exclusive: datetime,
    selected_subreddit: str | None,
) -> list[DailyScoreOut]:
    submission_query = select(Submission).where(
        Submission.created_utc >= start_utc,
        Submission.created_utc < end_utc_exclusive,
    )
    if selected_subreddit:
        submission_query = submission_query.where(Submission.subreddit == selected_subreddit)
    elif settings.subreddits:
        submission_query = submission_query.where(Submission.subreddit.in_(settings.subreddits))
    submissions = db.execute(submission_query).scalars().all()

    comment_query = (
        select(Comment)
        .join(Submission, Submission.id == Comment.submission_id)
        .where(
            Comment.created_utc >= start_utc,
            Comment.created_utc < end_utc_exclusive,
        )
    )
    if selected_subreddit:
        comment_query = comment_query.where(Submission.subreddit == selected_subreddit)
    elif settings.subreddits:
        comment_query = comment_query.where(Submission.subreddit.in_(settings.subreddits))
    comments = db.execute(comment_query).scalars().all()

    submission_ids = [row.id for row in submissions]
    comment_ids = [row.id for row in comments]
    if not submission_ids and not comment_ids:
        return []

    submission_meta = {
        row.id: {
            'score': int(row.score),
            'depth': 0,
            'created_utc': row.created_utc,
        }
        for row in submissions
    }
    comment_meta = {
        row.id: {
            'score': int(row.score),
            'depth': int(row.depth),
            'created_utc': row.created_utc,
        }
        for row in comments
    }

    stance_query = select(Stance).where(
        or_(
            and_(Stance.target_type == 'submission', Stance.target_id.in_(submission_ids or ['__none__'])),
            and_(Stance.target_type == 'comment', Stance.target_id.in_(comment_ids or ['__none__'])),
        )
    )
    stance_rows = db.execute(stance_query).scalars().all()
    if not stance_rows:
        return []

    records: list[AggregationRecord] = []
    for stance in stance_rows:
        meta = submission_meta.get(stance.target_id) if stance.target_type == 'submission' else comment_meta.get(stance.target_id)
        if meta is None:
            continue
        created = meta['created_utc']
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        records.append(
            AggregationRecord(
                ticker=stance.ticker,
                stance_label=stance.stance_label,
                stance_score=stance.stance_score,
                upvote_score=int(meta['score']),
                depth=int(meta['depth']),
                created_utc=created,
            )
        )
    if not records:
        return []

    metrics_by_ticker = compute_daily_scores(
        records,
        use_depth_decay=settings.use_depth_decay,
        lambda_depth=settings.lambda_depth,
        use_time_decay=settings.use_time_decay,
        lambda_time=settings.lambda_time,
        reference_time=end_utc_exclusive,
    )
    if not metrics_by_ticker:
        return []

    end_berlin_date = end_utc_exclusive.astimezone(BERLIN).date() - timedelta(days=1)
    subreddit_label = selected_subreddit or 'ALL'
    rows = [
        DailyScoreOut(
            date_bucket_berlin=end_berlin_date,
            subreddit=subreddit_label,
            ticker=ticker,
            score_unweighted=metrics.score_unweighted,
            score_weighted=metrics.score_weighted,
            score_stddev_unweighted=metrics.score_stddev_unweighted,
            ci95_low_unweighted=metrics.ci95_low_unweighted,
            ci95_high_unweighted=metrics.ci95_high_unweighted,
            valid_count=metrics.valid_count,
            mention_count=metrics.mention_count,
            bullish_count=metrics.bullish_count,
            bearish_count=metrics.bearish_count,
            neutral_count=metrics.neutral_count,
            unclear_count=metrics.unclear_count,
            unclear_rate=metrics.unclear_rate,
        )
        for ticker, metrics in metrics_by_ticker.items()
    ]
    rows.sort(key=lambda row: (row.mention_count, row.score_weighted), reverse=True)
    return rows


def _build_ticker_series(rows: list[DailyScore], collapse_subreddits: bool) -> list[TickerPoint]:
    if not collapse_subreddits:
        return [
            TickerPoint(
                date_bucket_berlin=r.date_bucket_berlin,
                score_unweighted=r.score_unweighted,
                score_weighted=r.score_weighted,
                mention_count=r.mention_count,
                unclear_rate=r.unclear_rate,
            )
            for r in rows
        ]

    grouped: dict[date, list[DailyScore]] = {}
    for row in rows:
        grouped.setdefault(row.date_bucket_berlin, []).append(row)

    points: list[TickerPoint] = []
    for day in sorted(grouped.keys()):
        day_rows = grouped[day]
        total_mentions = sum(r.mention_count for r in day_rows)
        total_valid = sum(r.valid_count for r in day_rows)
        total_unclear = sum(r.unclear_count for r in day_rows)
        total_score_sum = sum(r.score_sum_unweighted for r in day_rows)
        total_weighted_num = sum(r.weighted_numerator for r in day_rows)
        total_weighted_den = sum(r.weighted_denominator for r in day_rows)

        if total_valid > 0:
            score_unweighted = total_score_sum / total_valid
        else:
            score_unweighted = 0.0

        if total_weighted_den > 0:
            score_weighted = total_weighted_num / total_weighted_den
        else:
            score_weighted = score_unweighted

        unclear_rate = (total_unclear / total_mentions) if total_mentions > 0 else 0.0

        points.append(
            TickerPoint(
                date_bucket_berlin=day,
                score_unweighted=score_unweighted,
                score_weighted=score_weighted,
                mention_count=total_mentions,
                unclear_rate=unclear_rate,
            )
        )

    return points


def _aggregate_daily_rows(
    rows: list[DailyScore],
    date_bucket: date,
    subreddit_label: str,
) -> list[DailyScoreOut]:
    if not rows:
        return []

    grouped: dict[str, list[DailyScore]] = {}
    for row in rows:
        grouped.setdefault(row.ticker, []).append(row)

    out: list[DailyScoreOut] = []
    for ticker, ticker_rows in grouped.items():
        mention_count = sum(r.mention_count for r in ticker_rows)
        valid_count = sum(r.valid_count for r in ticker_rows)
        bullish_count = sum(r.bullish_count for r in ticker_rows)
        bearish_count = sum(r.bearish_count for r in ticker_rows)
        neutral_count = sum(r.neutral_count for r in ticker_rows)
        unclear_count = sum(r.unclear_count for r in ticker_rows)
        score_sum_unweighted = sum(r.score_sum_unweighted for r in ticker_rows)
        weighted_numerator = sum(r.weighted_numerator for r in ticker_rows)
        weighted_denominator = sum(r.weighted_denominator for r in ticker_rows)
        score_stddev_unweighted = 0.0
        ci95_low_unweighted = 0.0
        ci95_high_unweighted = 0.0

        if valid_count > 0:
            score_unweighted = score_sum_unweighted / valid_count
        else:
            score_unweighted = 0.0

        if weighted_denominator > 0:
            score_weighted = weighted_numerator / weighted_denominator
        else:
            score_weighted = score_unweighted

        if valid_count > 1:
            sum_squares = 0.0
            for row in ticker_rows:
                if row.valid_count <= 0:
                    continue
                row_var = row.score_stddev_unweighted ** 2
                sum_squares += (row.valid_count - 1) * row_var
                mean_delta = row.score_unweighted - score_unweighted
                sum_squares += row.valid_count * (mean_delta ** 2)
            score_stddev_unweighted = math.sqrt(max(sum_squares / (valid_count - 1), 0.0))
            margin = 1.96 * (score_stddev_unweighted / math.sqrt(valid_count))
            ci95_low_unweighted = max(score_unweighted - margin, -1.0)
            ci95_high_unweighted = min(score_unweighted + margin, 1.0)
        elif valid_count == 1:
            score_stddev_unweighted = 0.0
            ci95_low_unweighted = score_unweighted
            ci95_high_unweighted = score_unweighted

        unclear_rate = (unclear_count / mention_count) if mention_count > 0 else 0.0

        out.append(
            DailyScoreOut(
                date_bucket_berlin=date_bucket,
                subreddit=subreddit_label,
                ticker=ticker,
                score_unweighted=score_unweighted,
                score_weighted=score_weighted,
                score_stddev_unweighted=score_stddev_unweighted,
                ci95_low_unweighted=ci95_low_unweighted,
                ci95_high_unweighted=ci95_high_unweighted,
                valid_count=valid_count,
                mention_count=mention_count,
                bullish_count=bullish_count,
                bearish_count=bearish_count,
                neutral_count=neutral_count,
                unclear_count=unclear_count,
                unclear_rate=unclear_rate,
            )
        )

    out.sort(key=lambda r: (r.mention_count, r.score_weighted), reverse=True)
    return out


def _aggregate_day_ticker(
    *,
    rows: list[DailyScore],
    start_date: date,
    end_date: date,
) -> dict[date, dict[str, dict[str, float]]]:
    out: dict[date, dict[str, dict[str, float]]] = {}
    day = start_date
    while day <= end_date:
        out[day] = {}
        day += timedelta(days=1)

    for row in rows:
        ticker_bucket = out.setdefault(row.date_bucket_berlin, {})
        ticker_stats = ticker_bucket.setdefault(
            row.ticker,
            {
                'mention_count': 0.0,
                'valid_count': 0.0,
                'bullish_count': 0.0,
                'bearish_count': 0.0,
                'neutral_count': 0.0,
                'unclear_count': 0.0,
                'score_sum_unweighted': 0.0,
                'weighted_numerator': 0.0,
                'weighted_denominator': 0.0,
            },
        )

        valid_count = _coalesce_valid_count(row)
        score_sum = _coalesce_score_sum(row, valid_count)
        weighted_numerator = _coalesce_weighted_num(row, valid_count)
        weighted_denominator = _coalesce_weighted_den(row, valid_count)

        ticker_stats['mention_count'] += float(row.mention_count)
        ticker_stats['valid_count'] += float(valid_count)
        ticker_stats['bullish_count'] += float(row.bullish_count)
        ticker_stats['bearish_count'] += float(row.bearish_count)
        ticker_stats['neutral_count'] += float(row.neutral_count)
        ticker_stats['unclear_count'] += float(row.unclear_count)
        ticker_stats['score_sum_unweighted'] += score_sum
        ticker_stats['weighted_numerator'] += weighted_numerator
        ticker_stats['weighted_denominator'] += weighted_denominator

    return out


def _build_analytics_trend(
    *,
    day_ticker: dict[date, dict[str, dict[str, float]]],
    start_date: date,
    end_date: date,
) -> list[AnalyticsDayPoint]:
    trend: list[AnalyticsDayPoint] = []
    day = start_date
    while day <= end_date:
        ticker_bucket = day_ticker.get(day, {})

        mention_count = int(sum(stats['mention_count'] for stats in ticker_bucket.values()))
        valid_count = int(sum(stats['valid_count'] for stats in ticker_bucket.values()))
        bullish_count = int(sum(stats['bullish_count'] for stats in ticker_bucket.values()))
        bearish_count = int(sum(stats['bearish_count'] for stats in ticker_bucket.values()))
        neutral_count = int(sum(stats['neutral_count'] for stats in ticker_bucket.values()))
        unclear_count = int(sum(stats['unclear_count'] for stats in ticker_bucket.values()))
        score_sum = sum(stats['score_sum_unweighted'] for stats in ticker_bucket.values())
        weighted_num = sum(stats['weighted_numerator'] for stats in ticker_bucket.values())
        weighted_den = sum(stats['weighted_denominator'] for stats in ticker_bucket.values())

        unweighted_score = (score_sum / valid_count) if valid_count > 0 else 0.0
        weighted_score = (weighted_num / weighted_den) if weighted_den > 0 else unweighted_score

        label_total = bullish_count + bearish_count + neutral_count
        bullish_share = (bullish_count / label_total) if label_total > 0 else 0.0
        bearish_share = (bearish_count / label_total) if label_total > 0 else 0.0
        neutral_share = (neutral_count / label_total) if label_total > 0 else 0.0
        unclear_rate = (unclear_count / mention_count) if mention_count > 0 else 0.0

        if mention_count > 0:
            weights = [stats['mention_count'] / mention_count for stats in ticker_bucket.values() if stats['mention_count'] > 0]
            concentration_hhi = sum(w * w for w in weights)
            top_ticker_share = max(weights) if weights else 0.0
        else:
            concentration_hhi = 0.0
            top_ticker_share = 0.0

        trend.append(
            AnalyticsDayPoint(
                date_bucket_berlin=day,
                weighted_score=weighted_score,
                unweighted_score=unweighted_score,
                mention_count=mention_count,
                valid_count=valid_count,
                unclear_rate=unclear_rate,
                bullish_share=bullish_share,
                bearish_share=bearish_share,
                neutral_share=neutral_share,
                concentration_hhi=concentration_hhi,
                top_ticker_share=top_ticker_share,
            )
        )
        day += timedelta(days=1)
    return trend


def _build_market_summary(trend: list[AnalyticsDayPoint]) -> AnalyticsMarketSummary:
    relevant = [point for point in trend if point.mention_count > 0]
    if not relevant:
        relevant = trend
    if not relevant:
        return AnalyticsMarketSummary(
            avg_weighted_score=0.0,
            score_volatility=0.0,
            avg_unclear_rate=0.0,
            avg_valid_ratio=0.0,
            avg_bullish_share=0.0,
            avg_bearish_share=0.0,
            avg_neutral_share=0.0,
            avg_concentration_hhi=0.0,
            avg_top_ticker_share=0.0,
            effective_ticker_count=0.0,
            active_days=0,
            total_mentions=0,
            score_trend_slope=0.0,
            mention_trend_slope=0.0,
        )

    n = len(relevant)
    total_mentions = int(sum(p.mention_count for p in trend))
    avg_weighted = sum(p.weighted_score for p in relevant) / n
    avg_unclear = sum(p.unclear_rate for p in relevant) / n
    avg_valid_ratio = sum((p.valid_count / p.mention_count) if p.mention_count > 0 else 0.0 for p in relevant) / n
    avg_bullish = sum(p.bullish_share for p in relevant) / n
    avg_bearish = sum(p.bearish_share for p in relevant) / n
    avg_neutral = sum(p.neutral_share for p in relevant) / n
    avg_hhi = sum(p.concentration_hhi for p in relevant) / n
    avg_top_share = sum(p.top_ticker_share for p in relevant) / n

    if n > 1:
        sq = sum((p.weighted_score - avg_weighted) ** 2 for p in relevant)
        volatility = math.sqrt(sq / (n - 1))
    else:
        volatility = 0.0

    effective_ticker_count = (1.0 / avg_hhi) if avg_hhi > 0 else 0.0

    return AnalyticsMarketSummary(
        avg_weighted_score=avg_weighted,
        score_volatility=volatility,
        avg_unclear_rate=avg_unclear,
        avg_valid_ratio=avg_valid_ratio,
        avg_bullish_share=avg_bullish,
        avg_bearish_share=avg_bearish,
        avg_neutral_share=avg_neutral,
        avg_concentration_hhi=avg_hhi,
        avg_top_ticker_share=avg_top_share,
        effective_ticker_count=effective_ticker_count,
        active_days=len([p for p in trend if p.mention_count > 0]),
        total_mentions=total_mentions,
        score_trend_slope=_linear_slope([p.weighted_score for p in relevant]),
        mention_trend_slope=_linear_slope([float(p.mention_count) for p in relevant]),
    )


def _build_rolling_trend(trend: list[AnalyticsDayPoint]) -> list[AnalyticsRollingPoint]:
    out: list[AnalyticsRollingPoint] = []
    for idx, point in enumerate(trend):
        window_7 = trend[max(0, idx - 6): idx + 1]
        window_14 = trend[max(0, idx - 13): idx + 1]
        window_7_active = [p for p in window_7 if p.mention_count > 0]
        window_14_active = [p for p in window_14 if p.mention_count > 0]

        weighted_ma7 = _safe_average([p.weighted_score for p in window_7_active], default=point.weighted_score)
        weighted_ma14 = _safe_average([p.weighted_score for p in window_14_active], default=point.weighted_score)
        mentions_ma7 = _safe_average([float(p.mention_count) for p in window_7], default=float(point.mention_count))
        unclear_ma7 = _safe_average([p.unclear_rate for p in window_7_active], default=point.unclear_rate)

        if len(window_7_active) > 1:
            mean = _safe_average([p.weighted_score for p in window_7_active], default=0.0)
            sq = sum((p.weighted_score - mean) ** 2 for p in window_7_active)
            volatility_ma7 = math.sqrt(sq / (len(window_7_active) - 1))
        else:
            volatility_ma7 = 0.0

        out.append(
            AnalyticsRollingPoint(
                date_bucket_berlin=point.date_bucket_berlin,
                weighted_score=point.weighted_score,
                weighted_ma7=weighted_ma7,
                weighted_ma14=weighted_ma14,
                mention_count=point.mention_count,
                mentions_ma7=mentions_ma7,
                unclear_rate=point.unclear_rate,
                unclear_ma7=unclear_ma7,
                volatility_ma7=volatility_ma7,
                momentum_7d=point.weighted_score - weighted_ma7,
            )
        )
    return out


def _build_regime_breakdown(trend: list[AnalyticsDayPoint]) -> AnalyticsRegimeBreakdown:
    relevant = [point for point in trend if point.mention_count > 0]
    if not relevant:
        return AnalyticsRegimeBreakdown(
            risk_on_days=0,
            balanced_days=0,
            risk_off_days=0,
            risk_on_share=0.0,
            balanced_share=0.0,
            risk_off_share=0.0,
            regime_switches=0,
            current_regime='no-data',
        )

    labels = [_classify_regime(point.weighted_score) for point in relevant]
    risk_on_days = sum(1 for label in labels if label == 'risk-on')
    balanced_days = sum(1 for label in labels if label == 'balanced')
    risk_off_days = sum(1 for label in labels if label == 'risk-off')
    switches = 0
    for prev, curr in zip(labels, labels[1:]):
        if curr != prev:
            switches += 1

    n = len(labels)
    return AnalyticsRegimeBreakdown(
        risk_on_days=risk_on_days,
        balanced_days=balanced_days,
        risk_off_days=risk_off_days,
        risk_on_share=(risk_on_days / n),
        balanced_share=(balanced_days / n),
        risk_off_share=(risk_off_days / n),
        regime_switches=switches,
        current_regime=labels[-1],
    )


def _build_correlations(trend: list[AnalyticsDayPoint]) -> AnalyticsCorrelation:
    relevant = [point for point in trend if point.mention_count > 0]
    if len(relevant) < 2:
        return AnalyticsCorrelation(
            mentions_vs_abs_score=0.0,
            unclear_vs_abs_score=0.0,
            concentration_vs_unclear=0.0,
        )

    abs_scores = [abs(point.weighted_score) for point in relevant]
    return AnalyticsCorrelation(
        mentions_vs_abs_score=_pearson_corr([float(point.mention_count) for point in relevant], abs_scores),
        unclear_vs_abs_score=_pearson_corr([point.unclear_rate for point in relevant], abs_scores),
        concentration_vs_unclear=_pearson_corr(
            [point.concentration_hhi for point in relevant],
            [point.unclear_rate for point in relevant],
        ),
    )


def _build_ticker_insights(
    *,
    day_ticker: dict[date, dict[str, dict[str, float]]],
    trend: list[AnalyticsDayPoint],
) -> list[AnalyticsTickerInsight]:
    if not trend:
        return []

    ticker_by_day: dict[str, list[tuple[date, dict[str, float]]]] = {}
    for day, bucket in day_ticker.items():
        for ticker, stats in bucket.items():
            if stats.get('mention_count', 0.0) <= 0:
                continue
            ticker_by_day.setdefault(ticker, []).append((day, stats))

    total_mentions_window = sum(point.mention_count for point in trend)
    if total_mentions_window <= 0:
        total_mentions_window = 1

    insights: list[AnalyticsTickerInsight] = []
    for ticker, samples in ticker_by_day.items():
        ordered = sorted(samples, key=lambda item: item[0])

        total_mentions = int(sum(sample[1].get('mention_count', 0.0) for sample in ordered))
        total_valid = sum(float(sample[1].get('valid_count', 0.0)) for sample in ordered)
        total_unclear = sum(float(sample[1].get('unclear_count', 0.0)) for sample in ordered)
        total_weighted_num = sum(float(sample[1].get('weighted_numerator', 0.0)) for sample in ordered)
        total_weighted_den = sum(float(sample[1].get('weighted_denominator', 0.0)) for sample in ordered)
        total_score_sum = sum(float(sample[1].get('score_sum_unweighted', 0.0)) for sample in ordered)

        if total_weighted_den > 0:
            avg_weighted = total_weighted_num / total_weighted_den
        elif total_valid > 0:
            avg_weighted = total_score_sum / total_valid
        else:
            avg_weighted = 0.0

        day_scores: list[float] = []
        for _, stats in ordered:
            weighted_den = float(stats.get('weighted_denominator', 0.0))
            valid_count = float(stats.get('valid_count', 0.0))
            if weighted_den > 0:
                day_scores.append(float(stats.get('weighted_numerator', 0.0)) / weighted_den)
            elif valid_count > 0:
                day_scores.append(float(stats.get('score_sum_unweighted', 0.0)) / valid_count)
            else:
                day_scores.append(0.0)

        latest_score = day_scores[-1] if day_scores else 0.0
        previous_score = day_scores[-2] if len(day_scores) > 1 else latest_score

        if len(day_scores) > 1:
            mean = _safe_average(day_scores, default=0.0)
            sq = sum((score - mean) ** 2 for score in day_scores)
            volatility = math.sqrt(sq / (len(day_scores) - 1))
        else:
            volatility = 0.0

        insights.append(
            AnalyticsTickerInsight(
                ticker=ticker,
                mention_count=total_mentions,
                mention_share=(total_mentions / total_mentions_window),
                avg_weighted_score=avg_weighted,
                score_volatility=volatility,
                latest_score=latest_score,
                previous_score=previous_score,
                momentum=latest_score - previous_score,
                active_days=len(day_scores),
                unclear_rate=(total_unclear / total_mentions if total_mentions > 0 else 0.0),
            )
        )

    insights.sort(key=lambda row: (row.mention_count, abs(row.momentum), abs(row.avg_weighted_score)), reverse=True)
    return insights[:18]


def _build_weekday_profile(trend: list[AnalyticsDayPoint]) -> list[AnalyticsWeekdayPoint]:
    weekday_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    buckets: dict[int, dict[str, float]] = {
        idx: {'weighted_sum': 0.0, 'mention_sum': 0.0, 'unclear_sum': 0.0, 'samples': 0.0}
        for idx in range(7)
    }

    for point in trend:
        if point.mention_count <= 0:
            continue
        idx = point.date_bucket_berlin.weekday()
        bucket = buckets[idx]
        bucket['weighted_sum'] += point.weighted_score
        bucket['mention_sum'] += float(point.mention_count)
        bucket['unclear_sum'] += point.unclear_rate
        bucket['samples'] += 1.0

    out: list[AnalyticsWeekdayPoint] = []
    for idx in range(7):
        bucket = buckets[idx]
        samples = int(bucket['samples'])
        out.append(
            AnalyticsWeekdayPoint(
                weekday=idx,
                label=weekday_labels[idx],
                avg_weighted_score=(bucket['weighted_sum'] / samples if samples > 0 else 0.0),
                avg_mentions=(bucket['mention_sum'] / samples if samples > 0 else 0.0),
                avg_unclear_rate=(bucket['unclear_sum'] / samples if samples > 0 else 0.0),
                samples=samples,
            )
        )
    return out


def _build_movers(
    *,
    day_ticker: dict[date, dict[str, dict[str, float]]],
    trend: list[AnalyticsDayPoint],
) -> tuple[list[AnalyticsMover], list[AnalyticsMover]]:
    relevant = [point for point in trend if point.mention_count > 0]
    if len(relevant) < 2:
        return [], []

    current_day = relevant[-1].date_bucket_berlin
    previous_day = relevant[-2].date_bucket_berlin
    current_bucket = day_ticker.get(current_day, {})
    previous_bucket = day_ticker.get(previous_day, {})
    tickers = sorted(set(current_bucket.keys()).union(previous_bucket.keys()))

    movers: list[AnalyticsMover] = []
    for ticker in tickers:
        curr = current_bucket.get(ticker, {})
        prev = previous_bucket.get(ticker, {})

        curr_mentions = int(curr.get('mention_count', 0.0))
        prev_mentions = int(prev.get('mention_count', 0.0))
        curr_weighted_den = float(curr.get('weighted_denominator', 0.0))
        prev_weighted_den = float(prev.get('weighted_denominator', 0.0))
        curr_unweighted_den = float(curr.get('valid_count', 0.0))
        prev_unweighted_den = float(prev.get('valid_count', 0.0))

        if curr_weighted_den > 0:
            curr_score = float(curr.get('weighted_numerator', 0.0)) / curr_weighted_den
        elif curr_unweighted_den > 0:
            curr_score = float(curr.get('score_sum_unweighted', 0.0)) / curr_unweighted_den
        else:
            curr_score = 0.0

        if prev_weighted_den > 0:
            prev_score = float(prev.get('weighted_numerator', 0.0)) / prev_weighted_den
        elif prev_unweighted_den > 0:
            prev_score = float(prev.get('score_sum_unweighted', 0.0)) / prev_unweighted_den
        else:
            prev_score = 0.0

        movers.append(
            AnalyticsMover(
                ticker=ticker,
                current_mentions=curr_mentions,
                current_weighted_score=curr_score,
                previous_weighted_score=prev_score,
                score_delta=curr_score - prev_score,
                mention_delta=curr_mentions - prev_mentions,
            )
        )

    movers.sort(key=lambda row: (row.score_delta, row.current_mentions), reverse=True)
    top_up = movers[:8]
    top_down = list(sorted(movers, key=lambda row: (row.score_delta, -row.current_mentions))[:8])
    return top_up, top_down


def _build_subreddit_snapshot(
    *,
    rows: list[DailyScore],
    target_date: date,
    selected_subreddit: str | None,
) -> list[AnalyticsSubredditPoint]:
    relevant = [row for row in rows if row.date_bucket_berlin == target_date]
    if selected_subreddit:
        relevant = [row for row in relevant if row.subreddit == selected_subreddit]

    grouped: dict[str, dict[str, float]] = {}
    for row in relevant:
        bucket = grouped.setdefault(
            row.subreddit,
            {
                'mention_count': 0.0,
                'valid_count': 0.0,
                'bullish_count': 0.0,
                'bearish_count': 0.0,
                'neutral_count': 0.0,
                'unclear_count': 0.0,
                'score_sum_unweighted': 0.0,
                'weighted_numerator': 0.0,
                'weighted_denominator': 0.0,
            },
        )
        valid_count = _coalesce_valid_count(row)
        bucket['mention_count'] += float(row.mention_count)
        bucket['valid_count'] += float(valid_count)
        bucket['bullish_count'] += float(row.bullish_count)
        bucket['bearish_count'] += float(row.bearish_count)
        bucket['neutral_count'] += float(row.neutral_count)
        bucket['unclear_count'] += float(row.unclear_count)
        bucket['score_sum_unweighted'] += _coalesce_score_sum(row, valid_count)
        bucket['weighted_numerator'] += _coalesce_weighted_num(row, valid_count)
        bucket['weighted_denominator'] += _coalesce_weighted_den(row, valid_count)

    out: list[AnalyticsSubredditPoint] = []
    for subreddit, bucket in grouped.items():
        mention_count = int(bucket['mention_count'])
        valid_count = int(bucket['valid_count'])
        bullish = int(bucket['bullish_count'])
        bearish = int(bucket['bearish_count'])
        neutral = int(bucket['neutral_count'])
        unclear = int(bucket['unclear_count'])
        label_total = bullish + bearish + neutral

        if bucket['weighted_denominator'] > 0:
            weighted_score = bucket['weighted_numerator'] / bucket['weighted_denominator']
        elif valid_count > 0:
            weighted_score = bucket['score_sum_unweighted'] / valid_count
        else:
            weighted_score = 0.0

        out.append(
            AnalyticsSubredditPoint(
                subreddit=subreddit,
                mention_count=mention_count,
                weighted_score=weighted_score,
                unclear_rate=(unclear / mention_count if mention_count > 0 else 0.0),
                bullish_share=(bullish / label_total if label_total > 0 else 0.0),
                bearish_share=(bearish / label_total if label_total > 0 else 0.0),
                neutral_share=(neutral / label_total if label_total > 0 else 0.0),
            )
        )

    out.sort(key=lambda row: row.mention_count, reverse=True)
    return out


def _safe_average(values: list[float], default: float = 0.0) -> float:
    if not values:
        return default
    return sum(values) / len(values)


def _linear_slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    den = sum((idx - x_mean) ** 2 for idx in range(n))
    if den <= 0:
        return 0.0
    num = sum((idx - x_mean) * (value - y_mean) for idx, value in enumerate(values))
    return num / den


def _pearson_corr(x: list[float], y: list[float]) -> float:
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    x_vals = x[:n]
    y_vals = y[:n]
    x_mean = sum(x_vals) / n
    y_mean = sum(y_vals) / n
    x_var = sum((value - x_mean) ** 2 for value in x_vals)
    y_var = sum((value - y_mean) ** 2 for value in y_vals)
    if x_var <= 0 or y_var <= 0:
        return 0.0
    cov = sum((x_vals[idx] - x_mean) * (y_vals[idx] - y_mean) for idx in range(n))
    corr = cov / math.sqrt(x_var * y_var)
    return max(-1.0, min(1.0, corr))


def _classify_regime(score: float) -> str:
    if score >= 0.15:
        return 'risk-on'
    if score <= -0.15:
        return 'risk-off'
    return 'balanced'


def _coalesce_valid_count(row: DailyScore) -> int:
    valid = int(row.valid_count) if isinstance(row.valid_count, int) else 0
    if valid > 0:
        return valid
    return max(int(row.mention_count) - int(row.unclear_count), 0)


def _coalesce_score_sum(row: DailyScore, valid_count: int) -> float:
    if _is_finite_number(row.score_sum_unweighted):
        return float(row.score_sum_unweighted)
    return float(row.score_unweighted) * float(valid_count)


def _coalesce_weighted_num(row: DailyScore, valid_count: int) -> float:
    if _is_finite_number(row.weighted_numerator):
        return float(row.weighted_numerator)
    return float(row.score_weighted) * float(valid_count)


def _coalesce_weighted_den(row: DailyScore, valid_count: int) -> float:
    if _is_finite_number(row.weighted_denominator) and float(row.weighted_denominator) > 0:
        return float(row.weighted_denominator)
    return float(valid_count)


def _is_finite_number(value: float | int | None) -> bool:
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
