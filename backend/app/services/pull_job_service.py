from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from app.core.config import Settings
from app.db.session import SessionLocal
from app.services.ingestion_service import IngestionService, PullExecutionResult, PullProgressUpdate
from app.utils.timezone import to_berlin_date, utc_now


@dataclass(slots=True)
class PullJobSnapshot:
    job_id: str
    mode: str
    requested_subreddit: str | None
    status: str
    started_at_utc: datetime
    finished_at_utc: datetime | None
    total_steps: int
    completed_steps: int
    current_subreddit: str | None
    current_phase: str | None
    current_total_submissions: int | None
    current_processed_submissions: int
    current_submission_id: str | None
    current_submissions: int
    current_comments: int
    current_mentions: int
    current_stance_rows: int
    current_partial_errors: int
    heartbeat_utc: datetime | None
    results: list[PullExecutionResult]
    error: str | None


@dataclass(slots=True)
class _PullJobState:
    job_id: str
    mode: str
    requested_subreddit: str | None
    status: str
    started_at_utc: datetime
    finished_at_utc: datetime | None = None
    total_steps: int = 0
    completed_steps: int = 0
    current_subreddit: str | None = None
    current_phase: str | None = None
    current_total_submissions: int | None = None
    current_processed_submissions: int = 0
    current_submission_id: str | None = None
    current_submissions: int = 0
    current_comments: int = 0
    current_mentions: int = 0
    current_stance_rows: int = 0
    current_partial_errors: int = 0
    heartbeat_utc: datetime | None = None
    results: list[PullExecutionResult] = field(default_factory=list)
    error: str | None = None


class PullJobService:
    def __init__(self, settings: Settings, ingestion_service: IngestionService) -> None:
        self._settings = settings
        self._ingestion_service = ingestion_service
        self._jobs: dict[str, _PullJobState] = {}
        self._lock = Lock()
        self._active_job_id: str | None = None

    def start_job(self, subreddit: str | None) -> PullJobSnapshot:
        with self._lock:
            if self._active_job_id:
                active = self._jobs.get(self._active_job_id)
                if active and active.status in {'queued', 'running'}:
                    return PullJobSnapshot(
                        job_id=active.job_id,
                        mode=active.mode,
                        requested_subreddit=active.requested_subreddit,
                        status=active.status,
                        started_at_utc=active.started_at_utc,
                        finished_at_utc=active.finished_at_utc,
                        total_steps=active.total_steps,
                        completed_steps=active.completed_steps,
                        current_subreddit=active.current_subreddit,
                        current_phase=active.current_phase,
                        current_total_submissions=active.current_total_submissions,
                        current_processed_submissions=active.current_processed_submissions,
                        current_submission_id=active.current_submission_id,
                        current_submissions=active.current_submissions,
                        current_comments=active.current_comments,
                        current_mentions=active.current_mentions,
                        current_stance_rows=active.current_stance_rows,
                        current_partial_errors=active.current_partial_errors,
                        heartbeat_utc=active.heartbeat_utc,
                        results=list(active.results),
                        error=active.error,
                    )
                self._active_job_id = None

            if subreddit:
                subreddits = [subreddit]
                mode = 'single'
            else:
                subreddits = list(self._settings.subreddits)
                mode = 'all'

            now = datetime.now(timezone.utc)
            job_id = uuid4().hex
            job = _PullJobState(
                job_id=job_id,
                mode=mode,
                requested_subreddit=subreddit,
                status='queued',
                started_at_utc=now,
                total_steps=len(subreddits),
            )
            self._jobs[job_id] = job
            self._active_job_id = job_id

        loop = asyncio.get_running_loop()
        loop.create_task(self._run_job(job_id=job_id, subreddits=subreddits))
        return self._snapshot(job_id)

    def get_job(self, job_id: str) -> PullJobSnapshot | None:
        with self._lock:
            if job_id not in self._jobs:
                return None
        return self._snapshot(job_id)

    def _snapshot(self, job_id: str) -> PullJobSnapshot:
        with self._lock:
            job = self._jobs[job_id]
            return PullJobSnapshot(
                job_id=job.job_id,
                mode=job.mode,
                requested_subreddit=job.requested_subreddit,
                status=job.status,
                started_at_utc=job.started_at_utc,
                finished_at_utc=job.finished_at_utc,
                total_steps=job.total_steps,
                completed_steps=job.completed_steps,
                current_subreddit=job.current_subreddit,
                current_phase=job.current_phase,
                current_total_submissions=job.current_total_submissions,
                current_processed_submissions=job.current_processed_submissions,
                current_submission_id=job.current_submission_id,
                current_submissions=job.current_submissions,
                current_comments=job.current_comments,
                current_mentions=job.current_mentions,
                current_stance_rows=job.current_stance_rows,
                current_partial_errors=job.current_partial_errors,
                heartbeat_utc=job.heartbeat_utc,
                results=list(job.results),
                error=job.error,
            )

    async def _run_job(self, *, job_id: str, subreddits: list[str]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = 'running'

        fatal_error: str | None = None
        for subreddit in subreddits:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.current_subreddit = subreddit
                job.current_phase = 'subreddit_started'
                job.current_total_submissions = None
                job.current_processed_submissions = 0
                job.current_submission_id = None
                job.current_submissions = 0
                job.current_comments = 0
                job.current_mentions = 0
                job.current_stance_rows = 0
                job.current_partial_errors = 0
                job.heartbeat_utc = datetime.now(timezone.utc)

            def on_progress(update: PullProgressUpdate) -> None:
                self._apply_progress_update(job_id=job_id, update=update)

            try:
                with SessionLocal() as session:
                    result = await self._ingestion_service.pull_subreddit(
                        session,
                        subreddit=subreddit,
                        on_progress=on_progress,
                    )
            except Exception as exc:  # pragma: no cover - safety net
                fatal_error = str(exc)
                result = PullExecutionResult(
                    pull_run_id=-1,
                    subreddit=subreddit,
                    date_bucket_berlin=to_berlin_date(utc_now()),
                    status='failed',
                    submissions=0,
                    comments=0,
                    mentions=0,
                    stance_rows=0,
                    error=fatal_error[:4000],
                )

            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.results.append(result)
                job.completed_steps += 1
                job.current_phase = 'subreddit_done'
                job.current_total_submissions = max(job.current_total_submissions or 0, job.current_processed_submissions)
                job.current_submission_id = None
                job.heartbeat_utc = datetime.now(timezone.utc)
            if job.completed_steps < len(subreddits):
                pause = max(float(self._settings.pull_subreddit_pause_seconds), 0.0)
                if pause > 0:
                    await asyncio.sleep(pause)

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            failed = [row for row in job.results if row.status != 'success']
            if fatal_error:
                job.status = 'failed'
                job.error = fatal_error[:4000]
            elif failed and len(failed) < len(job.results):
                job.status = 'partial_success'
                job.error = '; '.join(f'{row.subreddit}:{row.status}' for row in failed[:6])
            elif failed:
                job.status = 'failed'
                job.error = '; '.join(f'{row.subreddit}:{row.status}' for row in failed[:6])
            else:
                job.status = 'success'
                job.error = None
            job.current_subreddit = None
            job.current_phase = 'finished'
            job.current_submission_id = None
            job.finished_at_utc = datetime.now(timezone.utc)
            job.heartbeat_utc = datetime.now(timezone.utc)
            if self._active_job_id == job_id:
                self._active_job_id = None

    def _apply_progress_update(self, *, job_id: str, update: PullProgressUpdate) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if job.current_subreddit and update.subreddit != job.current_subreddit:
                return
            job.current_phase = update.phase
            job.current_total_submissions = update.total_submissions
            job.current_processed_submissions = max(update.processed_submissions, 0)
            job.current_submission_id = update.current_submission_id
            job.current_submissions = max(update.submissions, 0)
            job.current_comments = max(update.comments, 0)
            job.current_mentions = max(update.mentions, 0)
            job.current_stance_rows = max(update.stance_rows, 0)
            job.current_partial_errors = max(update.partial_errors, 0)
            job.heartbeat_utc = datetime.now(timezone.utc)
