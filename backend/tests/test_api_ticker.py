from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.main import app
from app.db.session import SessionLocal
from app.models.daily_score import DailyScore
from app.utils.timezone import to_berlin_date, utc_now


def test_ticker_series_collapses_subreddits_when_filter_missing() -> None:
    today = to_berlin_date(utc_now())

    with SessionLocal() as session:
        session.execute(
            delete(DailyScore).where(
                DailyScore.date_bucket_berlin == today,
                DailyScore.ticker == 'AAPL',
            )
        )
        session.add_all(
            [
                DailyScore(
                    date_bucket_berlin=today,
                    subreddit='stocks',
                    ticker='AAPL',
                    score_unweighted=0.5,
                    score_weighted=0.6,
                    valid_count=9,
                    score_sum_unweighted=4.5,
                    weighted_numerator=5.4,
                    weighted_denominator=9.0,
                    mention_count=10,
                    bullish_count=6,
                    bearish_count=2,
                    neutral_count=1,
                    unclear_count=1,
                    unclear_rate=0.1,
                ),
                DailyScore(
                    date_bucket_berlin=today,
                    subreddit='investing',
                    ticker='AAPL',
                    score_unweighted=-0.2,
                    score_weighted=-0.1,
                    valid_count=4,
                    score_sum_unweighted=-0.8,
                    weighted_numerator=-0.4,
                    weighted_denominator=4.0,
                    mention_count=5,
                    bullish_count=1,
                    bearish_count=3,
                    neutral_count=0,
                    unclear_count=1,
                    unclear_rate=0.2,
                ),
            ]
        )
        session.commit()

    client = TestClient(app)
    response = client.get('/api/ticker/AAPL?days=1')
    assert response.status_code == 200
    payload = response.json()
    assert len(payload['series']) == 1
    assert payload['series'][0]['mention_count'] == 15
    assert abs(payload['series'][0]['score_unweighted'] - ((4.5 - 0.8) / (9 + 4))) < 1e-9
    assert abs(payload['series'][0]['score_weighted'] - ((5.4 - 0.4) / (9 + 4))) < 1e-9


def test_ticker_series_rejects_unknown_subreddit() -> None:
    client = TestClient(app)
    response = client.get('/api/ticker/AAPL?days=30&subreddit=unknown_subreddit')
    assert response.status_code == 400
