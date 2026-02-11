from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.main import app
from app.db.session import SessionLocal
from app.models.comment import Comment
from app.models.daily_score import DailyScore
from app.models.mention import Mention
from app.models.pull_run import PullRun
from app.models.stance import Stance
from app.models.submission import Submission


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
                valid_count=9,
                score_sum_unweighted=2.7,
                weighted_numerator=3.6,
                weighted_denominator=9.0,
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

    eval_resp = client.get('/api/evaluate?max_rows=50')
    assert eval_resp.status_code == 200
    eval_payload = eval_resp.json()
    assert eval_payload['rows_evaluated'] > 0
    assert 'macro_f1' in eval_payload


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
                    valid_count=9,
                    score_sum_unweighted=3.6,
                    weighted_numerator=4.5,
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
                    score_unweighted=0.1,
                    score_weighted=0.2,
                    valid_count=4,
                    score_sum_unweighted=0.4,
                    weighted_numerator=0.8,
                    weighted_denominator=4.0,
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
    assert aapl['valid_count'] == 13
    assert 'ci95_low_unweighted' in aapl
    assert 'ci95_high_unweighted' in aapl
    assert aapl['bullish_count'] == 8
    assert abs(aapl['score_weighted'] - ((4.5 + 0.8) / (9 + 4))) < 1e-9


def test_api_results_supports_7d_window_aggregation() -> None:
    end_date = date.today()
    prev_date = end_date - timedelta(days=1)

    with SessionLocal() as session:
        session.execute(
            delete(DailyScore).where(
                DailyScore.subreddit == 'stocks',
                DailyScore.ticker == 'MSFT',
                DailyScore.date_bucket_berlin.in_([prev_date, end_date]),
            )
        )
        session.add_all(
            [
                DailyScore(
                    date_bucket_berlin=prev_date,
                    subreddit='stocks',
                    ticker='MSFT',
                    score_unweighted=0.1,
                    score_weighted=0.2,
                    valid_count=5,
                    score_sum_unweighted=0.5,
                    weighted_numerator=1.0,
                    weighted_denominator=5.0,
                    mention_count=6,
                    bullish_count=2,
                    bearish_count=1,
                    neutral_count=2,
                    unclear_count=1,
                    unclear_rate=1 / 6,
                ),
                DailyScore(
                    date_bucket_berlin=end_date,
                    subreddit='stocks',
                    ticker='MSFT',
                    score_unweighted=0.5,
                    score_weighted=0.6,
                    valid_count=7,
                    score_sum_unweighted=3.5,
                    weighted_numerator=4.2,
                    weighted_denominator=7.0,
                    mention_count=8,
                    bullish_count=5,
                    bearish_count=1,
                    neutral_count=1,
                    unclear_count=1,
                    unclear_rate=1 / 8,
                ),
            ]
        )
        session.commit()

    client = TestClient(app)
    response = client.get(f'/api/results?date={end_date.isoformat()}&subreddit=stocks&window=7d')
    assert response.status_code == 200
    payload = response.json()
    assert payload['window'] == '7d'
    assert payload['date_from'] == (end_date - timedelta(days=6)).isoformat()
    assert payload['date_to'] == end_date.isoformat()

    msft = next((row for row in payload['rows'] if row['ticker'] == 'MSFT'), None)
    assert msft is not None
    assert msft['mention_count'] == 14
    assert msft['valid_count'] == 12
    assert abs(msft['score_weighted'] - ((1.0 + 4.2) / (5 + 7))) < 1e-9


def test_api_results_window_uses_content_timestamps() -> None:
    target_date = date(2025, 1, 8)
    now = datetime(2025, 1, 8, 12, 0, tzinfo=timezone.utc)

    with SessionLocal() as session:
        session.execute(delete(Stance).where(Stance.target_id.in_(['subw24a', 'subw7a'])))
        session.execute(delete(Comment).where(Comment.id.in_(['comw24a', 'comw7a'])))
        session.execute(delete(Submission).where(Submission.id.in_(['subw24a', 'subw7a'])))

        run = PullRun(
            pulled_at_utc=now,
            date_bucket_berlin=target_date,
            subreddit='stocks',
            sort='top',
            t_param='day',
            limit=10,
            status='success',
            error=None,
        )
        session.add(run)
        session.flush()

        sub_recent = Submission(
            id='subw24a',
            subreddit='stocks',
            created_utc=datetime(2025, 1, 8, 10, 0, tzinfo=timezone.utc),
            title='AAPL today',
            selftext='',
            url='https://reddit.com/r/stocks/comments/subw24a',
            score=10,
            num_comments=0,
            permalink='/r/stocks/comments/subw24a',
            pull_run_id=run.id,
        )
        sub_older = Submission(
            id='subw7a',
            subreddit='stocks',
            created_utc=datetime(2025, 1, 4, 10, 0, tzinfo=timezone.utc),
            title='TSLA this week',
            selftext='',
            url='https://reddit.com/r/stocks/comments/subw7a',
            score=8,
            num_comments=0,
            permalink='/r/stocks/comments/subw7a',
            pull_run_id=run.id,
        )
        session.add_all([sub_recent, sub_older])
        session.add_all(
            [
                Stance(
                    target_type='submission',
                    target_id='subw24a',
                    ticker='AAPL',
                    stance_label='BULLISH',
                    stance_score=0.7,
                    confidence=0.8,
                    model_version='deterministic-v1',
                    context_text='',
                ),
                Stance(
                    target_type='submission',
                    target_id='subw7a',
                    ticker='TSLA',
                    stance_label='BULLISH',
                    stance_score=0.6,
                    confidence=0.8,
                    model_version='deterministic-v1',
                    context_text='',
                ),
            ]
        )
        session.commit()

    client = TestClient(app)
    resp_24 = client.get('/api/results?date=2025-01-08&subreddit=stocks&window=24h')
    resp_7d = client.get('/api/results?date=2025-01-08&subreddit=stocks&window=7d')
    assert resp_24.status_code == 200
    assert resp_7d.status_code == 200

    rows_24 = resp_24.json()['rows']
    rows_7d = resp_7d.json()['rows']
    mentions_24 = sum(int(row['mention_count']) for row in rows_24)
    mentions_7 = sum(int(row['mention_count']) for row in rows_7d)
    assert mentions_7 > mentions_24
    assert any(row['ticker'] == 'TSLA' for row in rows_7d)


def test_api_quality_endpoint_shape_and_metrics() -> None:
    target_date = date(2025, 1, 1)
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    with SessionLocal() as session:
        session.execute(delete(Mention).where(Mention.target_id.in_(['subq1', 'comq1'])))
        session.execute(delete(Stance).where(Stance.target_id.in_(['subq1', 'comq1'])))
        session.execute(delete(Comment).where(Comment.id == 'comq1'))
        session.execute(delete(Submission).where(Submission.id == 'subq1'))

        run = PullRun(
            pulled_at_utc=now,
            date_bucket_berlin=target_date,
            subreddit='stocks',
            sort='top',
            t_param='day',
            limit=10,
            status='success',
            error=None,
        )
        session.add(run)
        session.flush()

        submission = Submission(
            id='subq1',
            subreddit='stocks',
            created_utc=now,
            title='AAPL thread',
            selftext='',
            url='https://reddit.com/r/stocks/comments/subq1',
            score=10,
            num_comments=3,
            permalink='/r/stocks/comments/subq1',
            pull_run_id=run.id,
        )
        session.add(submission)
        comment = Comment(
            id='comq1',
            submission_id='subq1',
            parent_id='subq1',
            depth=0,
            author='tester',
            created_utc=now,
            score=1,
            body='agree',
            permalink='/r/stocks/comments/subq1/comq1',
        )
        session.add(comment)
        session.add(
            Mention(
                target_type='comment',
                target_id='comq1',
                ticker='AAPL',
                confidence=0.4,
                source='context',
                span_start=-1,
                span_end=-1,
            )
        )
        session.add(
            Stance(
                target_type='comment',
                target_id='comq1',
                ticker='AAPL',
                stance_label='UNCLEAR',
                stance_score=0.0,
                confidence=0.5,
                model_version='deterministic-v1',
                context_text='...',
            )
        )
        session.commit()

    client = TestClient(app)
    resp = client.get('/api/quality?date=2025-01-01&subreddit=stocks')
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['subreddit'] == 'stocks'
    assert payload['pulls_total'] >= 1
    assert payload['submissions'] >= 1
    assert payload['mentions_total'] >= 1
    assert payload['context_mentions'] >= 1
    assert payload['unclear_count'] >= 1
    assert 'model_versions' in payload
    assert 'mention_sources' in payload
