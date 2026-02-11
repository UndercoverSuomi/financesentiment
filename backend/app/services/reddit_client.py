from __future__ import annotations

import asyncio
import random
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings


class RedditClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None
        self._sem = asyncio.Semaphore(settings.reddit_max_concurrency)
        self._cache: dict[str, Any] = {}

    async def __aenter__(self) -> 'RedditClient':
        self._client = httpx.AsyncClient(
            base_url=self._settings.reddit_base_url,
            timeout=httpx.Timeout(connect=self._settings.reddit_timeout_connect, read=self._settings.reddit_timeout_read, write=10.0, pool=10.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=0, max_connections=self._settings.reddit_max_concurrency),
            headers={
                'User-Agent': self._settings.reddit_user_agent,
                'Accept': 'application/json',
                'Connection': 'close',
            },
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()

    def reset_run_cache(self) -> None:
        self._cache = {}

    async def get_top_listing(self, subreddit: str, sort: str, t_param: str, limit: int) -> dict[str, Any]:
        return await self._get_json(
            path=f'/r/{subreddit}/{sort}.json',
            params={'t': t_param, 'limit': limit, 'raw_json': 1},
        )

    async def get_thread(self, post_id: str, limit: int = 500, depth: int = 10) -> Any:
        return await self._get_json(
            path=f'/comments/{post_id}.json',
            params={'limit': limit, 'depth': depth, 'raw_json': 1},
        )

    async def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        if self._client is None:
            raise RuntimeError('RedditClient is not initialized')

        query = urlencode(sorted((str(k), str(v)) for k, v in params.items()))
        cache_key = f'{path}?{query}'
        if cache_key in self._cache:
            return self._cache[cache_key]

        last_error: Exception | None = None
        for attempt in range(self._settings.reddit_max_retries + 1):
            try:
                async with self._sem:
                    response = await self._client.get(path, params=params)

                if 200 <= response.status_code < 300:
                    payload = response.json()
                    self._cache[cache_key] = payload
                    return payload

                if response.status_code in {403, 429, 500, 502, 503, 504}:
                    last_error = RuntimeError(f'HTTP {response.status_code} for {path}')
                    delay = self._retry_delay(response.headers.get('Retry-After'), attempt)
                    await asyncio.sleep(delay)
                    continue

                response.raise_for_status()
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt >= self._settings.reddit_max_retries:
                    break
                await asyncio.sleep(self._retry_delay(None, attempt))

        detail = str(last_error) if last_error is not None else 'unknown error'
        raise RuntimeError(f'Failed to fetch Reddit endpoint {path}: {detail}')

    def _retry_delay(self, retry_after: str | None, attempt: int) -> float:
        if retry_after:
            try:
                return max(float(retry_after), 0.1)
            except ValueError:
                pass
        base = self._settings.reddit_backoff_base * (2 ** attempt)
        jitter = random.uniform(0, 0.25)
        return min(base + jitter, 30.0)
