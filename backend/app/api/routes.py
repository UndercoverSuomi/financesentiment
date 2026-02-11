from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_ingestion_service
from app.core.config import get_settings
from app.models.comment import Comment
from app.models.daily_score import DailyScore
from app.models.mention import Mention
from app.models.pull_run import PullRun
from app.models.stance import Stance
from app.models.submission import Submission
from app.schemas.api import (
    CommentExample,
    CommentThreadOut,
    DailyScoreOut,
    PullSummary,
    ResultsResponse,
    StanceOut,
    SubredditsResponse,
    SubmissionOut,
    ThreadResponse,
    TickerPoint,
    TickerSeriesResponse,
)
from app.services.ingestion_service import IngestionService
from app.utils.timezone import to_berlin_date, utc_now

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


@router.get('/results', response_model=ResultsResponse)
def get_results(
    date: str | None = Query(default=None),
    subreddit: str | None = Query(default=None),
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
            date_bucket = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail='date must be YYYY-MM-DD') from exc
    else:
        date_bucket = to_berlin_date(utc_now())

    query = select(DailyScore).where(DailyScore.date_bucket_berlin == date_bucket)
    if selected_subreddit:
        query = query.where(DailyScore.subreddit == selected_subreddit)
    elif settings.subreddits:
        query = query.where(DailyScore.subreddit.in_(settings.subreddits))

    rows = db.execute(query).scalars().all()

    if selected_subreddit:
        out_rows = sorted(rows, key=lambda r: (r.mention_count, r.score_weighted), reverse=True)
        response_subreddit = selected_subreddit
    else:
        out_rows = _aggregate_daily_rows(rows, date_bucket)
        response_subreddit = 'ALL'

    return ResultsResponse(
        date_bucket_berlin=date_bucket,
        subreddit=response_subreddit,
        rows=[
            (DailyScoreOut.model_validate(r.__dict__) if isinstance(r, DailyScore) else r)
            for r in out_rows
        ],
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

        if total_mentions > 0:
            score_unweighted = sum(r.score_unweighted * r.mention_count for r in day_rows) / total_mentions
            score_weighted = sum(r.score_weighted * r.mention_count for r in day_rows) / total_mentions
            unclear_rate = sum(r.unclear_rate * r.mention_count for r in day_rows) / total_mentions
        else:
            score_unweighted = sum(r.score_unweighted for r in day_rows) / len(day_rows)
            score_weighted = sum(r.score_weighted for r in day_rows) / len(day_rows)
            unclear_rate = sum(r.unclear_rate for r in day_rows) / len(day_rows)

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


def _aggregate_daily_rows(rows: list[DailyScore], date_bucket: date) -> list[DailyScoreOut]:
    if not rows:
        return []

    grouped: dict[str, list[DailyScore]] = {}
    for row in rows:
        grouped.setdefault(row.ticker, []).append(row)

    out: list[DailyScoreOut] = []
    for ticker, ticker_rows in grouped.items():
        mention_count = sum(r.mention_count for r in ticker_rows)
        bullish_count = sum(r.bullish_count for r in ticker_rows)
        bearish_count = sum(r.bearish_count for r in ticker_rows)
        neutral_count = sum(r.neutral_count for r in ticker_rows)
        unclear_count = sum(r.unclear_count for r in ticker_rows)

        if mention_count > 0:
            score_unweighted = sum(r.score_unweighted * r.mention_count for r in ticker_rows) / mention_count
            score_weighted = sum(r.score_weighted * r.mention_count for r in ticker_rows) / mention_count
            unclear_rate = unclear_count / mention_count
        else:
            score_unweighted = sum(r.score_unweighted for r in ticker_rows) / len(ticker_rows)
            score_weighted = sum(r.score_weighted for r in ticker_rows) / len(ticker_rows)
            unclear_rate = 0.0

        out.append(
            DailyScoreOut(
                date_bucket_berlin=date_bucket,
                subreddit='ALL',
                ticker=ticker,
                score_unweighted=score_unweighted,
                score_weighted=score_weighted,
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
