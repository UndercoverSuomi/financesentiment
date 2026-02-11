from __future__ import annotations

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Mention(Base):
    __tablename__ = 'mentions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    span_start: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    span_end: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)

    __table_args__ = (
        Index('ix_mentions_target_type_target_id', 'target_type', 'target_id'),
        UniqueConstraint('target_type', 'target_id', 'ticker', name='uq_mentions_target_ticker'),
    )
