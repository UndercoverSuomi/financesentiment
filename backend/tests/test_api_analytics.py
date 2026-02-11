from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.main import app
from app.db.session import SessionLocal
from app.models.daily_score import DailyScore


def test_api_analytics_returns_trend_and_movers() -> None:
    end = date(2026, 2, 11)
    prev = end - timedelta(days=1)

    with SessionLocal() as session:
        session.execute(
            delete(DailyScore).where(
                DailyScore.date_bucket_berlin.in_([prev, end]),
                DailyScore.subreddit.in_(['stocks', 'investing']),
                DailyScore.ticker.in_(['AAPL', 'TSLA']),
            )
        )
        session.add_all(
            [
                DailyScore(
                    date_bucket_berlin=prev,
                    subreddit='stocks',
                    ticker='AAPL',
                    score_unweighted=0.2,
                    score_weighted=0.3,
                    score_stddev_unweighted=0.1,
                    ci95_low_unweighted=0.1,
                    ci95_high_unweighted=0.3,
                    valid_count=8,
                    score_sum_unweighted=1.6,
                    weighted_numerator=2.4,
                    weighted_denominator=8.0,
                    mention_count=10,
                    bullish_count=5,
                    bearish_count=1,
                    neutral_count=2,
                    unclear_count=2,
                    unclear_rate=0.2,
                ),
                DailyScore(
                    date_bucket_berlin=end,
                    subreddit='stocks',
                    ticker='AAPL',
                    score_unweighted=0.6,
                    score_weighted=0.7,
                    score_stddev_unweighted=0.15,
                    ci95_low_unweighted=0.5,
                    ci95_high_unweighted=0.7,
                    valid_count=9,
                    score_sum_unweighted=5.4,
                    weighted_numerator=6.3,
                    weighted_denominator=9.0,
                    mention_count=11,
                    bullish_count=7,
                    bearish_count=1,
                    neutral_count=1,
                    unclear_count=2,
                    unclear_rate=2 / 11,
                ),
                DailyScore(
                    date_bucket_berlin=prev,
                    subreddit='investing',
                    ticker='TSLA',
                    score_unweighted=-0.4,
                    score_weighted=-0.3,
                    score_stddev_unweighted=0.12,
                    ci95_low_unweighted=-0.5,
                    ci95_high_unweighted=-0.3,
                    valid_count=5,
                    score_sum_unweighted=-2.0,
                    weighted_numerator=-1.5,
                    weighted_denominator=5.0,
                    mention_count=6,
                    bullish_count=1,
                    bearish_count=3,
                    neutral_count=1,
                    unclear_count=1,
                    unclear_rate=1 / 6,
                ),
                DailyScore(
                    date_bucket_berlin=end,
                    subreddit='investing',
                    ticker='TSLA',
                    score_unweighted=-0.1,
                    score_weighted=0.0,
                    score_stddev_unweighted=0.1,
                    ci95_low_unweighted=-0.2,
                    ci95_high_unweighted=0.1,
                    valid_count=5,
                    score_sum_unweighted=-0.5,
                    weighted_numerator=0.0,
                    weighted_denominator=5.0,
                    mention_count=7,
                    bullish_count=2,
                    bearish_count=2,
                    neutral_count=1,
                    unclear_count=2,
                    unclear_rate=2 / 7,
                ),
            ]
        )
        session.commit()

    client = TestClient(app)
    response = client.get('/api/analytics?days=3&date=2026-02-11')
    assert response.status_code == 200
    payload = response.json()

    assert payload['days'] == 3
    assert len(payload['trend']) == 3
    assert len(payload['rolling_trend']) == 3
    assert payload['market_summary']['avg_weighted_score'] != 0
    assert payload['market_summary']['active_days'] >= 2
    assert payload['regime_breakdown']['current_regime'] in {'risk-on', 'balanced', 'risk-off', 'no-data'}
    assert 'mentions_vs_abs_score' in payload['correlations']
    assert payload['top_movers_up']
    assert payload['top_movers_down']
    assert payload['ticker_insights']
    assert len(payload['weekday_profile']) == 7
    assert any(row['subreddit'] in {'stocks', 'investing'} for row in payload['subreddit_snapshot'])
