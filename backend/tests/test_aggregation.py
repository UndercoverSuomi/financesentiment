from __future__ import annotations

import math
from datetime import datetime, timezone

from app.services.aggregation_service import AggregationRecord, compute_daily_scores


def test_aggregation_weighted_and_unweighted() -> None:
    now = datetime(2026, 2, 11, 12, 0, tzinfo=timezone.utc)
    records = [
        AggregationRecord(
            ticker='AAPL',
            stance_label='BULLISH',
            stance_score=0.8,
            upvote_score=9,
            depth=0,
            created_utc=now,
        ),
        AggregationRecord(
            ticker='AAPL',
            stance_label='BEARISH',
            stance_score=-0.4,
            upvote_score=3,
            depth=1,
            created_utc=now,
        ),
        AggregationRecord(
            ticker='AAPL',
            stance_label='UNCLEAR',
            stance_score=0.0,
            upvote_score=2,
            depth=2,
            created_utc=now,
        ),
    ]

    scores = compute_daily_scores(
        records,
        use_depth_decay=False,
        lambda_depth=0.15,
        use_time_decay=False,
        lambda_time=0.05,
        reference_time=now,
    )

    row = scores['AAPL']
    assert row.mention_count == 3
    assert row.valid_count == 2
    assert row.bullish_count == 1
    assert row.bearish_count == 1
    assert row.unclear_count == 1
    assert row.unclear_rate == 1 / 3

    assert abs(row.score_unweighted - 0.2) < 1e-6
    assert abs(row.score_sum_unweighted - 0.4) < 1e-6

    expected_weighted = (math.log(10) * 0.8 + math.log(4) * -0.4) / (math.log(10) + math.log(4))
    assert abs(row.score_weighted - expected_weighted) < 1e-6
    assert abs(row.weighted_numerator - (math.log(10) * 0.8 + math.log(4) * -0.4)) < 1e-6
    assert abs(row.weighted_denominator - (math.log(10) + math.log(4))) < 1e-6
    assert row.score_stddev_unweighted > 0
    assert row.ci95_low_unweighted <= row.score_unweighted <= row.ci95_high_unweighted
