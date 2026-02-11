from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.schemas.reddit import ParsedComment, ParsedSubmission
from app.utils.ids import normalize_parent_id


@dataclass(slots=True)
class PendingMore:
    parent_id: str | None
    depth: int
    children: list[str]


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
    submission, comments, _ = parse_thread_with_more(payload)
    return submission, comments


def parse_thread_with_more(payload: Any) -> tuple[ParsedSubmission | None, list[ParsedComment], list[PendingMore]]:
    if not isinstance(payload, list) or len(payload) < 2:
        return None, [], []

    submission_listing = payload[0]
    comment_listing = payload[1]

    submission = _parse_submission_from_listing(submission_listing)
    comments: list[ParsedComment] = []
    pending_more: list[PendingMore] = []

    if submission is None:
        return None, comments, pending_more

    children = comment_listing.get('data', {}).get('children', []) if isinstance(comment_listing, dict) else []
    for child in children:
        _walk_comment_tree(child, submission.id, comments, pending_more, depth=0)

    return submission, comments, pending_more


def parse_morechildren(
    payload: Any,
    submission_id: str,
    *,
    parent_depths: dict[str, int],
    fallback_parent_id: str | None,
    fallback_depth: int,
) -> tuple[list[ParsedComment], list[PendingMore]]:
    if not isinstance(payload, dict):
        return [], []

    things = (
        payload.get('json', {})
        .get('data', {})
        .get('things', [])
    )
    if not isinstance(things, list):
        return [], []

    comments: list[ParsedComment] = []
    pending_more: list[PendingMore] = []
    resolved_parent_depths = dict(parent_depths)
    for thing in things:
        if not isinstance(thing, dict):
            continue

        kind = thing.get('kind')
        data = thing.get('data', {})
        if not isinstance(data, dict):
            continue

        if kind == 't1':
            parsed = _parse_comment_from_data(
                data,
                submission_id=submission_id,
                parent_depths=resolved_parent_depths,
                fallback_parent_id=fallback_parent_id,
                fallback_depth=fallback_depth,
            )
            if parsed is None:
                continue
            comments.append(parsed)
            resolved_parent_depths[parsed.id] = parsed.depth

            replies = data.get('replies')
            if isinstance(replies, dict):
                reply_children = replies.get('data', {}).get('children', [])
                for child in reply_children:
                    _walk_comment_tree(
                        child,
                        submission_id=submission_id,
                        out=comments,
                        out_more=pending_more,
                        depth=parsed.depth + 1,
                    )
            continue

        if kind == 'more':
            children = [str(c) for c in data.get('children', []) if isinstance(c, str) and c]
            if not children:
                continue
            parent_id = normalize_parent_id(data.get('parent_id')) or fallback_parent_id
            depth = _resolve_depth(
                parent_id=parent_id,
                submission_id=submission_id,
                parent_depths=resolved_parent_depths,
                fallback_depth=fallback_depth,
            )
            pending_more.append(PendingMore(parent_id=parent_id, depth=depth, children=children))

    return comments, pending_more


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


def _walk_comment_tree(
    node: dict[str, Any],
    submission_id: str,
    out: list[ParsedComment],
    out_more: list[PendingMore],
    depth: int,
) -> None:
    kind = node.get('kind')
    if kind == 'more':
        data = node.get('data', {})
        if not isinstance(data, dict):
            return
        children = [str(c) for c in data.get('children', []) if isinstance(c, str) and c]
        if not children:
            return
        out_more.append(
            PendingMore(
                parent_id=normalize_parent_id(data.get('parent_id')),
                depth=max(depth, 0),
                children=children,
            )
        )
        return

    if kind != 't1':
        return

    data = node.get('data', {})
    parsed = _parse_comment_from_data(
        data,
        submission_id=submission_id,
        parent_depths={},
        fallback_parent_id=None,
        fallback_depth=depth,
    )
    if parsed is None:
        return
    out.append(parsed)

    replies = data.get('replies')
    if isinstance(replies, dict):
        reply_children = replies.get('data', {}).get('children', [])
        for child in reply_children:
            _walk_comment_tree(child, submission_id, out, out_more, depth=depth + 1)


def _parse_comment_from_data(
    data: dict[str, Any],
    *,
    submission_id: str,
    parent_depths: dict[str, int],
    fallback_parent_id: str | None,
    fallback_depth: int,
) -> ParsedComment | None:
    comment_id = data.get('id')
    if not comment_id:
        return None

    parent_id = normalize_parent_id(data.get('parent_id')) or fallback_parent_id
    depth = _resolve_depth(
        parent_id=parent_id,
        submission_id=submission_id,
        parent_depths=parent_depths,
        fallback_depth=fallback_depth,
    )
    return ParsedComment(
        id=str(comment_id),
        submission_id=submission_id,
        parent_id=parent_id,
        depth=depth,
        author=(None if data.get('author') in {'[deleted]', None} else str(data.get('author'))),
        created_utc=datetime.fromtimestamp(float(data.get('created_utc', 0)), tz=timezone.utc),
        score=int(data.get('score', 0) or 0),
        body=str(data.get('body', '')),
        permalink=str(data.get('permalink', '')),
    )


def _resolve_depth(parent_id: str | None, submission_id: str, parent_depths: dict[str, int], fallback_depth: int) -> int:
    if parent_id is None:
        return max(fallback_depth, 0)
    if parent_id == submission_id:
        return 0
    parent_depth = parent_depths.get(parent_id)
    if parent_depth is not None:
        return parent_depth + 1
    return max(fallback_depth, 0)
