from __future__ import annotations

from functools import lru_cache
from typing import Generator

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.ingestion_service import IngestionService


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@lru_cache(maxsize=1)
def get_ingestion_service() -> IngestionService:
    return IngestionService(settings=get_settings())
