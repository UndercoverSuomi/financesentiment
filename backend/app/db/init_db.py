from __future__ import annotations

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == '__main__':
    init_db()
