from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from app.core.config import Settings
from app.schemas.common import StanceLabel, TargetType
from app.services.deterministic_model import DeterministicStanceModel
from app.services.finbert_model import FinbertStanceModel
from app.services.llm_stance_model import LLMStanceModel
from app.services.stance_model import StanceModel
from app.services.ticker_extractor import ExtractedTicker, TickerExtractor
from app.utils.text import normalize_text

LOGGER = logging.getLogger(__name__)
SARCASM_CUES = (
    '/s',
    '(sarcasm)',
    'yeah right',
    'sure jan',
    'as if',
)


@dataclass(slots=True)
class StanceResult:
    mention: ExtractedTicker
    label: StanceLabel
    score: float
    confidence: float
    model_version: str
    context_text: str


@dataclass(slots=True)
class StanceRuntimeMetrics:
    base_model_calls: int = 0
    llm_calls: int = 0
    llm_failures: int = 0
    llm_prompt_tokens: int = 0
    llm_output_tokens: int = 0
    llm_total_tokens: int = 0
    llm_calls_without_usage: int = 0
    llm_estimated_cost_usd: float = 0.0


class StanceService:
    def __init__(
        self,
        settings: Settings,
        ticker_extractor: TickerExtractor,
        *,
        base_model: StanceModel | None = None,
        llm_model: StanceModel | None = None,
    ) -> None:
        self._settings = settings
        self._ticker_extractor = ticker_extractor
        self._model = base_model or self._build_model(settings)
        self._llm_model = llm_model if llm_model is not None else self._build_llm_model(settings)
        self._runtime_metrics = StanceRuntimeMetrics()

    @property
    def model(self) -> StanceModel:
        return self._model

    def reset_runtime_metrics(self) -> None:
        self._runtime_metrics = StanceRuntimeMetrics()

    def get_runtime_metrics(self) -> StanceRuntimeMetrics:
        current = self._runtime_metrics
        return StanceRuntimeMetrics(
            base_model_calls=current.base_model_calls,
            llm_calls=current.llm_calls,
            llm_failures=current.llm_failures,
            llm_prompt_tokens=current.llm_prompt_tokens,
            llm_output_tokens=current.llm_output_tokens,
            llm_total_tokens=current.llm_total_tokens,
            llm_calls_without_usage=current.llm_calls_without_usage,
            llm_estimated_cost_usd=current.llm_estimated_cost_usd,
        )

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
            context_with_ticker = f'{context}\nTICKER: {mention.ticker}'
            self._runtime_metrics.base_model_calls += 1
            probs = self._model.predict(context_text=context_with_ticker)
            bullish = float(probs['bullish'])
            bearish = float(probs['bearish'])
            neutral = float(probs['neutral'])
            label, confidence = self._label_from_probs(
                mention=mention,
                text=text,
                bullish=bullish,
                bearish=bearish,
                neutral=neutral,
            )
            used_model_version = self._model.model_version

            if self._should_use_llm(text=text, mention=mention, label=label, confidence=confidence):
                self._runtime_metrics.llm_calls += 1
                try:
                    llm_model = self._llm_model
                    if llm_model is None:
                        raise RuntimeError('llm model unavailable')
                    llm_probs = llm_model.predict(context_text=context_with_ticker)
                    bullish = float(llm_probs['bullish'])
                    bearish = float(llm_probs['bearish'])
                    neutral = float(llm_probs['neutral'])
                    label, confidence = self._label_from_probs(
                        mention=mention,
                        text=text,
                        bullish=bullish,
                        bearish=bearish,
                        neutral=neutral,
                    )
                    used_model_version = llm_model.model_version
                    self._record_llm_usage(llm_model)
                except Exception as exc:
                    self._runtime_metrics.llm_failures += 1
                    LOGGER.warning('LLM stance fallback failed for ticker=%s: %s', mention.ticker, exc)

            results.append(
                StanceResult(
                    mention=mention,
                    label=label,
                    score=max(min(bullish - bearish, 1.0), -1.0),
                    confidence=confidence,
                    model_version=used_model_version,
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

    def _build_llm_model(self, settings: Settings) -> StanceModel | None:
        if not settings.use_llm_model:
            return None
        try:
            return LLMStanceModel(settings)
        except Exception as exc:
            LOGGER.warning('Failed to initialize LLM stance model, using base model only: %s', exc)
            return None

    def _label_from_probs(
        self,
        *,
        mention: ExtractedTicker,
        text: str,
        bullish: float,
        bearish: float,
        neutral: float,
    ) -> tuple[StanceLabel, float]:
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
        return label, confidence

    def _should_use_llm(
        self,
        *,
        text: str,
        mention: ExtractedTicker,
        label: StanceLabel,
        confidence: float,
    ) -> bool:
        if self._llm_model is None:
            return False
        if mention.source == 'context' and not self._settings.allow_context_label_inference:
            return False
        if self._settings.llm_enable_sarcasm_trigger and self._contains_sarcasm_cue(text):
            return True
        if self._settings.llm_unclear_only:
            return label == StanceLabel.unclear or confidence < self._settings.llm_low_confidence_threshold
        return True

    def _contains_sarcasm_cue(self, text: str) -> bool:
        normalized = normalize_text(text).lower()
        return any(cue in normalized for cue in SARCASM_CUES)

    def _record_llm_usage(self, llm_model: StanceModel) -> None:
        getter = getattr(llm_model, 'get_last_usage', None)
        if not callable(getter):
            self._runtime_metrics.llm_calls_without_usage += 1
            return

        usage_raw = getter()
        if not isinstance(usage_raw, dict):
            self._runtime_metrics.llm_calls_without_usage += 1
            return

        prompt_tokens = self._as_non_negative_int(usage_raw.get('prompt_tokens'))
        output_tokens = self._as_non_negative_int(usage_raw.get('output_tokens'))
        total_tokens = self._as_non_negative_int(usage_raw.get('total_tokens'))
        if total_tokens == 0 and (prompt_tokens > 0 or output_tokens > 0):
            total_tokens = prompt_tokens + output_tokens

        if prompt_tokens == 0 and output_tokens == 0 and total_tokens == 0:
            self._runtime_metrics.llm_calls_without_usage += 1
            return

        self._runtime_metrics.llm_prompt_tokens += prompt_tokens
        self._runtime_metrics.llm_output_tokens += output_tokens
        self._runtime_metrics.llm_total_tokens += total_tokens

        input_cost = (
            prompt_tokens * float(self._settings.llm_input_price_per_million_tokens)
        ) / 1_000_000.0
        output_cost = (
            output_tokens * float(self._settings.llm_output_price_per_million_tokens)
        ) / 1_000_000.0
        self._runtime_metrics.llm_estimated_cost_usd += (input_cost + output_cost)

    def _as_non_negative_int(self, value: Any) -> int:
        if value is None:
            return 0
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        return parsed if parsed > 0 else 0

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
