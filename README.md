# financesentiment

Reddit ticker-targeted stance analytics MVP.

This project ingests Reddit `.json` endpoints server-side, parses full comment trees, extracts ticker mentions, computes per-ticker stance (`BULLISH`, `BEARISH`, `NEUTRAL`, `UNCLEAR`), aggregates daily scores by `(date_bucket_berlin, subreddit, ticker)`, and serves a dashboard UI.

## Architecture

- `backend/`: FastAPI + SQLAlchemy + SQLite + Alembic
- `frontend/`: Next.js App Router + Tailwind
- `scripts/pull_once.py`: CLI pull trigger
- `data/images/`: optional image downloads
- `tickers_sample.csv`, `synonyms.json`, `stoplist.json`: ticker extraction resources

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

Daily aggregation stores:

- `score_unweighted`: mean `stance_score` over non-UNCLEAR rows
- `score_weighted`: weighted mean with `log(1 + max(upvote, 0))`
- counts: mention + label distribution + `unclear_rate`

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

### 3) Environment

Copy `.env.example` to `.env` and edit values as needed.

Defaults:

- subreddits: `StockMarket,wallstreetbetsGER,ValueInvesting,Finanzen,wallstreetbets,stocks,investing,Aktien`
- sort: `top`
- time window: `t=day`
- limit: `10`

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

Trigger pulls via API:

- `POST /api/pull?subreddit=stocks`
- `POST /api/pull_all`

Or CLI:

```bash
python scripts/pull_once.py
python scripts/pull_once.py stocks
```

## API endpoints

- `GET /api/subreddits`
- `POST /api/pull?subreddit=...`
- `POST /api/pull_all`
- `GET /api/results?date=YYYY-MM-DD&subreddit=...`
- `GET /api/ticker/{ticker}?days=30&subreddit=...`
- `GET /api/thread/{submission_id}`

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
