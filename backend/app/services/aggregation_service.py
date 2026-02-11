from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(slots=True)
class AggregationRecord:
    ticker: str
    stance_label: str
    stance_score: float
    upvote_score: int
    depth: int
    created_utc: datetime


@dataclass(slots=True)
class AggregationMetrics:
    score_unweighted: float
    score_weighted: float
    mention_count: int
    bullish_count: int
    bearish_count: int
    neutral_count: int
    unclear_count: int
    unclear_rate: float


def compute_daily_scores(
    records: list[AggregationRecord],
    *,
    use_depth_decay: bool,
    lambda_depth: float,
    use_time_decay: bool,
    lambda_time: float,
    reference_time: datetime | None = None,
) -> dict[str, AggregationMetrics]:
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    grouped: dict[str, list[AggregationRecord]] = defaultdict(list)
    for record in records:
        grouped[record.ticker].append(record)

    output: dict[str, AggregationMetrics] = {}
    for ticker, ticker_records in grouped.items():
        mention_count = len(ticker_records)
        bullish_count = sum(1 for r in ticker_records if r.stance_label == 'BULLISH')
        bearish_count = sum(1 for r in ticker_records if r.stance_label == 'BEARISH')
        neutral_count = sum(1 for r in ticker_records if r.stance_label == 'NEUTRAL')
        unclear_count = sum(1 for r in ticker_records if r.stance_label == 'UNCLEAR')

        valid = [r for r in ticker_records if r.stance_label != 'UNCLEAR']
        if valid:
            score_unweighted = sum(r.stance_score for r in valid) / len(valid)
        else:
            score_unweighted = 0.0

        weighted_numerator = 0.0
        weighted_denominator = 0.0
        for r in valid:
            weight = math.log(1 + max(r.upvote_score, 0))
            if use_depth_decay:
                weight *= math.exp(-lambda_depth * max(r.depth, 0))
            if use_time_decay:
                age_hours = max((reference_time - r.created_utc).total_seconds() / 3600.0, 0.0)
                weight *= math.exp(-lambda_time * age_hours)
            weighted_numerator += weight * r.stance_score
            weighted_denominator += weight

        if weighted_denominator > 0:
            score_weighted = weighted_numerator / weighted_denominator
        else:
            score_weighted = score_unweighted

        output[ticker] = AggregationMetrics(
            score_unweighted=score_unweighted,
            score_weighted=score_weighted,
            mention_count=mention_count,
            bullish_count=bullish_count,
            bearish_count=bearish_count,
            neutral_count=neutral_count,
            unclear_count=unclear_count,
            unclear_rate=(unclear_count / mention_count if mention_count else 0.0),
        )

    return output
