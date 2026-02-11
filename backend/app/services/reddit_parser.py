from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.reddit import ParsedComment, ParsedSubmission
from app.utils.ids import normalize_parent_id


def parse_listing_posts(payload: dict[str, Any]) -> list[ParsedSubmission]:
    children = payload.get('data', {}).get('children', [])
    submissions: list[ParsedSubmission] = []
    for child in children:
        if child.get('kind') != 't3':
            continue
        data = child.get('data', {})
        post_id = data.get('id')
        if not post_id:
            continue
        submissions.append(
            ParsedSubmission(
                id=post_id,
                subreddit=str(data.get('subreddit', '')),
                created_utc=datetime.fromtimestamp(float(data.get('created_utc', 0)), tz=timezone.utc),
                title=str(data.get('title', '')),
                selftext=str(data.get('selftext', '')),
                url=str(data.get('url', '')),
                score=int(data.get('score', 0) or 0),
                num_comments=int(data.get('num_comments', 0) or 0),
                permalink=str(data.get('permalink', '')),
                raw=data,
            )
        )
    return submissions


def parse_thread(payload: Any) -> tuple[ParsedSubmission | None, list[ParsedComment]]:
    if not isinstance(payload, list) or len(payload) < 2:
        return None, []

    submission_listing = payload[0]
    comment_listing = payload[1]

    submission = _parse_submission_from_listing(submission_listing)
    comments: list[ParsedComment] = []

    if submission is None:
        return None, comments

    children = comment_listing.get('data', {}).get('children', []) if isinstance(comment_listing, dict) else []
    for child in children:
        _walk_comment_tree(child, submission.id, comments, depth=0)

    return submission, comments


def _parse_submission_from_listing(listing: Any) -> ParsedSubmission | None:
    if not isinstance(listing, dict):
        return None
    children = listing.get('data', {}).get('children', [])
    for child in children:
        if child.get('kind') != 't3':
            continue
        data = child.get('data', {})
        post_id = data.get('id')
        if not post_id:
            continue
        return ParsedSubmission(
            id=post_id,
            subreddit=str(data.get('subreddit', '')),
            created_utc=datetime.fromtimestamp(float(data.get('created_utc', 0)), tz=timezone.utc),
            title=str(data.get('title', '')),
            selftext=str(data.get('selftext', '')),
            url=str(data.get('url', '')),
            score=int(data.get('score', 0) or 0),
            num_comments=int(data.get('num_comments', 0) or 0),
            permalink=str(data.get('permalink', '')),
            raw=data,
        )
    return None


def _walk_comment_tree(node: dict[str, Any], submission_id: str, out: list[ParsedComment], depth: int) -> None:
    if node.get('kind') != 't1':
        return

    data = node.get('data', {})
    comment_id = data.get('id')
    if not comment_id:
        return

    parsed = ParsedComment(
        id=str(comment_id),
        submission_id=submission_id,
        parent_id=normalize_parent_id(data.get('parent_id')),
        depth=depth,
        author=(None if data.get('author') in {'[deleted]', None} else str(data.get('author'))),
        created_utc=datetime.fromtimestamp(float(data.get('created_utc', 0)), tz=timezone.utc),
        score=int(data.get('score', 0) or 0),
        body=str(data.get('body', '')),
        permalink=str(data.get('permalink', '')),
    )
    out.append(parsed)

    replies = data.get('replies')
    if isinstance(replies, dict):
        reply_children = replies.get('data', {}).get('children', [])
        for child in reply_children:
            _walk_comment_tree(child, submission_id, out, depth=depth + 1)
