from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.route_utils import parse_berlin_date_param, resolve_subreddit_param, settings
from app.models.daily_score import DailyScore
from app.schemas.api import AnalyticsResponse
from app.services.analytics.service import build_analytics_response

router = APIRouter()


@router.get('/analytics', response_model=AnalyticsResponse)
def get_analytics(
    days: int = Query(default=30, ge=3, le=365),
    date: str | None = Query(default=None),
    subreddit: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AnalyticsResponse:
    selected_subreddit = resolve_subreddit_param(subreddit)
    end_date = parse_berlin_date_param(date)
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

    return build_analytics_response(
        rows=rows,
        selected_subreddit=selected_subreddit,
        days=days,
        start_date=start_date,
        end_date=end_date,
    )
