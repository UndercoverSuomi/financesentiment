from __future__ import annotations

import asyncio

import pytest

from app.core.config import get_settings
from app.services.reddit_client import RedditClient


def _settings(**overrides):
    return get_settings().model_copy(update=overrides)


def test_official_api_uses_single_oauth_host() -> None:
    client = RedditClient(
        _settings(
            reddit_use_official_api=True,
            reddit_base_url='https://oauth.reddit.com',
            reddit_client_id='demo-client',
        )
    )
    assert client._base_hosts == ['https://oauth.reddit.com']


def test_legacy_mode_keeps_fallback_hosts() -> None:
    client = RedditClient(
        _settings(
            reddit_use_official_api=False,
            reddit_base_url='https://www.reddit.com',
        )
    )
    assert client._base_hosts[0] == 'https://www.reddit.com'
    assert 'https://api.reddit.com' in client._base_hosts
    assert 'https://old.reddit.com' in client._base_hosts


def test_official_api_requires_client_id() -> None:
    client = RedditClient(
        _settings(
            reddit_use_official_api=True,
            reddit_client_id='',
        )
    )
    with pytest.raises(RuntimeError, match='REDDIT_CLIENT_ID'):
        asyncio.run(client.__aenter__())

