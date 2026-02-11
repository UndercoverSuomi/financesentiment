from __future__ import annotations

from app.services.stance_model import StanceProbabilities


class FinbertStanceModel:
    model_version = 'finbert-prosusai-v1'

    def __init__(self) -> None:
        try:
            from transformers import pipeline
        except Exception as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError('transformers is required for USE_FINBERT=true') from exc

        self._pipeline = pipeline(
            'text-classification',
            model='ProsusAI/finbert',
            tokenizer='ProsusAI/finbert',
            return_all_scores=True,
            device=-1,
            truncation=True,
        )

    def predict(self, context_text: str) -> StanceProbabilities:
        outputs = self._pipeline(context_text[:2048])[0]
        mapped = {'bullish': 0.0, 'bearish': 0.0, 'neutral': 0.0}
        for entry in outputs:
            label = str(entry.get('label', '')).lower()
            score = float(entry.get('score', 0.0))
            if 'pos' in label:
                mapped['bullish'] = score
            elif 'neg' in label:
                mapped['bearish'] = score
            elif 'neu' in label:
                mapped['neutral'] = score

        total = mapped['bullish'] + mapped['bearish'] + mapped['neutral']
        if total <= 0:
            return {'bullish': 0.33, 'bearish': 0.33, 'neutral': 0.34}
        return {k: v / total for k, v in mapped.items()}  # type: ignore[return-value]
