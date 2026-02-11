from __future__ import annotations

import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / 'backend'
sys.path.insert(0, str(BACKEND_ROOT))

from app.api.deps import get_ingestion_service
from app.core.config import get_settings
from app.db.session import SessionLocal


async def main(subreddit: str | None = None) -> None:
    settings = get_settings()
    service = get_ingestion_service()

    with SessionLocal() as session:
        if subreddit:
            result = await service.pull_subreddit(session, subreddit=subreddit)
            print(result)
        else:
            results = await service.pull_all(session)
            for row in results:
                print(row)


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg and arg not in get_settings().subreddits:
        raise SystemExit(f'Subreddit must be one of: {get_settings().subreddits}')
    asyncio.run(main(arg))
