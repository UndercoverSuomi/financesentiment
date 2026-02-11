from __future__ import annotations

from typing import Protocol, TypedDict


class StanceProbabilities(TypedDict):
    bullish: float
    bearish: float
    neutral: float


class StanceModel(Protocol):
    model_version: str

    def predict(self, context_text: str) -> StanceProbabilities:
        ...
