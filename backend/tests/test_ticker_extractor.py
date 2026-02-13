from __future__ import annotations

from pathlib import Path

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

    lower_cashtag_mentions = extractor.extract('$aapl keeps going')
    assert any(m.ticker == 'AAPL' and m.source == 'cashtag' for m in lower_cashtag_mentions)


def test_ambiguous_synonym_requires_finance_context() -> None:
    extractor = TickerExtractor(get_settings())

    no_context = extractor.extract('the meta discussion about testing was long')
    with_context = extractor.extract('meta stock is undervalued, buying more')

    assert all(m.ticker != 'META' for m in no_context)
    assert any(m.ticker == 'META' and m.source == 'synonym' for m in with_context)


def test_cashtag_can_override_stoplist_when_ticker_exists(tmp_path: Path) -> None:
    ticker_file = tmp_path / 'tickers_custom.csv'
    ticker_file.write_text('ticker,name\nAI,C3.ai\n', encoding='utf-8')

    settings = get_settings().model_copy(update={'ticker_master_path': str(ticker_file)})
    extractor = TickerExtractor(settings)

    plain_mentions = extractor.extract('AI is everywhere this year')
    cashtag_mentions = extractor.extract('$AI is everywhere this year')

    assert all(m.ticker != 'AI' for m in plain_mentions)
    assert any(m.ticker == 'AI' and m.source == 'cashtag' for m in cashtag_mentions)
