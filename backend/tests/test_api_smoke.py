from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.main import app
from app.db.session import SessionLocal
from app.models.daily_score import DailyScore


def test_api_smoke_subreddits_and_results_shape() -> None:
    today = date.today()

    with SessionLocal() as session:
        session.execute(
            delete(DailyScore).where(
                DailyScore.date_bucket_berlin == today,
                DailyScore.subreddit == 'stocks',
            )
        )
        session.add(
            DailyScore(
                date_bucket_berlin=today,
                subreddit='stocks',
                ticker='AAPL',
                score_unweighted=0.3,
                score_weighted=0.4,
                mention_count=10,
                bullish_count=6,
                bearish_count=2,
                neutral_count=1,
                unclear_count=1,
                unclear_rate=0.1,
            )
        )
        session.commit()

    client = TestClient(app)

    sub_resp = client.get('/api/subreddits')
    assert sub_resp.status_code == 200
    assert 'stocks' in sub_resp.json()['subreddits']

    result_resp = client.get(f'/api/results?date={today.isoformat()}&subreddit=stocks')
    assert result_resp.status_code == 200
    payload = result_resp.json()
    assert payload['subreddit'] == 'stocks'
    assert any(row['ticker'] == 'AAPL' for row in payload['rows'])


def test_api_results_defaults_to_all_subreddits_aggregation() -> None:
    today = date.today()

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
                    score_unweighted=0.4,
                    score_weighted=0.5,
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
                    score_unweighted=0.1,
                    score_weighted=0.2,
                    mention_count=5,
                    bullish_count=2,
                    bearish_count=1,
                    neutral_count=1,
                    unclear_count=1,
                    unclear_rate=0.2,
                ),
            ]
        )
        session.commit()

    client = TestClient(app)
    result_resp = client.get(f'/api/results?date={today.isoformat()}')
    assert result_resp.status_code == 200
    payload = result_resp.json()
    assert payload['subreddit'] == 'ALL'

    aapl = next((row for row in payload['rows'] if row['ticker'] == 'AAPL'), None)
    assert aapl is not None
    assert aapl['mention_count'] == 15
    assert aapl['bullish_count'] == 8
    assert abs(aapl['score_weighted'] - ((0.5 * 10 + 0.2 * 5) / 15)) < 1e-9
