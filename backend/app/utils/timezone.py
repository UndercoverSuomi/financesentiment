from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo('Europe/Berlin')


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_berlin_date(dt: datetime) -> date:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BERLIN).date()
