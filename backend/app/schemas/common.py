from __future__ import annotations

from enum import Enum


class TargetType(str, Enum):
    submission = 'submission'
    comment = 'comment'


class StanceLabel(str, Enum):
    bullish = 'BULLISH'
    bearish = 'BEARISH'
    neutral = 'NEUTRAL'
    unclear = 'UNCLEAR'
