from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_ingestion_service, get_pull_job_service
from app.api.route_utils import resolve_subreddit_param
from app.core.config import get_settings
from app.models.pull_run import PullRun
from app.schemas.api import PullJobStatus, PullRunStatusOut, PullStatusOverview, PullSummary, SubredditsResponse
from app.services.ingestion_service import IngestionService, PullExecutionResult
from app.services.pull_job_service import PullJobService
from app.utils.timezone import utc_now

router = APIRouter()
settings = get_settings()


@router.get('/subreddits', response_model=SubredditsResponse)
def list_subreddits() -> SubredditsResponse:
    return SubredditsResponse(
        subreddits=settings.subreddits,
        default_sort=settings.pull_sort,
        default_t_param=settings.pull_t_param,
        default_limit=settings.pull_limit,
    )


@router.post('/pull', response_model=PullSummary)
async def pull_subreddit(
    subreddit: str = Query(...),
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> PullSummary:
    if subreddit not in settings.subreddits:
        raise HTTPException(status_code=400, detail=f'Subreddit {subreddit} is not in configured list')
    result = await ingestion_service.pull_subreddit(db, subreddit=subreddit)
    return _pull_summary_from_result(result)


@router.post('/pull_all', response_model=list[PullSummary])
async def pull_all(
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> list[PullSummary]:
    results = await ingestion_service.pull_all(db)
    return [_pull_summary_from_result(row) for row in results]


@router.post('/pull/start', response_model=PullJobStatus)
async def start_pull_job(
    subreddit: str | None = Query(default=None),
    pull_job_service: PullJobService = Depends(get_pull_job_service),
) -> PullJobStatus:
    selected_subreddit = resolve_subreddit_param(subreddit)
    snapshot = pull_job_service.start_job(subreddit=selected_subreddit)
    return _pull_job_status_from_snapshot(snapshot)


@router.get('/pull/jobs/{job_id}', response_model=PullJobStatus)
def get_pull_job(
    job_id: str,
    pull_job_service: PullJobService = Depends(get_pull_job_service),
) -> PullJobStatus:
    snapshot = pull_job_service.get_job(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f'pull job not found: {job_id}')
    return _pull_job_status_from_snapshot(snapshot)


@router.get('/pull/status', response_model=PullStatusOverview)
def get_pull_status(db: Session = Depends(get_db)) -> PullStatusOverview:
    latest_by_subreddit: list[PullRunStatusOut] = []
    last_success_by_subreddit: list[PullRunStatusOut] = []
    running_subreddits: list[str] = []
    failed_subreddits: list[str] = []
    subreddits_without_success: list[str] = []

    for subreddit in settings.subreddits:
        latest = db.execute(
            select(PullRun)
            .where(PullRun.subreddit == subreddit)
            .order_by(PullRun.pulled_at_utc.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is not None:
            latest_out = PullRunStatusOut(
                subreddit=latest.subreddit,
                status=latest.status,
                pulled_at_utc=latest.pulled_at_utc,
                date_bucket_berlin=latest.date_bucket_berlin,
                error=latest.error,
            )
            latest_by_subreddit.append(latest_out)
            if latest.status == 'running':
                running_subreddits.append(latest.subreddit)
            if latest.status == 'failed':
                failed_subreddits.append(latest.subreddit)

        latest_success = db.execute(
            select(PullRun)
            .where(
                PullRun.subreddit == subreddit,
                PullRun.status == 'success',
            )
            .order_by(PullRun.pulled_at_utc.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest_success is None:
            subreddits_without_success.append(subreddit)
        else:
            last_success_by_subreddit.append(
                PullRunStatusOut(
                    subreddit=latest_success.subreddit,
                    status=latest_success.status,
                    pulled_at_utc=latest_success.pulled_at_utc,
                    date_bucket_berlin=latest_success.date_bucket_berlin,
                    error=latest_success.error,
                )
            )

    overall_success_query = select(func.max(PullRun.pulled_at_utc)).where(PullRun.status == 'success')
    if settings.subreddits:
        overall_success_query = overall_success_query.where(PullRun.subreddit.in_(settings.subreddits))
    overall_last_success_utc = db.execute(overall_success_query).scalar_one_or_none()

    return PullStatusOverview(
        generated_at_utc=utc_now(),
        overall_last_success_utc=overall_last_success_utc,
        running_subreddits=running_subreddits,
        failed_subreddits=failed_subreddits,
        subreddits_without_success=subreddits_without_success,
        latest_by_subreddit=latest_by_subreddit,
        last_success_by_subreddit=last_success_by_subreddit,
    )


def _pull_job_status_from_snapshot(snapshot) -> PullJobStatus:
    declared_total_steps = max(int(snapshot.total_steps), 0)
    completed_steps = max(int(snapshot.completed_steps), 0)
    if declared_total_steps > 0:
        completed_steps = min(completed_steps, declared_total_steps)
    total_steps_for_progress = max(declared_total_steps, 1)

    current_subreddit_progress = _current_subreddit_progress(
        current_total_submissions=snapshot.current_total_submissions,
        current_processed_submissions=snapshot.current_processed_submissions,
        current_phase=snapshot.current_phase,
    )
    if snapshot.current_subreddit and snapshot.status in {'queued', 'running'} and completed_steps < total_steps_for_progress:
        progress = min(max((completed_steps + current_subreddit_progress) / total_steps_for_progress, 0.0), 1.0)
    else:
        progress = min(max(completed_steps / total_steps_for_progress, 0.0), 1.0)

    return PullJobStatus(
        job_id=snapshot.job_id,
        mode=snapshot.mode,
        requested_subreddit=snapshot.requested_subreddit,
        status=snapshot.status,
        started_at_utc=snapshot.started_at_utc,
        finished_at_utc=snapshot.finished_at_utc,
        total_steps=snapshot.total_steps,
        completed_steps=snapshot.completed_steps,
        progress=progress,
        current_subreddit=snapshot.current_subreddit,
        current_phase=snapshot.current_phase,
        current_subreddit_progress=current_subreddit_progress,
        current_total_submissions=snapshot.current_total_submissions,
        current_processed_submissions=snapshot.current_processed_submissions,
        current_submission_id=snapshot.current_submission_id,
        current_submissions=snapshot.current_submissions,
        current_comments=snapshot.current_comments,
        current_mentions=snapshot.current_mentions,
        current_stance_rows=snapshot.current_stance_rows,
        current_partial_errors=snapshot.current_partial_errors,
        heartbeat_utc=snapshot.heartbeat_utc,
        summaries=[_pull_summary_from_result(row) for row in snapshot.results],
        error=snapshot.error,
    )


def _current_subreddit_progress(
    *,
    current_total_submissions: int | None,
    current_processed_submissions: int,
    current_phase: str | None,
) -> float:
    if current_total_submissions is None:
        if current_phase in {'aggregating', 'subreddit_done', 'finished'}:
            return 1.0
        return 0.0

    total_submissions = int(current_total_submissions)
    if total_submissions <= 0:
        return 1.0

    processed_submissions = max(int(current_processed_submissions), 0)
    return min(max(processed_submissions / total_submissions, 0.0), 1.0)


def _pull_summary_from_result(result: PullExecutionResult) -> PullSummary:
    return PullSummary(
        pull_run_id=result.pull_run_id,
        subreddit=result.subreddit,
        date_bucket_berlin=result.date_bucket_berlin,
        status=result.status,
        submissions=result.submissions,
        comments=result.comments,
        mentions=result.mentions,
        stance_rows=result.stance_rows,
        error=result.error,
    )
