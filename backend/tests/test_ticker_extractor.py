from __future__ import annotations

from app.core.config import get_settings
from app.services.ticker_extractor import TickerExtractor


def test_ticker_extractor_filters_stoplist_and_supports_synonyms() -> None:
    extractor = TickerExtractor(get_settings())

    text = 'Apple looks strong. $AAPL calls are up. CEO talked. YOLO TSLA stock.'
    mentions = extractor.extract(text)
    tickers = {m.ticker for m in mentions}

    assert 'AAPL' in tickers
    assert 'TSLA' in tickers
    assert 'CEO' not in tickers
    assert 'YOLO' not in tickers

    assert any(m.source == 'synonym' and m.ticker == 'AAPL' for m in mentions)
    assert any(m.source == 'cashtag' and m.ticker == 'AAPL' for m in mentions)


def test_ticker_extractor_avoids_cashtag_double_count_and_substring_synonyms() -> None:
    extractor = TickerExtractor(get_settings())

    cashtag_mentions = extractor.extract('$AAPL to the moon')
    aapl_mentions = [m for m in cashtag_mentions if m.ticker == 'AAPL']
    assert len(aapl_mentions) == 1
    assert aapl_mentions[0].source == 'cashtag'

    false_positive_mentions = extractor.extract('metaphor pineapple')
    assert all(m.ticker not in {'META', 'AAPL'} for m in false_positive_mentions)
