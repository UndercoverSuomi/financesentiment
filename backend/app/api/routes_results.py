from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_evaluation_service
from app.api.route_utils import parse_berlin_date_param, resolve_subreddit_param, settings
from app.models.comment import Comment
from app.models.daily_score import DailyScore
from app.models.mention import Mention
from app.models.pull_run import PullRun
from app.models.stance import Stance
from app.models.submission import Submission
from app.schemas.api import (
    DailyScoreOut,
    EvaluationResponse,
    MentionSourceCount,
    ModelVersionCount,
    QualityResponse,
    ResultsResponse,
)
from app.services.aggregation_service import AggregationRecord, compute_daily_scores
from app.services.evaluation_service import EvaluationService
from app.utils.timezone import BERLIN

router = APIRouter()


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
    selected_subreddit = resolve_subreddit_param(subreddit)
    end_date = parse_berlin_date_param(date)

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
    selected_subreddit = resolve_subreddit_param(subreddit)
    date_bucket = parse_berlin_date_param(date)

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
