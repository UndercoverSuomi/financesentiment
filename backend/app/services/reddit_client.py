from __future__ import annotations

from typing import Any

import asyncpraw

from app.core.config import Settings


class RedditClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[str, Any] = {}
        self._reddit: Any | None = None

    async def __aenter__(self) -> 'RedditClient':
        client_id = self._settings.reddit_client_id.strip()
        client_secret = self._settings.reddit_client_secret.strip()
        user_agent = self._settings.reddit_user_agent.strip()
        if not client_id:
            raise RuntimeError('REDDIT_CLIENT_ID is required for Reddit API access')
        if not client_secret:
            raise RuntimeError('REDDIT_CLIENT_SECRET is required for Reddit API access')
        if not user_agent:
            raise RuntimeError('REDDIT_USER_AGENT is required for Reddit API access')

        timeout_seconds = max(float(self._settings.reddit_timeout_read), 1.0)
        self._reddit = asyncpraw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
            ratelimit_seconds=90,
            requestor_kwargs={'timeout': timeout_seconds},
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._reddit is not None:
            await self._reddit.close()
        self._reddit = None

    def reset_run_cache(self) -> None:
        self._cache = {}

    def get_rate_limit_snapshot(self) -> dict[str, float | None] | None:
        reddit = self._reddit
        if reddit is None:
            return None
        auth = getattr(reddit, 'auth', None)
        limits = getattr(auth, 'limits', None)
        if not isinstance(limits, dict):
            return None

        remaining = _to_float(limits.get('remaining'))
        used = _to_float(limits.get('used'))
        reset_timestamp = _to_float(limits.get('reset_timestamp'))
        remaining_percent: float | None = None
        if remaining is not None and used is not None and (remaining + used) > 0:
            remaining_percent = (remaining / (remaining + used)) * 100.0

        return {
            'remaining': remaining,
            'used': used,
            'reset_timestamp': reset_timestamp,
            'remaining_percent': remaining_percent,
        }

    async def get_top_listing(
        self,
        subreddit: str,
        sort: str,
        t_param: str,
        limit: int,
        *,
        after: str | None = None,
    ) -> dict[str, Any]:
        reddit = self._require_reddit()
        cache_key = f'listing:{subreddit}:{sort}:{t_param}:{limit}:{after or ""}'
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        subreddit_ref = await reddit.subreddit(subreddit)
        listing_params: dict[str, str] = {}
        if after:
            listing_params['after'] = after
        params = listing_params or None

        normalized_sort = (sort or 'top').strip().lower()
        listing_gen: Any
        if normalized_sort == 'top':
            listing_gen = subreddit_ref.top(time_filter=t_param, limit=limit, params=params)
        elif normalized_sort == 'controversial':
            listing_gen = subreddit_ref.controversial(time_filter=t_param, limit=limit, params=params)
        elif normalized_sort == 'new':
            listing_gen = subreddit_ref.new(limit=limit, params=params)
        elif normalized_sort == 'hot':
            listing_gen = subreddit_ref.hot(limit=limit, params=params)
        elif normalized_sort == 'rising':
            listing_gen = subreddit_ref.rising(limit=limit, params=params)
        else:
            raise RuntimeError(f'unsupported listing sort: {sort}')

        submissions: list[Any] = []
        async for item in listing_gen:
            submissions.append(item)

        payload = {
            'kind': 'Listing',
            'data': {
                'children': [{'kind': 't3', 'data': self._submission_to_dict(item)} for item in submissions],
                'after': (
                    str(getattr(submissions[-1], 'fullname', '') or '')
                    if submissions and len(submissions) >= max(int(limit), 1)
                    else None
                ),
            },
        }
        self._cache[cache_key] = payload
        return payload

    async def get_thread(self, post_id: str, limit: int | None = None, depth: int | None = None) -> Any:
        reddit = self._require_reddit()
        cache_key = f'thread:{post_id}:{limit}:{depth}'
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        submission = await reddit.submission(id=post_id)
        await submission.load()

        if limit is not None:
            submission.comment_limit = max(int(limit), 1)
        submission.comment_sort = 'confidence'

        replace_limit: int | None = None
        configured_batches = int(self._settings.reddit_morechildren_max_batches)
        if configured_batches > 0:
            replace_limit = configured_batches
        await submission.comments.replace_more(limit=replace_limit)

        comments = []
        for node in submission.comments:
            converted = self._comment_node_to_listing(node=node, depth=0, max_depth=depth)
            if converted is not None:
                comments.append(converted)

        payload = [
            {
                'kind': 'Listing',
                'data': {
                    'children': [
                        {
                            'kind': 't3',
                            'data': self._submission_to_dict(submission),
                        }
                    ],
                },
            },
            {
                'kind': 'Listing',
                'data': {
                    'children': comments,
                },
            },
        ]
        self._cache[cache_key] = payload
        return payload

    async def get_morechildren(self, post_id: str, children: list[str], sort: str = 'confidence') -> Any:
        if not children:
            return {}
        reddit = self._require_reddit()
        cache_key = f'more:{post_id}:{sort}:{",".join(children)}'
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        fullnames = [f't1_{child_id}' for child_id in children if child_id]
        comment_by_id: dict[str, dict[str, Any]] = {}
        info_gen = reddit.info(fullnames=fullnames)
        async for item in info_gen:
            item_id = str(getattr(item, 'id', '') or '')
            if not item_id:
                continue
            comment_by_id[item_id] = {'kind': 't1', 'data': self._comment_to_data(item)}

        ordered = [comment_by_id[child_id] for child_id in children if child_id in comment_by_id]
        payload = {'json': {'data': {'things': ordered}}}
        self._cache[cache_key] = payload
        return payload

    def _require_reddit(self) -> Any:
        if self._reddit is None:
            raise RuntimeError('RedditClient is not initialized')
        return self._reddit

    def _submission_to_dict(self, submission: Any) -> dict[str, Any]:
        subreddit_obj = getattr(submission, 'subreddit', None)
        subreddit_name = str(
            getattr(subreddit_obj, 'display_name', None)
            or getattr(submission, 'subreddit', '')
            or ''
        )
        preview = getattr(submission, 'preview', None)
        if not isinstance(preview, dict):
            preview = {}
        return {
            'id': str(getattr(submission, 'id', '') or ''),
            'subreddit': subreddit_name,
            'created_utc': float(getattr(submission, 'created_utc', 0) or 0),
            'title': str(getattr(submission, 'title', '') or ''),
            'selftext': str(getattr(submission, 'selftext', '') or ''),
            'url': str(getattr(submission, 'url', '') or ''),
            'score': int(getattr(submission, 'score', 0) or 0),
            'num_comments': int(getattr(submission, 'num_comments', 0) or 0),
            'permalink': str(getattr(submission, 'permalink', '') or ''),
            'preview': preview,
        }

    def _comment_node_to_listing(
        self,
        *,
        node: Any,
        depth: int,
        max_depth: int | None,
    ) -> dict[str, Any] | None:
        if self._is_more_node(node):
            children = [str(child_id) for child_id in getattr(node, 'children', []) if child_id]
            if not children:
                return None
            return {
                'kind': 'more',
                'data': {
                    'id': str(getattr(node, 'id', '') or ''),
                    'parent_id': str(getattr(node, 'parent_id', '') or ''),
                    'children': children,
                },
            }

        comment_id = str(getattr(node, 'id', '') or '')
        if not comment_id:
            return None

        author = getattr(node, 'author', None)
        author_str = str(author) if author is not None else None
        if author_str == '[deleted]':
            author_str = None

        replies: Any = ''
        if max_depth is None or depth < max_depth:
            reply_nodes = []
            for child in getattr(node, 'replies', []):
                converted = self._comment_node_to_listing(node=child, depth=depth + 1, max_depth=max_depth)
                if converted is not None:
                    reply_nodes.append(converted)
            replies = {
                'kind': 'Listing',
                'data': {
                    'children': reply_nodes,
                },
            }

        return {
            'kind': 't1',
            'data': {
                'id': comment_id,
                'parent_id': str(getattr(node, 'parent_id', '') or ''),
                'author': author_str,
                'created_utc': float(getattr(node, 'created_utc', 0) or 0),
                'score': int(getattr(node, 'score', 0) or 0),
                'body': str(getattr(node, 'body', '') or ''),
                'permalink': str(getattr(node, 'permalink', '') or ''),
                'replies': replies,
            },
        }

    def _comment_to_data(self, comment: Any) -> dict[str, Any]:
        author = getattr(comment, 'author', None)
        author_str = str(author) if author is not None else None
        if author_str == '[deleted]':
            author_str = None
        return {
            'id': str(getattr(comment, 'id', '') or ''),
            'parent_id': str(getattr(comment, 'parent_id', '') or ''),
            'author': author_str,
            'created_utc': float(getattr(comment, 'created_utc', 0) or 0),
            'score': int(getattr(comment, 'score', 0) or 0),
            'body': str(getattr(comment, 'body', '') or ''),
            'permalink': str(getattr(comment, 'permalink', '') or ''),
            'replies': '',
        }

    def _is_more_node(self, node: Any) -> bool:
        return node.__class__.__name__ == 'MoreComments'


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
