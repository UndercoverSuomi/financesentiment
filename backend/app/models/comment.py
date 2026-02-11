from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Comment(Base):
    __tablename__ = 'comments'

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey('submissions.id', ondelete='CASCADE'), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    author: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    body: Mapped[str] = mapped_column(Text, nullable=False, default='')
    permalink: Mapped[str] = mapped_column(Text, nullable=False, default='')

    submission = relationship('Submission', back_populates='comments')
