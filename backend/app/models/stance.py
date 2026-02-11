from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Stance(Base):
    __tablename__ = 'stance'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    stance_label: Mapped[str] = mapped_column(String(16), nullable=False)
    stance_score: Mapped[float] = mapped_column(nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    context_text: Mapped[str] = mapped_column(Text, nullable=False, default='')

    __table_args__ = (
        Index('ix_stance_target_type_target_id', 'target_type', 'target_id'),
        UniqueConstraint('target_type', 'target_id', 'ticker', name='uq_stance_target_ticker'),
    )
