from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / 'backend'
sys.path.insert(0, str(BACKEND_ROOT))

from app.api.deps import get_evaluation_service


def main(dataset_path: str | None = None, max_rows: int | None = None) -> None:
    service = get_evaluation_service()
    report = service.evaluate(dataset_path=dataset_path, max_rows=max_rows)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    dataset_arg = sys.argv[1] if len(sys.argv) > 1 else None
    max_rows_arg = int(sys.argv[2]) if len(sys.argv) > 2 else None
    main(dataset_arg, max_rows_arg)
