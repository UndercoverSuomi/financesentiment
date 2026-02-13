from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException

from app.core.config import get_settings
from app.utils.timezone import to_berlin_date, utc_now

settings = get_settings()


def resolve_subreddit_param(subreddit: str | None) -> str | None:
    if not subreddit or not subreddit.strip():
        return None

    requested = subreddit.strip()
    if requested.lower() in {'all', '*'}:
        return None

    selected = next((item for item in settings.subreddits if item.lower() == requested.lower()), None)
    if selected is None:
        raise HTTPException(status_code=400, detail=f'Subreddit {subreddit} is not in configured list')
    return selected


def parse_berlin_date_param(date_value: str | None) -> date:
    if not date_value:
        return to_berlin_date(utc_now())
    try:
        return datetime.strptime(date_value, '%Y-%m-%d').date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='date must be YYYY-MM-DD') from exc
