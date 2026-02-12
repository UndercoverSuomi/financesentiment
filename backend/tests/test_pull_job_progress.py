from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.routes import _current_subreddit_progress, _pull_job_status_from_snapshot


def _snapshot(**overrides):
    now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    base = {
        'job_id': 'job-1',
        'mode': 'all',
        'requested_subreddit': None,
        'status': 'running',
        'started_at_utc': now,
        'finished_at_utc': None,
        'total_steps': 4,
        'completed_steps': 1,
        'current_subreddit': 'stocks',
        'current_phase': 'processing_submission',
        'current_total_submissions': 20,
        'current_processed_submissions': 10,
        'current_submission_id': 'abc123',
        'current_submissions': 8,
        'current_comments': 500,
        'current_mentions': 120,
        'current_stance_rows': 120,
        'current_partial_errors': 2,
        'heartbeat_utc': now,
        'results': [],
        'error': None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_current_subreddit_progress_ratio() -> None:
    assert _current_subreddit_progress(
        current_total_submissions=20,
        current_processed_submissions=5,
        current_phase='processing_submission',
    ) == 0.25


def test_current_subreddit_progress_zero_total_is_complete() -> None:
    assert _current_subreddit_progress(
        current_total_submissions=0,
        current_processed_submissions=0,
        current_phase='listing_complete',
    ) == 1.0


def test_pull_job_status_uses_subreddit_progress_for_overall_progress() -> None:
    status = _pull_job_status_from_snapshot(_snapshot())
    assert status.current_subreddit_progress == 0.5
    assert status.progress == 0.375
    assert status.current_submission_id == 'abc123'
    assert status.current_mentions == 120

