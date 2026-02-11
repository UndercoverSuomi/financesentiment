from __future__ import annotations

import re

from app.services.stance_model import StanceProbabilities


class DeterministicStanceModel:
    model_version = 'deterministic-v1'

    _bullish_words = {
        'bull', 'bullish', 'buy', 'long', 'moon', 'pump', 'beat', 'upside', 'rally', 'undervalued', 'strong', 'calls'
    }
    _bearish_words = {
        'bear', 'bearish', 'sell', 'short', 'dump', 'miss', 'downside', 'crash', 'overvalued', 'weak', 'puts'
    }
    _neutral_words = {'neutral', 'hold', 'wait', 'sideways', 'flat', 'mixed'}

    def predict(self, context_text: str) -> StanceProbabilities:
        text = context_text.lower()
        tokens = re.findall(r"[a-z']+", text)

        bullish = sum(1 for t in tokens if t in self._bullish_words)
        bearish = sum(1 for t in tokens if t in self._bearish_words)
        neutral = sum(1 for t in tokens if t in self._neutral_words)

        if bullish == 0 and bearish == 0 and neutral == 0:
            return {'bullish': 0.22, 'bearish': 0.22, 'neutral': 0.56}

        total = float(bullish + bearish + neutral + 1)
        return {
            'bullish': (bullish + 0.2) / total,
            'bearish': (bearish + 0.2) / total,
            'neutral': (neutral + 0.6) / total,
        }
