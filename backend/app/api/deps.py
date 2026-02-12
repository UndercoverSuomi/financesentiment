from __future__ import annotations

from functools import lru_cache
from typing import Generator

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.evaluation_service import EvaluationService
from app.services.ingestion_service import IngestionService
from app.services.pull_job_service import PullJobService


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@lru_cache(maxsize=1)
def get_ingestion_service() -> IngestionService:
    return IngestionService(settings=get_settings())


@lru_cache(maxsize=1)
def get_evaluation_service() -> EvaluationService:
    return EvaluationService(settings=get_settings())


@lru_cache(maxsize=1)
def get_pull_job_service() -> PullJobService:
    return PullJobService(
        settings=get_settings(),
        ingestion_service=get_ingestion_service(),
    )
