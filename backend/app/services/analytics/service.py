from __future__ import annotations

from datetime import date

from app.models.daily_score import DailyScore
from app.schemas.api import AnalyticsResponse
from app.services.analytics.aggregation import aggregate_day_ticker
from app.services.analytics.insights import (
    build_analytics_trend,
    build_correlations,
    build_market_summary,
    build_movers,
    build_regime_breakdown,
    build_rolling_trend,
    build_subreddit_snapshot,
    build_ticker_insights,
    build_weekday_profile,
)


def build_analytics_response(
    *,
    rows: list[DailyScore],
    selected_subreddit: str | None,
    days: int,
    start_date: date,
    end_date: date,
) -> AnalyticsResponse:
    day_ticker = aggregate_day_ticker(
        rows=rows,
        start_date=start_date,
        end_date=end_date,
    )
    trend = build_analytics_trend(
        day_ticker=day_ticker,
        start_date=start_date,
        end_date=end_date,
    )
    rolling_trend = build_rolling_trend(trend)
    market_summary = build_market_summary(trend)
    regime_breakdown = build_regime_breakdown(trend)
    correlations = build_correlations(trend)
    movers_up, movers_down = build_movers(day_ticker=day_ticker, trend=trend)
    ticker_insights = build_ticker_insights(day_ticker=day_ticker, trend=trend)
    weekday_profile = build_weekday_profile(trend)
    subreddit_snapshot = build_subreddit_snapshot(
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
