from __future__ import annotations

from fastapi import APIRouter

from app.api.routes_analytics import router as analytics_router
from app.api.routes_pull import (
    _current_subreddit_progress,
    _pull_job_status_from_snapshot,
    router as pull_router,
)
from app.api.routes_results import router as results_router
from app.api.routes_ticker import router as ticker_router

router = APIRouter(prefix='/api', tags=['api'])
router.include_router(pull_router)
router.include_router(results_router)
router.include_router(analytics_router)
router.include_router(ticker_router)

__all__ = ['router', '_pull_job_status_from_snapshot', '_current_subreddit_progress']
