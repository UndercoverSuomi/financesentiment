from __future__ import annotations

from sqlalchemy import Date, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DailyScore(Base):
    __tablename__ = 'daily_scores'

    date_bucket_berlin: Mapped[Date] = mapped_column(Date, primary_key=True)
    subreddit: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)

    score_unweighted: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_weighted: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_stddev_unweighted: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ci95_low_unweighted: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ci95_high_unweighted: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    valid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_sum_unweighted: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    weighted_numerator: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    weighted_denominator: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bullish_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bearish_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    neutral_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unclear_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unclear_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    __table_args__ = (
        Index('ix_daily_scores_date_subreddit_ticker', 'date_bucket_berlin', 'subreddit', 'ticker'),
    )
