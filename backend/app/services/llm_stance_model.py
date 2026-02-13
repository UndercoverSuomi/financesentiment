from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.services.stance_model import StanceProbabilities

LOGGER = logging.getLogger(__name__)
TICKER_RE = re.compile(r'\bTICKER:\s*([A-Z][A-Z\.]{0,5})\b')


class LLMStanceModel:
    model_version: str

    def __init__(self, settings: Settings) -> None:
        api_key = settings.gemini_api_key.strip()
        if not api_key:
            raise RuntimeError('GEMINI_API_KEY is required when USE_LLM_MODEL=true')

        self._api_key = api_key
        self._model = settings.gemini_model.strip() or 'gemini-3-flash-preview'
        self._base_url = settings.gemini_api_base_url.rstrip('/')
        self._max_retries = max(int(settings.llm_max_retries), 0)
        self._temperature = max(float(settings.llm_temperature), 0.0)
        self._max_output_tokens = max(int(settings.llm_max_output_tokens), 32)
        self._timeout_seconds = max(float(settings.llm_timeout_seconds), 1.0)
        self.model_version = f'gemini-{self._model}'
        self._last_usage: dict[str, int | None] = {
            'prompt_tokens': None,
            'output_tokens': None,
            'total_tokens': None,
        }

        self._client = httpx.Client(
            timeout=httpx.Timeout(
                connect=min(self._timeout_seconds, 10.0),
                read=self._timeout_seconds,
                write=min(self._timeout_seconds, 10.0),
                pool=min(self._timeout_seconds, 10.0),
            ),
            headers={
                'Content-Type': 'application/json',
                'x-goog-api-key': self._api_key,
            },
        )

    def predict(self, context_text: str) -> StanceProbabilities:
        ticker = self._extract_ticker(context_text)
        system_prompt = (
            'Du bist ein Finanz-Experte fuer Social Media Sentiment. '
            f'Analysiere den folgenden Kommentar im Kontext des Titels (/vorherigen Kommentars). '
            f'Ist die Haltung gegenueber dem Ticker {ticker} BULLISH, BEARISH oder NEUTRAL? '
            'Achte besonders auf Sarkasmus (z.B. WallStreetBets-Slang). '
            'Antworte nur mit JSON.'
        )
        user_prompt = (
            'Nutze nur diese JSON-Struktur:\n'
            '{"label":"BULLISH|BEARISH|NEUTRAL|UNCLEAR","confidence":0.0-1.0}\n\n'
            'Kontext:\n'
            f'{context_text[:4000]}'
        )

        payload = {
            'systemInstruction': {
                'parts': [{'text': system_prompt}],
            },
            'contents': [
                {
                    'role': 'user',
                    'parts': [{'text': user_prompt}],
                }
            ],
            'generationConfig': {
                'temperature': self._temperature,
                'maxOutputTokens': self._max_output_tokens,
                'responseMimeType': 'application/json',
                'responseJsonSchema': {
                    'type': 'object',
                    'properties': {
                        'label': {
                            'type': 'string',
                            'enum': ['BULLISH', 'BEARISH', 'NEUTRAL', 'UNCLEAR'],
                        },
                        'confidence': {'type': 'number'},
                    },
                    'required': ['label'],
                },
            },
        }

        endpoint = f'{self._base_url}/models/{self._model}:generateContent'
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(endpoint, json=payload)
                response.raise_for_status()
                response_payload = response.json()
                self._last_usage = self._extract_usage(response_payload)
                return self._parse_response_to_probs(response_payload)
            except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                delay = min(1.5 * (2 ** attempt), 6.0)
                time.sleep(delay)

        detail = str(last_error) if last_error is not None else 'unknown llm error'
        raise RuntimeError(f'Gemini stance request failed: {detail}')

    def get_last_usage(self) -> dict[str, int | None]:
        return dict(self._last_usage)

    def _extract_ticker(self, context_text: str) -> str:
        match = TICKER_RE.search(context_text)
        if match:
            return match.group(1)
        return 'UNKNOWN'

    def _parse_response_to_probs(self, payload: dict[str, Any]) -> StanceProbabilities:
        text = self._extract_text(payload)
        if not text:
            raise ValueError('Gemini response did not include text output')

        parsed = self._parse_json_text(text)
        label = str(parsed.get('label', '')).upper().strip()
        confidence = _coerce_confidence(parsed.get('confidence'))
        if label not in {'BULLISH', 'BEARISH', 'NEUTRAL', 'UNCLEAR'}:
            raise ValueError(f'invalid label from Gemini: {label}')
        return _label_to_probabilities(label=label, confidence=confidence)

    def _extract_text(self, payload: dict[str, Any]) -> str:
        candidates = payload.get('candidates', [])
        if isinstance(candidates, list):
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                content = candidate.get('content', {})
                if not isinstance(content, dict):
                    continue
                parts = content.get('parts', [])
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    text = part.get('text')
                    if isinstance(text, str) and text.strip():
                        return text.strip()
        return ''

    def _parse_json_text(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith('```'):
            stripped = stripped.strip('`')
            if stripped.lower().startswith('json'):
                stripped = stripped[4:]
            stripped = stripped.strip()
        obj = json.loads(stripped)
        if not isinstance(obj, dict):
            raise ValueError('Gemini output is not a JSON object')
        return obj

    def _extract_usage(self, payload: dict[str, Any]) -> dict[str, int | None]:
        usage = payload.get('usageMetadata', {})
        if not isinstance(usage, dict):
            return {
                'prompt_tokens': None,
                'output_tokens': None,
                'total_tokens': None,
            }

        prompt = _to_int(usage.get('promptTokenCount'))
        output = _to_int(usage.get('candidatesTokenCount'))
        total = _to_int(usage.get('totalTokenCount'))
        if total is None and prompt is not None and output is not None:
            total = prompt + output
        if output is None and total is not None and prompt is not None and total >= prompt:
            output = total - prompt

        return {
            'prompt_tokens': prompt,
            'output_tokens': output,
            'total_tokens': total,
        }


def _coerce_confidence(value: Any) -> float:
    if value is None:
        return 0.75
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return 0.75
    if conf < 0.0:
        return 0.0
    if conf > 1.0:
        return 1.0
    return conf


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out >= 0 else None


def _label_to_probabilities(*, label: str, confidence: float) -> StanceProbabilities:
    if label == 'UNCLEAR':
        return {'bullish': 0.33, 'bearish': 0.33, 'neutral': 0.34}

    dominant = min(max(confidence, 0.51), 0.99)
    rest = (1.0 - dominant) / 2.0
    if label == 'BULLISH':
        return {'bullish': dominant, 'bearish': rest, 'neutral': rest}
    if label == 'BEARISH':
        return {'bullish': rest, 'bearish': dominant, 'neutral': rest}
    return {'bullish': rest, 'bearish': rest, 'neutral': dominant}
