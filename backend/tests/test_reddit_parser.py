from __future__ import annotations

from app.services.reddit_parser import parse_morechildren, parse_thread, parse_thread_with_more


def test_parse_thread_nested_replies_and_depth() -> None:
    payload = [
        {
            'kind': 'Listing',
            'data': {
                'children': [
                    {
                        'kind': 't3',
                        'data': {
                            'id': 'post1',
                            'subreddit': 'stocks',
                            'created_utc': 1700000000,
                            'title': 'AAPL discussion',
                            'selftext': 'text',
                            'url': 'https://reddit.com/r/stocks/post1',
                            'score': 100,
                            'num_comments': 2,
                            'permalink': '/r/stocks/comments/post1/test/',
                        },
                    }
                ]
            },
        },
        {
            'kind': 'Listing',
            'data': {
                'children': [
                    {
                        'kind': 't1',
                        'data': {
                            'id': 'c1',
                            'parent_id': 't3_post1',
                            'author': 'user1',
                            'created_utc': 1700000100,
                            'score': 5,
                            'body': 'Top comment',
                            'permalink': '/r/stocks/comments/post1/test/c1/',
                            'replies': {
                                'kind': 'Listing',
                                'data': {
                                    'children': [
                                        {
                                            'kind': 't1',
                                            'data': {
                                                'id': 'c2',
                                                'parent_id': 't1_c1',
                                                'author': 'user2',
                                                'created_utc': 1700000200,
                                                'score': 3,
                                                'body': 'Reply',
                                                'permalink': '/r/stocks/comments/post1/test/c2/',
                                                'replies': '',
                                            },
                                        }
                                    ]
                                },
                            },
                        },
                    },
                    {'kind': 'more', 'data': {'id': 'm1'}},
                ]
            },
        },
    ]

    submission, comments = parse_thread(payload)

    assert submission is not None
    assert submission.id == 'post1'
    assert len(comments) == 2

    c1 = next(c for c in comments if c.id == 'c1')
    c2 = next(c for c in comments if c.id == 'c2')

    assert c1.parent_id == 'post1'
    assert c1.depth == 0

    assert c2.parent_id == 'c1'
    assert c2.depth == 1


def test_parse_thread_collects_pending_more_nodes() -> None:
    payload = [
        {
            'kind': 'Listing',
            'data': {
                'children': [
                    {
                        'kind': 't3',
                        'data': {
                            'id': 'post1',
                            'subreddit': 'stocks',
                            'created_utc': 1700000000,
                            'title': 'AAPL discussion',
                            'selftext': 'text',
                            'url': 'https://reddit.com/r/stocks/post1',
                            'score': 100,
                            'num_comments': 3,
                            'permalink': '/r/stocks/comments/post1/test/',
                        },
                    }
                ]
            },
        },
        {
            'kind': 'Listing',
            'data': {
                'children': [
                    {
                        'kind': 'more',
                        'data': {
                            'id': 'm1',
                            'parent_id': 't3_post1',
                            'children': ['c3', 'c4'],
                        },
                    }
                ]
            },
        },
    ]

    submission, comments, pending = parse_thread_with_more(payload)
    assert submission is not None
    assert comments == []
    assert len(pending) == 1
    assert pending[0].parent_id == 'post1'
    assert pending[0].depth == 0
    assert pending[0].children == ['c3', 'c4']


def test_parse_morechildren_resolves_depth_from_parent() -> None:
    payload = {
        'json': {
            'data': {
                'things': [
                    {
                        'kind': 't1',
                        'data': {
                            'id': 'c3',
                            'parent_id': 't1_c2',
                            'author': 'user3',
                            'created_utc': 1700000300,
                            'score': 2,
                            'body': 'Deep reply',
                            'permalink': '/r/stocks/comments/post1/test/c3/',
                            'replies': '',
                        },
                    }
                ]
            }
        }
    }

    comments, pending = parse_morechildren(
        payload,
        submission_id='post1',
        parent_depths={'c2': 1},
        fallback_parent_id='post1',
        fallback_depth=0,
    )

    assert len(comments) == 1
    assert comments[0].id == 'c3'
    assert comments[0].parent_id == 'c2'
    assert comments[0].depth == 2
    assert pending == []
