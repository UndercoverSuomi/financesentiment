from __future__ import annotations

from app.core.config import get_settings
from app.schemas.common import StanceLabel, TargetType
from app.services.stance_service import StanceService
from app.services.ticker_extractor import TickerExtractor


def _build_service(**overrides) -> StanceService:
    settings = get_settings().model_copy(update=overrides)
    extractor = TickerExtractor(settings)
    return StanceService(settings=settings, ticker_extractor=extractor)


def test_context_inherited_ticker_is_unclear_by_default() -> None:
    service = _build_service(
        inherit_parent_tickers_for_comments=True,
        inherit_title_tickers_for_comments=False,
        allow_context_label_inference=False,
    )

    results = service.analyze_target(
        target_type=TargetType.comment,
        text='I agree with this.',
        title='AAPL daily thread',
        selftext='',
        parent_text='AAPL still looks strong here.',
    )

    assert len(results) == 1
    assert results[0].mention.ticker == 'AAPL'
    assert results[0].mention.source == 'context'
    assert results[0].label == StanceLabel.unclear


def test_comment_does_not_inherit_from_title_when_disabled() -> None:
    service = _build_service(
        inherit_parent_tickers_for_comments=True,
        inherit_title_tickers_for_comments=False,
        allow_context_label_inference=False,
    )

    results = service.analyze_target(
        target_type=TargetType.comment,
        text='same view',
        title='AAPL daily thread',
        selftext='',
        parent_text='general market chatter only',
    )

    assert results == []


def test_mentions_are_deduped_per_ticker_per_target() -> None:
    service = _build_service()

    results = service.analyze_target(
        target_type=TargetType.comment,
        text='$AAPL and AAPL and apple',
        title='',
        selftext='',
        parent_text='',
    )

    assert len(results) == 1
    assert results[0].mention.ticker == 'AAPL'
    assert results[0].mention.source == 'cashtag'
