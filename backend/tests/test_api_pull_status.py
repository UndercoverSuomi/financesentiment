from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.main import app
from app.models.pull_run import PullRun


def test_pull_status_overview_reports_running_and_failed_latest_runs() -> None:
    with SessionLocal() as session:
        session.execute(
            delete(PullRun).where(PullRun.subreddit.in_(['stocks', 'investing']))
        )
        session.add_all(
            [
                PullRun(
                    pulled_at_utc=datetime(2029, 12, 30, 12, 0, tzinfo=timezone.utc),
                    date_bucket_berlin=date(2029, 12, 30),
                    subreddit='stocks',
                    sort='top',
                    t_param='week',
                    limit=100,
                    status='success',
                    error=None,
                ),
                PullRun(
                    pulled_at_utc=datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc),
                    date_bucket_berlin=date(2030, 1, 1),
                    subreddit='stocks',
                    sort='top',
                    t_param='week',
                    limit=100,
                    status='running',
                    error=None,
                ),
                PullRun(
                    pulled_at_utc=datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc),
                    date_bucket_berlin=date(2030, 1, 1),
                    subreddit='investing',
                    sort='top',
                    t_param='week',
                    limit=100,
                    status='failed',
                    error='boom',
                ),
            ]
        )
        session.commit()

    client = TestClient(app)
    response = client.get('/api/pull/status')
    assert response.status_code == 200
    payload = response.json()

    assert 'stocks' in payload['running_subreddits']
    assert 'investing' in payload['failed_subreddits']
    assert payload['overall_last_success_utc'] is not None

    latest_by_subreddit = {row['subreddit']: row for row in payload['latest_by_subreddit']}
    assert latest_by_subreddit['stocks']['status'] == 'running'
    assert latest_by_subreddit['investing']['status'] == 'failed'

    last_success_by_subreddit = {row['subreddit']: row for row in payload['last_success_by_subreddit']}
    assert last_success_by_subreddit['stocks']['status'] == 'success'
