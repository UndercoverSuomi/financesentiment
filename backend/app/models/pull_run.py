from __future__ import annotations

from sqlalchemy import Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PullRun(Base):
    __tablename__ = 'pull_runs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pulled_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    date_bucket_berlin: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    subreddit: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sort: Mapped[str] = mapped_column(String(32), nullable=False)
    t_param: Mapped[str] = mapped_column(String(32), nullable=False)
    limit: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='running')
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    submissions = relationship('Submission', back_populates='pull_run')
