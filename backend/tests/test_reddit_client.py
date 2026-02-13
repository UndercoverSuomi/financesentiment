from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from app.core.config import get_settings
from app.services.reddit_client import RedditClient


def _settings(**overrides):
    return get_settings().model_copy(update=overrides)


class _FakeAsyncIterator:
    def __init__(self, rows):
        self._rows = list(rows)
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._idx]
        self._idx += 1
        return row


@dataclass
class _FakeSubredditRef:
    submissions: list[object]

    def top(self, *, time_filter: str, limit: int, params=None):
        after = (params or {}).get('after')
        if after:
            start = next((idx + 1 for idx, item in enumerate(self.submissions) if item.fullname == after), len(self.submissions))
        else:
            start = 0
        return _FakeAsyncIterator(self.submissions[start:start + limit])

    def controversial(self, *, time_filter: str, limit: int, params=None):
        return self.top(time_filter=time_filter, limit=limit, params=params)

    def new(self, *, limit: int, params=None):
        return self.top(time_filter='day', limit=limit, params=params)

    def hot(self, *, limit: int, params=None):
        return self.top(time_filter='day', limit=limit, params=params)

    def rising(self, *, limit: int, params=None):
        return self.top(time_filter='day', limit=limit, params=params)


@dataclass
class _FakeSubmission:
    id: str
    fullname: str
    subreddit: str = 'stocks'
    created_utc: float = 1_700_000_000
    title: str = 'AAPL'
    selftext: str = 'text'
    url: str = 'https://example.com'
    score: int = 10
    num_comments: int = 3
    permalink: str = '/r/stocks/comments/x'
    preview: dict = None

    def __post_init__(self):
        if self.preview is None:
            self.preview = {}


class _FakeReddit:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        self._submissions = [
            _FakeSubmission(id='p1', fullname='t3_p1'),
            _FakeSubmission(id='p2', fullname='t3_p2'),
        ]

    async def subreddit(self, name: str):
        return _FakeSubredditRef(self._submissions)

    async def close(self):
        self.closed = True


def test_official_api_requires_client_id() -> None:
    client = RedditClient(
        _settings(
            reddit_client_id='',
            reddit_client_secret='demo-secret',
            reddit_user_agent='demo-agent',
        )
    )
    with pytest.raises(RuntimeError, match='REDDIT_CLIENT_ID'):
        asyncio.run(client.__aenter__())


def test_client_initializes_asyncpraw_and_closes(monkeypatch) -> None:
    captured = {}

    def _factory(**kwargs):
        reddit = _FakeReddit(**kwargs)
        captured['reddit'] = reddit
        return reddit

    monkeypatch.setattr('app.services.reddit_client.asyncpraw.Reddit', _factory)
    client = RedditClient(
        _settings(
            reddit_client_id='demo-client',
            reddit_client_secret='demo-secret',
            reddit_user_agent='demo-agent',
        )
    )

    entered = asyncio.run(client.__aenter__())
    assert entered is client
    assert captured['reddit'].kwargs['client_id'] == 'demo-client'
    assert captured['reddit'].kwargs['client_secret'] == 'demo-secret'
    assert captured['reddit'].kwargs['user_agent'] == 'demo-agent'

    asyncio.run(client.__aexit__(None, None, None))
    assert captured['reddit'].closed is True


def test_get_top_listing_maps_asyncpraw_to_listing_payload(monkeypatch) -> None:
    monkeypatch.setattr('app.services.reddit_client.asyncpraw.Reddit', lambda **kwargs: _FakeReddit(**kwargs))
    client = RedditClient(
        _settings(
            reddit_client_id='demo-client',
            reddit_client_secret='demo-secret',
            reddit_user_agent='demo-agent',
        )
    )

    asyncio.run(client.__aenter__())
    page1 = asyncio.run(client.get_top_listing('stocks', 'top', 'day', 1))
    page2 = asyncio.run(client.get_top_listing('stocks', 'top', 'day', 1, after=page1['data']['after']))
    asyncio.run(client.__aexit__(None, None, None))

    assert page1['kind'] == 'Listing'
    assert page1['data']['children'][0]['kind'] == 't3'
    assert page1['data']['children'][0]['data']['id'] == 'p1'
    assert page1['data']['after'] == 't3_p1'

    assert page2['data']['children'][0]['data']['id'] == 'p2'
