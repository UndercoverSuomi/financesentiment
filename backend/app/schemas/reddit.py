from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ParsedSubmission:
    id: str
    subreddit: str
    created_utc: datetime
    title: str
    selftext: str
    url: str
    score: int
    num_comments: int
    permalink: str
    raw: dict


@dataclass(slots=True)
class ParsedComment:
    id: str
    submission_id: str
    parent_id: str | None
    depth: int
    author: str | None
    created_utc: datetime
    score: int
    body: str
    permalink: str
