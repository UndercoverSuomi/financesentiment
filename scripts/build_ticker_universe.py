from __future__ import annotations

import csv
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

VALID_TICKER_RE = re.compile(r'^[A-Z][A-Z0-9\.]{0,9}$')
TICKER_COLUMNS = ('ticker', 'symbol', 'code')
NAME_COLUMNS = ('name', 'company', 'company_name', 'security')


def normalize_ticker(raw: str) -> str | None:
    ticker = raw.strip().upper()
    if not ticker:
        return None
    if not VALID_TICKER_RE.match(ticker):
        return None
    return ticker


def detect_column(fieldnames: list[str], candidates: tuple[str, ...]) -> str | None:
    mapping = {name.lower().strip(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in mapping:
            return mapping[candidate]
    return None


def load_source(path: Path) -> dict[str, tuple[str, str]]:
    rows: dict[str, tuple[str, str]] = {}
    with path.open('r', encoding='utf-8', newline='') as file:
        reader = csv.DictReader(file)
        fields = reader.fieldnames or []
        ticker_col = detect_column(fields, TICKER_COLUMNS)
        if ticker_col is None:
            raise ValueError(f'{path} is missing ticker column (expected one of {TICKER_COLUMNS})')
        name_col = detect_column(fields, NAME_COLUMNS)

        for raw in reader:
            ticker_raw = str(raw.get(ticker_col, '') or '')
            ticker = normalize_ticker(ticker_raw)
            if ticker is None:
                continue
            name = str(raw.get(name_col, '') or '').strip() if name_col else ''
            rows[ticker] = (name, path.name)
    return rows


def write_output(path: Path, rows: dict[str, tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['ticker', 'name', 'source'])
        writer.writeheader()
        for ticker in sorted(rows.keys()):
            name, source = rows[ticker]
            writer.writerow({'ticker': ticker, 'name': name, 'source': source})


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print('Usage: python scripts/build_ticker_universe.py <output.csv> <source1.csv> [source2.csv ...]')
        return 2

    output = (ROOT / argv[0]).resolve() if not Path(argv[0]).is_absolute() else Path(argv[0]).resolve()
    sources = [
        (ROOT / src).resolve() if not Path(src).is_absolute() else Path(src).resolve()
        for src in argv[1:]
    ]

    merged: dict[str, tuple[str, str]] = {}
    for source in sources:
        if not source.exists():
            raise FileNotFoundError(f'source not found: {source}')
        loaded = load_source(source)
        for ticker, value in loaded.items():
            if ticker not in merged:
                merged[ticker] = value

    write_output(output, merged)
    print(f'Wrote {len(merged)} tickers to {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
