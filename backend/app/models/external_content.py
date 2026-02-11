from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExternalContent(Base):
    __tablename__ = 'external_content'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey('submissions.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    external_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default='')
    text: Mapped[str] = mapped_column(Text, nullable=False, default='')
    status: Mapped[str] = mapped_column(Text, nullable=False, default='not_attempted')
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
