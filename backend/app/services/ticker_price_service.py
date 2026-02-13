from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.utils.timezone import to_berlin_date

SUPPORTED_YFINANCE_INTERVALS = {'1d', '5d', '1wk', '1mo'}


class TickerPriceError(RuntimeError):
    pass


@dataclass(slots=True)
class PricePoint:
    date_bucket_berlin: date
    close_price: float


def fetch_ticker_close_prices(
    ticker: str,
    start_date: date,
    end_date: date,
    *,
    interval: str = '1d',
) -> list[PricePoint]:
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        return []
    if start_date > end_date:
        return []

    normalized_interval = interval.strip().lower()
    if normalized_interval not in SUPPORTED_YFINANCE_INTERVALS:
        allowed = ', '.join(sorted(SUPPORTED_YFINANCE_INTERVALS))
        raise ValueError(f'interval must be one of: {allowed}')

    try:
        import yfinance as yf
    except ModuleNotFoundError as exc:
        raise TickerPriceError('yfinance is not installed') from exc

    try:
        history = yf.Ticker(normalized_ticker).history(
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            interval=normalized_interval,
            auto_adjust=False,
        )
    except Exception as exc:
        raise TickerPriceError(f'failed to fetch ticker price history for {normalized_ticker}') from exc

    if history is None:
        return []

    is_empty = bool(getattr(history, 'empty', False))
    columns = getattr(history, 'columns', [])
    if is_empty or 'Close' not in columns:
        return []

    by_day: dict[date, float] = {}
    for index, row in history.iterrows():
        row_date = _index_to_berlin_date(index)
        if row_date is None or row_date < start_date or row_date > end_date:
            continue

        close_price = _extract_close_price(row)
        if close_price is None:
            continue
        by_day[row_date] = close_price

    return [PricePoint(date_bucket_berlin=day, close_price=by_day[day]) for day in sorted(by_day.keys())]


def _index_to_berlin_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return to_berlin_date(value)
    if isinstance(value, date):
        return value

    if hasattr(value, 'to_pydatetime'):
        converted = value.to_pydatetime()
        if isinstance(converted, datetime):
            return to_berlin_date(converted)
        if isinstance(converted, date):
            return converted

    return None


def _extract_close_price(row: Any) -> float | None:
    close_raw: Any = row.get('Close') if hasattr(row, 'get') else None
    if close_raw is None:
        return None

    try:
        close_price = float(close_raw)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(close_price):
        return None

    return close_price
