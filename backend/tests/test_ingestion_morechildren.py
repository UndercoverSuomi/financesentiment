from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.services.ingestion_service import IngestionService
from app.services.reddit_parser import PendingMore


class _FakeRedditClient:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def get_morechildren(self, post_id: str, children: list[str], sort: str = 'confidence') -> dict:
        self.calls.append(list(children))
        things = [
            {
                'kind': 't1',
                'data': {
                    'id': child_id,
                    'parent_id': f't3_{post_id}',
                    'author': 'tester',
                    'created_utc': 1735689600,
                    'score': 1,
                    'body': f'comment {child_id}',
                    'permalink': f'/r/test/comments/{post_id}/_/{child_id}/',
                },
            }
            for child_id in children
        ]
        return {'json': {'data': {'things': things}}}


def _build_service(**overrides) -> IngestionService:
    settings = get_settings().model_copy(update=overrides)
    return IngestionService(settings=settings)


def test_expand_morechildren_respects_positive_batch_cap() -> None:
    service = _build_service(reddit_morechildren_chunk_size=1, reddit_morechildren_max_batches=2)
    client = _FakeRedditClient()

    comments = asyncio.run(
        service._expand_morechildren(
            reddit_client=client,
            submission_id='post1',
            initial_comments=[],
            initial_pending_more=[PendingMore(parent_id='post1', depth=0, children=['c1', 'c2', 'c3'])],
        )
    )

    assert len(client.calls) == 2
    assert len(comments) == 2
    assert {row.id for row in comments} == {'c1', 'c2'}


def test_expand_morechildren_zero_batch_cap_means_unlimited() -> None:
    service = _build_service(reddit_morechildren_chunk_size=1, reddit_morechildren_max_batches=0)
    client = _FakeRedditClient()

    comments = asyncio.run(
        service._expand_morechildren(
            reddit_client=client,
            submission_id='post1',
            initial_comments=[],
            initial_pending_more=[PendingMore(parent_id='post1', depth=0, children=['c1', 'c2', 'c3'])],
        )
    )

    assert len(client.calls) == 3
    assert len(comments) == 3
    assert {row.id for row in comments} == {'c1', 'c2', 'c3'}

