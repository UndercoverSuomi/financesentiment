from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.schemas.common import StanceLabel, TargetType
from app.services.deterministic_model import DeterministicStanceModel
from app.services.finbert_model import FinbertStanceModel
from app.services.stance_model import StanceModel
from app.services.ticker_extractor import ExtractedTicker, TickerExtractor
from app.utils.text import normalize_text


@dataclass(slots=True)
class StanceResult:
    mention: ExtractedTicker
    label: StanceLabel
    score: float
    confidence: float
    model_version: str
    context_text: str


class StanceService:
    def __init__(self, settings: Settings, ticker_extractor: TickerExtractor) -> None:
        self._settings = settings
        self._ticker_extractor = ticker_extractor
        self._model = self._build_model(settings)

    @property
    def model(self) -> StanceModel:
        return self._model

    def build_context(self, title: str, selftext: str, parent_text: str, text: str) -> str:
        return f'TITLE: {normalize_text(title)}\nSELF: {normalize_text(selftext)}\nPARENT: {normalize_text(parent_text)}\nTEXT: {normalize_text(text)}'

    def analyze_target(
        self,
        target_type: TargetType,
        text: str,
        title: str,
        selftext: str,
        parent_text: str,
    ) -> list[StanceResult]:
        current_mentions = self._merge_mentions_by_ticker(self._ticker_extractor.extract(text))
        parent_tickers = self._ticker_extractor.extract_tickers_only(parent_text)

        mentions = list(current_mentions)
        if not mentions and target_type == TargetType.comment and self._settings.inherit_parent_tickers_for_comments:
            inherited = set(parent_tickers)
            if self._settings.inherit_title_tickers_for_comments:
                inherited |= self._ticker_extractor.extract_tickers_only(title)
            for ticker in sorted(inherited):
                mentions.append(
                    ExtractedTicker(
                        ticker=ticker,
                        confidence=0.4,
                        source='context',
                        span_start=-1,
                        span_end=-1,
                    )
                )
            mentions = self._merge_mentions_by_ticker(mentions)

        if not mentions:
            return []

        results: list[StanceResult] = []
        context = self.build_context(title=title, selftext=selftext, parent_text=parent_text, text=text)

        for mention in mentions:
            probs = self._model.predict(context_text=f'{context}\nTICKER: {mention.ticker}')
            bullish = float(probs['bullish'])
            bearish = float(probs['bearish'])
            neutral = float(probs['neutral'])

            max_label = max((('BULLISH', bullish), ('BEARISH', bearish), ('NEUTRAL', neutral)), key=lambda x: x[1])
            confidence = max_label[1]
            ticker_in_text = mention.source != 'context'
            short_text = len(normalize_text(text)) < self._settings.unclear_short_text_len

            if mention.source == 'context' and not self._settings.allow_context_label_inference:
                label = StanceLabel.unclear
            elif confidence < self._settings.unclear_threshold or (short_text and not ticker_in_text):
                label = StanceLabel.unclear
            elif max_label[0] == 'BULLISH':
                label = StanceLabel.bullish
            elif max_label[0] == 'BEARISH':
                label = StanceLabel.bearish
            else:
                label = StanceLabel.neutral

            results.append(
                StanceResult(
                    mention=mention,
                    label=label,
                    score=max(min(bullish - bearish, 1.0), -1.0),
                    confidence=confidence,
                    model_version=self._model.model_version,
                    context_text=context,
                )
            )

        return results

    def _build_model(self, settings: Settings) -> StanceModel:
        if settings.use_finbert:
            try:
                return FinbertStanceModel()
            except Exception:
                return DeterministicStanceModel()
        return DeterministicStanceModel()

    def _merge_mentions_by_ticker(self, mentions: list[ExtractedTicker]) -> list[ExtractedTicker]:
        selected: dict[str, ExtractedTicker] = {}
        for mention in mentions:
            previous = selected.get(mention.ticker)
            if previous is None or self._is_better_mention(mention, previous):
                selected[mention.ticker] = mention
        return sorted(selected.values(), key=lambda m: m.ticker)

    def _is_better_mention(self, candidate: ExtractedTicker, current: ExtractedTicker) -> bool:
        source_rank = {
            'cashtag': 4,
            'token': 3,
            'synonym': 2,
            'context': 1,
        }
        candidate_key = (
            candidate.confidence,
            source_rank.get(candidate.source, 0),
            candidate.span_end - candidate.span_start,
        )
        current_key = (
            current.confidence,
            source_rank.get(current.source, 0),
            current.span_end - current.span_start,
        )
        return candidate_key > current_key
