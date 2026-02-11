from __future__ import annotations

from app.services.reddit_parser import parse_thread


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
