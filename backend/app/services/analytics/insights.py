from __future__ import annotations

from datetime import date, timedelta
import math

from app.models.daily_score import DailyScore
from app.schemas.api import (
    AnalyticsCorrelation,
    AnalyticsDayPoint,
    AnalyticsMarketSummary,
    AnalyticsMover,
    AnalyticsRegimeBreakdown,
    AnalyticsRollingPoint,
    AnalyticsSubredditPoint,
    AnalyticsTickerInsight,
    AnalyticsWeekdayPoint,
)
from app.services.analytics.aggregation import (
    DayTickerMap,
    coalesce_score_sum,
    coalesce_valid_count,
    coalesce_weighted_den,
    coalesce_weighted_num,
)


def build_analytics_trend(
    *,
    day_ticker: DayTickerMap,
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


def build_market_summary(trend: list[AnalyticsDayPoint]) -> AnalyticsMarketSummary:
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


def build_rolling_trend(trend: list[AnalyticsDayPoint]) -> list[AnalyticsRollingPoint]:
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


def build_regime_breakdown(trend: list[AnalyticsDayPoint]) -> AnalyticsRegimeBreakdown:
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


def build_correlations(trend: list[AnalyticsDayPoint]) -> AnalyticsCorrelation:
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


def build_ticker_insights(
    *,
    day_ticker: DayTickerMap,
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


def build_weekday_profile(trend: list[AnalyticsDayPoint]) -> list[AnalyticsWeekdayPoint]:
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


def build_movers(
    *,
    day_ticker: DayTickerMap,
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


def build_subreddit_snapshot(
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
        valid_count = coalesce_valid_count(row)
        bucket['mention_count'] += float(row.mention_count)
        bucket['valid_count'] += float(valid_count)
        bucket['bullish_count'] += float(row.bullish_count)
        bucket['bearish_count'] += float(row.bearish_count)
        bucket['neutral_count'] += float(row.neutral_count)
        bucket['unclear_count'] += float(row.unclear_count)
        bucket['score_sum_unweighted'] += coalesce_score_sum(row, valid_count)
        bucket['weighted_numerator'] += coalesce_weighted_num(row, valid_count)
        bucket['weighted_denominator'] += coalesce_weighted_den(row, valid_count)

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
