from __future__ import annotations

import re

WHITESPACE_RE = re.compile(r'\s+')


def normalize_text(text: str | None) -> str:
    if not text:
        return ''
    return WHITESPACE_RE.sub(' ', text).strip()


def clamp_text(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len]
