from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
sys.path.insert(0, str(BACKEND))

TEST_DB_PATH = BACKEND / 'data' / 'test_app.db'
TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
os.environ['DATABASE_URL'] = f"sqlite:///{TEST_DB_PATH.as_posix()}"

from app.core.config import get_settings

get_settings.cache_clear()
from app.db.init_db import init_db

init_db()


def pytest_sessionfinish(session, exitstatus):  # type: ignore[no-untyped-def]
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except PermissionError:
            pass
