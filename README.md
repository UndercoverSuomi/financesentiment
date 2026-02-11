# financesentiment

Reddit ticker-targeted stance analytics MVP.

This project ingests Reddit `.json` endpoints server-side, parses full comment trees, extracts ticker mentions, computes per-ticker stance (`BULLISH`, `BEARISH`, `NEUTRAL`, `UNCLEAR`), aggregates daily scores by `(date_bucket_berlin, subreddit, ticker)`, and serves a dashboard UI.

## Architecture

- `backend/`: FastAPI + SQLAlchemy + SQLite + Alembic
- `frontend/`: Next.js App Router + Tailwind
- `scripts/pull_once.py`: CLI pull trigger
- `data/images/`: optional image downloads
- `tickers_sample.csv`, `synonyms.json`, `stoplist.json`: ticker extraction resources

## Einfach erklaert (fuer alle)

Die App beantwortet im Kern diese Frage:

"Wie reden Reddit-Nutzer ueber bestimmte Aktien, und wird die Haltung eher positiv oder negativ?"

So laeuft es Schritt fuer Schritt:

1. Die App lädt Reddit-Posts und Kommentare fuer deine konfigurierten Subreddits.
2. Sie erkennt darin Ticker wie `AAPL`, `TSLA`, `MSFT`.
3. Pro Ticker-Erwaehnung wird eine Haltung vergeben:
   - `BULLISH` (eher positiv)
   - `BEARISH` (eher negativ)
   - `NEUTRAL`
   - `UNCLEAR` (nicht sicher zuordenbar)
4. Danach werden alle Einzelwerte zu Tages-/Fensterwerten zusammengefasst.
5. Im Dashboard siehst du:
   - Top-Ticker
   - Score-Entwicklung
   - Unsicherheit
   - Datenqualitaet
   - tiefere Analytics (Regime, Movers, Korrelationen usw.)

Wichtig: Die App ist kein Trading-Bot. Sie liefert ein Stimmungs-/Diskussions-Radar.

## Scientific scope

This app computes **ticker-targeted stance**, not generic sentiment.

Per mention target, context is built as:

```text
TITLE: ...
SELF: ...
PARENT: ...
TEXT: ...
```

UNCLEAR handling:

- max model probability `< UNCLEAR_THRESHOLD` (default `0.55`), or
- short text and ticker only inherited from title/parent context.
- context-inherited comment tickers are `UNCLEAR` by default (`ALLOW_CONTEXT_LABEL_INFERENCE=false`).

Daily aggregation stores:

- `score_unweighted`: mean `stance_score` over non-UNCLEAR rows
- `score_weighted`: weighted mean with `log(1 + max(upvote, 0))`
- uncertainty metrics: `score_stddev_unweighted`, `ci95_low_unweighted`, `ci95_high_unweighted`
- counts: mention + label distribution + `unclear_rate`
- sufficient statistics (`valid_count`, `score_sum_unweighted`, `weighted_numerator`, `weighted_denominator`) for exact cross-subreddit recombination.

## Hard constraints implemented

- Frontend never calls Reddit directly.
- Backend uses structured Reddit JSON endpoints only:
  - `/r/{subreddit}/top.json?...&raw_json=1`
  - `/comments/{post_id}.json?...&raw_json=1`
- User-Agent and `Accept: application/json` set on Reddit requests.
- Reddit rate limiting/backoff/caching implemented:
  - semaphore concurrency limit
  - retries on `429/5xx`
  - `Retry-After` respected
  - in-memory per-run URL cache
- Recursive comment tree parsing stores `parent_id` + `depth`.
- `more` placeholders are expanded via `/api/morechildren.json` (batched) for higher thread completeness.

## Quickstart

### 1) Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Backend runs on `http://localhost:8000`.

Fallback (if skipping Alembic for quick local MVP):

```bash
python -m app.db.init_db
```

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:3000`.

Research dashboard: `http://localhost:3000/research`

### 3) Environment

Copy `.env.example` to `.env` and edit values as needed.

Defaults:

- subreddits: `StockMarket,wallstreetbetsGER,ValueInvesting,Finanzen,wallstreetbets,stocks,investing,Aktien`
- sort: `top`
- time window: `t=week`
- posts per page: `100`
- listing pages per pull: `8` (bis zu ~800 Posts pro Subreddit/Pull, falls Reddit so viel liefert)
- thread depth: `32`
- morechildren batch cap: `30`
- concurrency: `1` (stabiler gegen Rate-Limits)
- backoff base: `1.25`

### "Alles nehmen" - was realistisch geht

Die App ist jetzt auf sehr breite Abdeckung eingestellt:

- `PULL_T_PARAM=week`
- `PULL_LIMIT=100` (Reddit-API-Obergrenze pro Listing-Seite)
- `PULL_MAX_PAGES=8` (Pagination ueber weitere Seiten)
- `REDDIT_MORECHILDREN_MAX_BATCHES=30` (mehr Kommentar-Aufloesung, aber noch stabil)
- `REDDIT_MAX_CONCURRENCY=1` + `REDDIT_BACKOFF_BASE=1.25` (weniger 429-Fehler)

Das kommt sehr nah an "alles aus der Woche" fuer die gewaehlten Subreddits.
Vollstaendig "absolut alles" garantiert die Reddit-API dennoch nicht (Ranking, API-Limits, geloeschte Inhalte, Rate-Limits).

## Ingestion and reproducibility

Each pull writes `pull_runs` with:

- `pulled_at_utc`
- `date_bucket_berlin` (derived from UTC pull timestamp)
- `subreddit`
- `sort`
- `t_param`
- `limit`
- `status`, `error`

This makes daily sampling auditable and reproducible.

If Reddit returns temporary errors (`429`, timeout, etc.) for single threads, the pull now continues with the remaining posts.
In that case, `status` stays `success` and `error` contains a short `partial errors: ...` summary.

Trigger pulls via API:

- `POST /api/pull?subreddit=stocks`
- `POST /api/pull_all`

Or CLI:

```bash
python scripts/pull_once.py
python scripts/pull_once.py stocks
```

Build a larger ticker universe by merging multiple symbol CSVs:

```bash
python scripts/build_ticker_universe.py tickers_master.csv source_us.csv source_eu.csv
```

## API endpoints

- `GET /api/subreddits`
- `POST /api/pull?subreddit=...`
- `POST /api/pull_all`
- `GET /api/results?date=YYYY-MM-DD&window=24h|7d&subreddit=...`
- `GET /api/analytics?days=21&date=YYYY-MM-DD&subreddit=...`
- `GET /api/quality?date=YYYY-MM-DD&subreddit=...`
- `GET /api/evaluate?dataset_path=...&max_rows=...`
- `GET /api/ticker/{ticker}?days=30&subreddit=...`
- `GET /api/thread/{submission_id}`

## Scientific evaluation

Use a gold-label CSV (`target_type,ticker,gold_label,text,title,selftext,parent_text`) to evaluate model quality:

```bash
python scripts/evaluate_gold.py
python scripts/evaluate_gold.py gold_labels_sample.csv 2000
```

The endpoint `GET /api/evaluate` returns:

- accuracy, macro/weighted F1
- per-label precision/recall/F1
- confusion matrix
- expected calibration error (ECE)
- detection-source rates + sample misclassifications

## Optional features

### External link text extraction

Set `ENABLE_EXTERNAL_EXTRACTION=true`.

- fetches external article HTML server-side with short timeouts
- tries `trafilatura`, then readability fallback
- stores extraction status and capped text (`EXTRACTION_TEXT_CAP`)
- does not bypass paywalls

### Image handling

Set `DOWNLOAD_IMAGES=true`.

- detects image URLs from submission URL and Reddit preview images
- validates content-type + max size
- stores local files under `data/images/{date_bucket}/{submission_id}/...`

### FinBERT (optional)

Set `USE_FINBERT=true`.

- if FinBERT is unavailable or fails to load, app falls back to deterministic CPU-safe model
- to enable FinBERT inference, install `transformers` (+ runtime dependencies) in backend env

## Tests

Run:

```bash
cd backend
pytest
```

Included tests:

- nested Reddit thread parsing
- ticker extraction stoplist/synonym behavior
- aggregation correctness
- API smoke test (`/api/subreddits`, `/api/results`)

## Limitations

- Top-10 daily listing sample introduces selection bias.
- Reddit text sarcasm/irony can reduce stance accuracy.
- Bots, brigading, and meme language may skew signal.
- Ticker ambiguity remains for short uppercase tokens.
- UNCLEAR rate should be interpreted as uncertainty, not noise to discard.

## Scheduling

For MVP, use OS cron/task scheduler. Example every hour:

```bash
python scripts/pull_once.py
```

No Redis/Celery required for this MVP.
