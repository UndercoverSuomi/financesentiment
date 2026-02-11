from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Submission(Base):
    __tablename__ = 'submissions'

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    subreddit: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    selftext: Mapped[str] = mapped_column(Text, nullable=False, default='')
    url: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    num_comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    permalink: Mapped[str] = mapped_column(Text, nullable=False)
    pull_run_id: Mapped[int] = mapped_column(ForeignKey('pull_runs.id', ondelete='CASCADE'), nullable=False, index=True)

    pull_run = relationship('PullRun', back_populates='submissions')
    comments = relationship('Comment', back_populates='submission', cascade='all, delete-orphan')
