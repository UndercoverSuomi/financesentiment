from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings

CASHTAG_RE = re.compile(r'\$([A-Za-z][A-Za-z\.]{0,4})\b')
# Avoid double-counting "$AAPL" as both cashtag and plain token.
TOKEN_RE = re.compile(r'(?<!\$)\b([A-Z]{1,5}(?:\.[A-Z])?)\b')
FINANCE_SIGNAL_RE = re.compile(
    r'(\$[A-Za-z][A-Za-z\.]{0,4}\b|\b(?:buy|sell|long|short|shares?|stock|stocks|earnings?|guidance|options?|calls?|puts?|price|valuation|profit|revenue|eps|pt|target)\b|[+\-]?\d+(?:\.\d+)?%)',
    re.IGNORECASE,
)

HARD_IGNORE_WITHOUT_CASHTAG = {
    'CEO',
    'CFO',
    'CTO',
    'YOLO',
    'IMO',
    'IMHO',
    'LOL',
    'LMAO',
    'ROFL',
    'FYI',
    'TLDR',
    'NFA',
    'FOMO',
    'GDP',
    'USA',
    'DD',
}

AMBIGUOUS_TICKERS_REQUIRE_CONTEXT = {
    'A',
    'I',
    'IT',
    'ON',
    'GO',
}

AMBIGUOUS_SYNONYMS_REQUIRE_CONTEXT = {
    'apple',
    'amazon',
    'meta',
}


@dataclass(slots=True)
class ExtractedTicker:
    ticker: str
    confidence: float
    source: str
    span_start: int
    span_end: int


class TickerExtractor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tickers = self._load_ticker_master(settings.ticker_master_file)
        self._synonyms = self._load_synonyms(settings.synonyms_file)
        self._synonym_patterns: list[tuple[re.Pattern[str], str, str]] = self._build_synonym_patterns(self._synonyms)
        self._stoplist = self._load_stoplist(settings.stoplist_file)
        self._hard_ignore_without_cashtag = set(HARD_IGNORE_WITHOUT_CASHTAG)
        self._ambiguous_tickers_require_context = set(AMBIGUOUS_TICKERS_REQUIRE_CONTEXT)
        self._ambiguous_synonyms_require_context = {phrase.lower() for phrase in AMBIGUOUS_SYNONYMS_REQUIRE_CONTEXT}
        self._finance_cues = {
            'stock',
            'shares',
            'earnings',
            'guidance',
            'short',
            'options',
            'call',
            'put',
            'price',
            'valuation',
            'profit',
            'revenue',
        }

    @property
    def ticker_universe(self) -> set[str]:
        return self._tickers

    def extract(self, text: str) -> list[ExtractedTicker]:
        if not text:
            return []

        candidates: list[ExtractedTicker] = []

        for match in CASHTAG_RE.finditer(text):
            ticker = match.group(1).upper()
            if self._is_valid_ticker(
                ticker,
                source='cashtag',
                text=text,
                span_start=match.start(),
                span_end=match.end(),
            ):
                conf = self._confidence(text, match.start(), match.end(), base=0.85)
                candidates.append(ExtractedTicker(ticker=ticker, confidence=conf, source='cashtag', span_start=match.start(), span_end=match.end()))

        for match in TOKEN_RE.finditer(text):
            ticker = match.group(1).upper()
            if self._is_valid_ticker(
                ticker,
                source='token',
                text=text,
                span_start=match.start(),
                span_end=match.end(),
            ):
                conf = self._confidence(text, match.start(), match.end(), base=0.65)
                candidates.append(ExtractedTicker(ticker=ticker, confidence=conf, source='token', span_start=match.start(), span_end=match.end()))

        for pattern, ticker, phrase in self._synonym_patterns:
            for match in pattern.finditer(text):
                if not self._is_valid_ticker(
                    ticker,
                    source='synonym',
                    text=text,
                    span_start=match.start(),
                    span_end=match.end(),
                    synonym_phrase=phrase,
                ):
                    continue
                conf = self._confidence(text, match.start(), match.end(), base=0.70)
                candidates.append(
                    ExtractedTicker(
                        ticker=ticker,
                        confidence=conf,
                        source='synonym',
                        span_start=match.start(),
                        span_end=match.end(),
                    )
                )

        deduped: dict[tuple[str, int, int], ExtractedTicker] = {}
        for c in candidates:
            key = (c.ticker, c.span_start, c.span_end)
            prev = deduped.get(key)
            if prev is None or c.confidence > prev.confidence:
                deduped[key] = c
        return list(deduped.values())

    def extract_tickers_only(self, text: str) -> set[str]:
        return {m.ticker for m in self.extract(text)}

    def _confidence(self, text: str, start: int, end: int, base: float) -> float:
        bonus = 0.1 if self._has_finance_context(text, start, end) else 0.0
        return min(base + bonus, 0.99)

    def _is_valid_ticker(
        self,
        ticker: str,
        *,
        source: str,
        text: str,
        span_start: int,
        span_end: int,
        synonym_phrase: str | None = None,
    ) -> bool:
        if ticker not in self._tickers:
            return False

        if source != 'cashtag':
            if ticker in self._stoplist or ticker in self._hard_ignore_without_cashtag:
                return False

        if source == 'token' and ticker in self._ambiguous_tickers_require_context:
            if not self._has_finance_context(text, span_start, span_end):
                return False

        if source == 'synonym' and synonym_phrase is not None:
            if synonym_phrase.lower() in self._ambiguous_synonyms_require_context:
                if not self._has_finance_context(text, span_start, span_end):
                    return False

        return True

    def _has_finance_context(self, text: str, start: int, end: int) -> bool:
        window_start = max(start - 24, 0)
        window_end = min(end + 24, len(text))
        window = text[window_start:window_end]
        lower = window.lower()
        if any(cue in lower for cue in self._finance_cues):
            return True
        return FINANCE_SIGNAL_RE.search(window) is not None

    def _load_ticker_master(self, path: Path) -> set[str]:
        tickers: set[str] = set()
        if not path.exists():
            return tickers
        with path.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = (row.get('ticker') or '').strip().upper()
                if ticker:
                    tickers.add(ticker)
        return tickers

    def _load_synonyms(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding='utf-8'))
        return {str(k).lower(): str(v).upper() for k, v in data.items()}

    def _load_stoplist(self, path: Path) -> set[str]:
        if not path.exists():
            return set()
        data = json.loads(path.read_text(encoding='utf-8'))
        return {str(item).upper() for item in data}

    def _build_synonym_patterns(self, synonyms: dict[str, str]) -> list[tuple[re.Pattern[str], str, str]]:
        patterns: list[tuple[re.Pattern[str], str, str]] = []
        for phrase, ticker in sorted(synonyms.items(), key=lambda item: len(item[0]), reverse=True):
            escaped = re.escape(phrase)
            pattern = re.compile(rf'(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])', re.IGNORECASE)
            patterns.append((pattern, ticker, phrase))
        return patterns
