from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()
database_url = settings.resolved_database_url

if database_url.startswith('sqlite:///'):
    Path(settings.backend_root / 'data').mkdir(parents=True, exist_ok=True)

engine = create_engine(
    database_url,
    connect_args={'check_same_thread': False} if database_url.startswith('sqlite') else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
