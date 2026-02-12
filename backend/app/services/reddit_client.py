from __future__ import annotations

import asyncio
from collections import deque
import random
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings


@dataclass(slots=True)
class _ClientSlot:
    name: str
    client: httpx.AsyncClient
    proxy_url: str | None
    cooling_until_mono: float = 0.0
    failures: int = 0
    access_token: str | None = None
    token_expires_at_mono: float = 0.0


class RedditClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._using_official_api = bool(settings.reddit_use_official_api)
        self._client_slots: list[_ClientSlot] = []
        self._sem = asyncio.Semaphore(settings.reddit_max_concurrency)
        self._cache: dict[str, Any] = {}
        self._base_hosts = self._build_base_hosts(settings.reddit_base_url)
        self._request_lock = asyncio.Lock()
        self._last_request_mono = 0.0
        self._recent_request_mono: deque[float] = deque()
        mode = (settings.reddit_proxy_rotation_mode or 'round_robin').strip().lower()
        self._rotation_mode = mode if mode in {'round_robin', 'random'} else 'round_robin'
        self._next_slot_start = 0

    async def __aenter__(self) -> 'RedditClient':
        if self._using_official_api and not self._settings.reddit_client_id.strip():
            raise RuntimeError('REDDIT_CLIENT_ID is required when REDDIT_USE_OFFICIAL_API=true')
        self._client_slots = []
        self._recent_request_mono.clear()
        self._last_request_mono = 0.0
        if self._settings.reddit_proxy_include_direct_fallback or not self._settings.reddit_proxy_urls:
            self._client_slots.append(
                _ClientSlot(
                    name='direct',
                    client=self._build_client(proxy_url=None),
                    proxy_url=None,
                )
            )
        for idx, proxy_url in enumerate(self._settings.reddit_proxy_urls, start=1):
            self._client_slots.append(
                _ClientSlot(
                    name=f'proxy-{idx}',
                    client=self._build_client(proxy_url=proxy_url),
                    proxy_url=proxy_url,
                )
            )
        if not self._client_slots:
            self._client_slots.append(
                _ClientSlot(
                    name='direct',
                    client=self._build_client(proxy_url=None),
                    proxy_url=None,
                )
            )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        for slot in self._client_slots:
            await slot.client.aclose()
        self._client_slots = []

    def reset_run_cache(self) -> None:
        self._cache = {}

    async def get_top_listing(
        self,
        subreddit: str,
        sort: str,
        t_param: str,
        limit: int,
        *,
        after: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {'t': t_param, 'limit': limit, 'raw_json': 1}
        if after:
            params['after'] = after
        return await self._get_json(
            path=f'/r/{subreddit}/{sort}.json',
            params=params,
        )

    async def get_thread(self, post_id: str, limit: int | None = None, depth: int | None = None) -> Any:
        params: dict[str, Any] = {'raw_json': 1}
        if limit is not None:
            params['limit'] = limit
        if depth is not None:
            params['depth'] = depth
        return await self._get_json(
            path=f'/comments/{post_id}.json',
            params=params,
        )

    async def get_morechildren(self, post_id: str, children: list[str], sort: str = 'confidence') -> Any:
        if not children:
            return {}
        return await self._get_json(
            path='/api/morechildren.json',
            params={
                'link_id': f't3_{post_id}',
                'children': ','.join(children),
                'api_type': 'json',
                'sort': sort,
                'raw_json': 1,
            },
        )

    async def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        if not self._client_slots:
            raise RuntimeError('RedditClient is not initialized')

        query = urlencode(sorted((str(k), str(v)) for k, v in params.items()))
        cache_key = f'{path}?{query}'
        if cache_key in self._cache:
            return self._cache[cache_key]

        last_error: Exception | None = None
        for attempt in range(self._settings.reddit_max_retries + 1):
            try:
                async with self._sem:
                    response, slot_idx = await self._request_with_fallback(path=path, params=params)

                if 200 <= response.status_code < 300:
                    self._mark_slot_success(slot_idx)
                    payload = response.json()
                    self._cache[cache_key] = payload
                    return payload

                if response.status_code in {401, 403, 429, 500, 502, 503, 504}:
                    self._mark_slot_failure(slot_idx)
                    last_error = RuntimeError(f'HTTP {response.status_code} for {path}')
                    delay = self._retry_delay(response.headers.get('Retry-After'), attempt)
                    await asyncio.sleep(delay)
                    continue

                response.raise_for_status()
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, RuntimeError) as exc:
                last_error = exc
                if attempt >= self._settings.reddit_max_retries:
                    break
                await asyncio.sleep(self._retry_delay(None, attempt))

        detail = str(last_error) if last_error is not None else 'unknown error'
        raise RuntimeError(f'Failed to fetch Reddit endpoint {path}: {detail}')

    async def _request_with_fallback(self, path: str, params: dict[str, Any]) -> tuple[httpx.Response, int]:
        if not self._client_slots:
            raise RuntimeError('RedditClient is not initialized')

        last_response: httpx.Response | None = None
        last_response_slot_idx: int | None = None
        last_network_error: Exception | None = None
        slot_order = self._slot_order()

        for pass_idx in (0, 1):
            now = time.monotonic()
            for slot_idx in slot_order:
                slot = self._client_slots[slot_idx]
                if pass_idx == 0 and slot.cooling_until_mono > now:
                    continue
                try:
                    saw_403_only = True
                    auth_headers = await self._auth_headers_for_slot(slot)
                    for host in self._base_hosts:
                        await self._respect_min_interval()
                        response = await slot.client.get(f'{host}{path}', params=params, headers=auth_headers)
                        if response.status_code == 401 and self._using_official_api:
                            await self._ensure_slot_token(slot, force_refresh=True)
                            auth_headers = await self._auth_headers_for_slot(slot)
                            await self._respect_min_interval()
                            response = await slot.client.get(f'{host}{path}', params=params, headers=auth_headers)
                        last_response = response
                        last_response_slot_idx = slot_idx
                        if response.status_code != 403:
                            saw_403_only = False
                            return response, slot_idx
                    if saw_403_only:
                        self._mark_slot_failure(slot_idx)
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_network_error = exc
                    self._mark_slot_failure(slot_idx)

            if last_response is not None and last_response_slot_idx is not None:
                return last_response, last_response_slot_idx

        if last_network_error is not None:
            raise last_network_error
        if last_response is None:
            raise RuntimeError(f'No response received for {path}')
        if last_response_slot_idx is None:
            raise RuntimeError(f'No slot resolved for {path}')
        return last_response, last_response_slot_idx

    def _build_base_hosts(self, configured_base_url: str) -> list[str]:
        configured = configured_base_url.rstrip('/')
        if self._using_official_api:
            return [configured] if configured else ['https://oauth.reddit.com']
        candidates = [configured]
        for fallback in ('https://www.reddit.com', 'https://api.reddit.com', 'https://old.reddit.com'):
            if fallback not in candidates:
                candidates.append(fallback)
        return candidates

    def _build_client(self, proxy_url: str | None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_hosts[0],
            timeout=httpx.Timeout(
                connect=self._settings.reddit_timeout_connect,
                read=self._settings.reddit_timeout_read,
                write=10.0,
                pool=10.0,
            ),
            follow_redirects=True,
            limits=httpx.Limits(
                max_keepalive_connections=0,
                max_connections=self._settings.reddit_max_concurrency,
            ),
            headers={
                'User-Agent': self._settings.reddit_user_agent,
                'Accept': 'application/json',
                'Connection': 'close',
            },
            proxy=proxy_url,
        )

    def _slot_order(self) -> list[int]:
        n = len(self._client_slots)
        if n <= 1:
            return [0] if n == 1 else []
        indices = list(range(n))
        if self._rotation_mode == 'random':
            random.shuffle(indices)
            return indices
        start = self._next_slot_start % n
        self._next_slot_start = (start + 1) % n
        return [(start + i) % n for i in range(n)]

    def _mark_slot_success(self, slot_idx: int) -> None:
        if slot_idx < 0 or slot_idx >= len(self._client_slots):
            return
        slot = self._client_slots[slot_idx]
        slot.failures = 0
        slot.cooling_until_mono = 0.0

    def _mark_slot_failure(self, slot_idx: int) -> None:
        if slot_idx < 0 or slot_idx >= len(self._client_slots):
            return
        slot = self._client_slots[slot_idx]
        slot.failures = min(slot.failures + 1, 16)
        cooldown_base = max(float(self._settings.reddit_proxy_failure_cooldown_seconds), 0.0)
        if cooldown_base <= 0:
            return
        cooldown = cooldown_base * min(2 ** (slot.failures - 1), 8)
        slot.cooling_until_mono = max(slot.cooling_until_mono, time.monotonic() + cooldown)

    def _retry_delay(self, retry_after: str | None, attempt: int) -> float:
        if retry_after:
            try:
                return max(float(retry_after), 0.1)
            except ValueError:
                pass
        base = self._settings.reddit_backoff_base * (2 ** attempt)
        jitter = random.uniform(0, 0.25)
        return min(base + jitter, 30.0)

    async def _auth_headers_for_slot(self, slot: _ClientSlot) -> dict[str, str] | None:
        if not self._using_official_api:
            return None
        await self._ensure_slot_token(slot)
        if not slot.access_token:
            raise RuntimeError(f'No OAuth access token available for slot {slot.name}')
        return {'Authorization': f'Bearer {slot.access_token}'}

    async def _ensure_slot_token(self, slot: _ClientSlot, *, force_refresh: bool = False) -> None:
        if not self._using_official_api:
            return
        now = time.monotonic()
        if (
            not force_refresh
            and slot.access_token
            and slot.token_expires_at_mono > now + 60.0
        ):
            return

        await self._respect_min_interval()
        auth = httpx.BasicAuth(self._settings.reddit_client_id, self._settings.reddit_client_secret or '')
        token_payload: dict[str, str] = {'grant_type': 'client_credentials'}
        scope = (self._settings.reddit_oauth_scope or '').strip()
        if scope:
            token_payload['scope'] = scope

        response = await slot.client.post(
            self._settings.reddit_oauth_token_url,
            data=token_payload,
            auth=auth,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        response.raise_for_status()

        payload = response.json()
        access_token = payload.get('access_token')
        if not access_token:
            raise RuntimeError(f'OAuth token response missing access_token for slot {slot.name}')
        expires_in = int(payload.get('expires_in', 3600) or 3600)
        slot.access_token = str(access_token)
        slot.token_expires_at_mono = time.monotonic() + max(expires_in, 120)

    async def _respect_min_interval(self) -> None:
        min_interval = max(float(self._settings.reddit_min_request_interval_seconds), 0.0)
        max_rpm = max(int(self._settings.reddit_max_requests_per_minute), 0)
        if min_interval <= 0 and max_rpm <= 0:
            return
        async with self._request_lock:
            now = time.monotonic()
            if max_rpm > 0:
                cutoff = now - 60.0
                while self._recent_request_mono and self._recent_request_mono[0] <= cutoff:
                    self._recent_request_mono.popleft()

            wait_seconds = 0.0
            if min_interval > 0:
                elapsed = now - self._last_request_mono
                wait_seconds = max(wait_seconds, min_interval - elapsed)
            if max_rpm > 0 and len(self._recent_request_mono) >= max_rpm:
                wait_seconds = max(wait_seconds, (self._recent_request_mono[0] + 60.0) - now)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
                now = time.monotonic()
                if max_rpm > 0:
                    cutoff = now - 60.0
                    while self._recent_request_mono and self._recent_request_mono[0] <= cutoff:
                        self._recent_request_mono.popleft()
            self._last_request_mono = now
            if max_rpm > 0:
                self._recent_request_mono.append(now)
