from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.schemas.common import StanceLabel, TargetType
from app.services.stance_model import StanceProbabilities
from app.services.stance_service import StanceService
from app.services.ticker_extractor import TickerExtractor


@dataclass
class _FakeModel:
    model_version: str
    probs: StanceProbabilities
    calls: int = 0
    usage: dict | None = None

    def predict(self, context_text: str) -> StanceProbabilities:
        self.calls += 1
        return dict(self.probs)  # type: ignore[return-value]

    def get_last_usage(self):  # type: ignore[no-untyped-def]
        return self.usage


def _build_service(
    *,
    base_model=None,
    llm_model=None,
    **overrides,
) -> StanceService:
    settings = get_settings().model_copy(update=overrides)
    extractor = TickerExtractor(settings)
    return StanceService(
        settings=settings,
        ticker_extractor=extractor,
        base_model=base_model,
        llm_model=llm_model,
    )


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


def test_llm_fallback_used_for_unclear_predictions() -> None:
    base = _FakeModel(
        model_version='base-v1',
        probs={'bullish': 0.34, 'bearish': 0.33, 'neutral': 0.33},
    )
    llm = _FakeModel(
        model_version='llm-v1',
        probs={'bullish': 0.92, 'bearish': 0.04, 'neutral': 0.04},
        usage={'prompt_tokens': 300, 'output_tokens': 20, 'total_tokens': 320},
    )
    service = _build_service(
        use_llm_model=True,
        llm_unclear_only=True,
        llm_enable_sarcasm_trigger=False,
        base_model=base,
        llm_model=llm,
    )

    results = service.analyze_target(
        target_type=TargetType.comment,
        text='AAPL maybe maybe',
        title='',
        selftext='',
        parent_text='',
    )

    assert len(results) == 1
    assert results[0].label == StanceLabel.bullish
    assert results[0].model_version == 'llm-v1'
    assert llm.calls == 1
    metrics = service.get_runtime_metrics()
    assert metrics.base_model_calls == 1
    assert metrics.llm_calls == 1
    assert metrics.llm_failures == 0
    assert metrics.llm_prompt_tokens == 300
    assert metrics.llm_output_tokens == 20
    assert metrics.llm_total_tokens == 320
    assert abs(metrics.llm_estimated_cost_usd - 0.000057) < 1e-12


def test_llm_not_used_for_confident_non_sarcastic_case() -> None:
    base = _FakeModel(
        model_version='base-v1',
        probs={'bullish': 0.9, 'bearish': 0.05, 'neutral': 0.05},
    )
    llm = _FakeModel(
        model_version='llm-v1',
        probs={'bullish': 0.1, 'bearish': 0.8, 'neutral': 0.1},
    )
    service = _build_service(
        use_llm_model=True,
        llm_unclear_only=True,
        llm_enable_sarcasm_trigger=True,
        base_model=base,
        llm_model=llm,
    )

    results = service.analyze_target(
        target_type=TargetType.comment,
        text='AAPL is a strong buy',
        title='',
        selftext='',
        parent_text='',
    )

    assert len(results) == 1
    assert results[0].label == StanceLabel.bullish
    assert results[0].model_version == 'base-v1'
    assert llm.calls == 0


def test_llm_used_when_sarcasm_cue_present() -> None:
    base = _FakeModel(
        model_version='base-v1',
        probs={'bullish': 0.91, 'bearish': 0.05, 'neutral': 0.04},
    )
    llm = _FakeModel(
        model_version='llm-v1',
        probs={'bullish': 0.1, 'bearish': 0.8, 'neutral': 0.1},
    )
    service = _build_service(
        use_llm_model=True,
        llm_unclear_only=True,
        llm_enable_sarcasm_trigger=True,
        base_model=base,
        llm_model=llm,
    )

    results = service.analyze_target(
        target_type=TargetType.comment,
        text='Yeah right, AAPL to the moon /s',
        title='',
        selftext='',
        parent_text='',
    )

    assert len(results) == 1
    assert results[0].label == StanceLabel.bearish
    assert results[0].model_version == 'llm-v1'
    assert llm.calls == 1


def test_runtime_metrics_reset_clears_counters() -> None:
    base = _FakeModel(
        model_version='base-v1',
        probs={'bullish': 0.34, 'bearish': 0.33, 'neutral': 0.33},
    )
    llm = _FakeModel(
        model_version='llm-v1',
        probs={'bullish': 0.7, 'bearish': 0.2, 'neutral': 0.1},
        usage={'prompt_tokens': 100, 'output_tokens': 10, 'total_tokens': 110},
    )
    service = _build_service(
        use_llm_model=True,
        llm_unclear_only=True,
        llm_enable_sarcasm_trigger=False,
        base_model=base,
        llm_model=llm,
    )

    service.analyze_target(
        target_type=TargetType.comment,
        text='AAPL maybe maybe',
        title='',
        selftext='',
        parent_text='',
    )
    before = service.get_runtime_metrics()
    assert before.llm_calls == 1

    service.reset_runtime_metrics()
    after = service.get_runtime_metrics()
    assert after.base_model_calls == 0
    assert after.llm_calls == 0
    assert after.llm_prompt_tokens == 0
    assert after.llm_estimated_cost_usd == 0.0
