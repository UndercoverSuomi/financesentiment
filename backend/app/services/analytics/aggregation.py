from __future__ import annotations

from datetime import date, timedelta
import math

from app.models.daily_score import DailyScore

DayTickerMap = dict[date, dict[str, dict[str, float]]]


def aggregate_day_ticker(
    *,
    rows: list[DailyScore],
    start_date: date,
    end_date: date,
) -> DayTickerMap:
    out: DayTickerMap = {}
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

        valid_count = coalesce_valid_count(row)
        score_sum = coalesce_score_sum(row, valid_count)
        weighted_numerator = coalesce_weighted_num(row, valid_count)
        weighted_denominator = coalesce_weighted_den(row, valid_count)

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


def coalesce_valid_count(row: DailyScore) -> int:
    valid = int(row.valid_count) if isinstance(row.valid_count, int) else 0
    if valid > 0:
        return valid
    return max(int(row.mention_count) - int(row.unclear_count), 0)


def coalesce_score_sum(row: DailyScore, valid_count: int) -> float:
    if _is_finite_number(row.score_sum_unweighted):
        return float(row.score_sum_unweighted)
    return float(row.score_unweighted) * float(valid_count)


def coalesce_weighted_num(row: DailyScore, valid_count: int) -> float:
    if _is_finite_number(row.weighted_numerator):
        return float(row.weighted_numerator)
    return float(row.score_weighted) * float(valid_count)


def coalesce_weighted_den(row: DailyScore, valid_count: int) -> float:
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
