# financesentiment

Reddit ticker-targeted stance analytics MVP.

This project ingests Reddit JSON via the official OAuth API server-side, parses full comment trees, extracts ticker mentions, computes per-ticker stance (`BULLISH`, `BEARISH`, `NEUTRAL`, `UNCLEAR`), aggregates daily scores by `(date_bucket_berlin, subreddit, ticker)`, and serves a dashboard UI.

## Architecture

- `backend/`: FastAPI + SQLAlchemy + Alembic (`SQLite` for local dev, `PostgreSQL` in Docker Compose)
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
- Backend uses structured Reddit JSON endpoints only (official OAuth API host):
  - `/r/{subreddit}/top.json?...&raw_json=1`
  - `/comments/{post_id}.json?...&raw_json=1`
- User-Agent and `Accept: application/json` set on Reddit requests.
- OAuth access tokens are fetched via `client_credentials` and attached as `Authorization: Bearer ...`.
- Reddit rate limiting/backoff/caching implemented:
  - semaphore concurrency limit
  - hard rolling requests-per-minute guard (`REDDIT_MAX_REQUESTS_PER_MINUTE`, default `90`)
  - retries on `429/5xx`
  - `Retry-After` respected
  - in-memory per-run URL cache
- Recursive comment tree parsing stores `parent_id` + `depth`.
- `more` placeholders are expanded via `/api/morechildren.json` (batched) for higher thread completeness.

## Quickstart

### Docker (backend + frontend + postgres)

1. Copy `.env.example` to `.env` (first time only) and set your secrets.
2. Start everything from repo root:

```bash
docker compose up --build
```

Services:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- PostgreSQL: `localhost:5432`

Stop:

```bash
docker compose down
```

Reset DB volume:

```bash
docker compose down -v
```

Notes:

- Backend/Frontend receive environment variables via `.env` (`env_file` in Compose).
- Compose sets backend `DATABASE_URL` from `DATABASE_URL_DOCKER` (defaults to Postgres service `db`).
- Frontend uses `NEXT_PUBLIC_API_BASE_URL` for browser calls and `API_BASE_URL_SERVER` for server-side fetches.

### Local dev (without Docker)

From repo root:

```bash
python scripts/dev_up.py
```

Windows PowerShell shortcut:

```powershell
.\start-dev.ps1
```

This boots backend + frontend together, including setup checks (venv/deps/migrations) on first run.

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
- time window: `t=day`
- posts per page: `20`
- listing pages per pull: `1` (Top-20 Posts pro Subreddit/Pull)
- thread depth: `32`
- morechildren batch cap: `40` (fester Cap pro Submission fuer tiefe, aber kontrollierte Kommentarabdeckung)
- official API mode: `REDDIT_USE_OFFICIAL_API=true`
- oauth API host: `REDDIT_BASE_URL=https://oauth.reddit.com`
- oauth token endpoint: `REDDIT_OAUTH_TOKEN_URL=https://www.reddit.com/api/v1/access_token`
- oauth scope: `REDDIT_OAUTH_SCOPE=read`
- required: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`
- concurrency: `1` (stabiler gegen Rate-Limits)
- max request rate: `90 RPM` (unterhalb des 100 RPM Free-Limits)
- backoff base: `2.0`
- min request interval: `0.70s`
- pause between subreddits in pull-all: `2.0s`
- proxy rotation: disabled by default (`REDDIT_PROXY_URLS_CSV` empty)
- docker DB URL override: `DATABASE_URL_DOCKER=postgresql+psycopg://financesentiment:financesentiment@db:5432/financesentiment`
- frontend server-side API base in Docker: `API_BASE_URL_SERVER=http://backend:8000`

### Official API setup (kostenloser Modus)

1. Erstelle eine Reddit-App unter `reddit.com/prefs/apps`.
2. Trage in `.env` `REDDIT_CLIENT_ID` ein.
3. Trage in `.env` `REDDIT_CLIENT_SECRET` ein.
4. Nutze einen klaren `REDDIT_USER_AGENT` mit Kontakt (Reddit Policy).
5. Lass `REDDIT_MAX_REQUESTS_PER_MINUTE=90`, um unter dem 100 RPM Free-Limit zu bleiben.

Wenn `REDDIT_USE_OFFICIAL_API=true` und `REDDIT_CLIENT_ID` fehlt, bricht der Pull mit klarer Fehlermeldung ab.

### "Top-20 / 24h + moeglichst alle Kommentare" (aktuelles Setup)

Die App ist jetzt auf schnellere Pulls pro Subreddit eingestellt, bei gleichzeitig tiefer Kommentarabdeckung:

- `PULL_SORT=top`
- `PULL_T_PARAM=day`
- `PULL_LIMIT=20`
- `PULL_MAX_PAGES=1`
- `REDDIT_MORECHILDREN_MAX_BATCHES=40` (fester Cap pro Submission)
- `REDDIT_MAX_CONCURRENCY=1`, `REDDIT_BACKOFF_BASE=2.0`, `REDDIT_MIN_REQUEST_INTERVAL_SECONDS=0.45`
- `PULL_SUBREDDIT_PAUSE_SECONDS=2.0` (weniger Burst-Spitzen bei `pull all`)

Tradeoff:

- deutlich schneller als "1000 Posts pro Subreddit"
- dafuer nur Top-20 Posts der letzten 24h
- Kommentarabdeckung pro gewaehltem Post ist tief ausgelegt (bis 40 MoreChildren-Batches), bleibt aber von Reddit-API-Limits/Timeouts abhaengig

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
- `POST /api/pull/start?subreddit=stocks` (background job)
- `POST /api/pull/start` (all configured subreddits; prevents duplicate parallel runs)
- `GET /api/pull/jobs/{job_id}` (progress polling)
- `GET /api/pull/status` (latest per-subreddit status + last successful pull)

Local browser/CORS hint:

- if you open frontend via `http://127.0.0.1:3000`, backend CORS must allow that origin too.
- defaults now include both `http://localhost:3000` and `http://127.0.0.1:3000` via `FRONTEND_ORIGINS_CSV`.

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
- `POST /api/pull/start?subreddit=...` (background job, `subreddit=ALL|*|empty` => all)
- `GET /api/pull/jobs/{job_id}` (job progress/status)
- `GET /api/pull/status` (latest run status + last successful pull overview)
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

### Gemini LLM fallback (optional)

Set `USE_LLM_MODEL=true` and configure:

- `GEMINI_API_KEY`
- `GEMINI_MODEL` (default: `gemini-3-flash-preview`)
- `GEMINI_API_BASE_URL` (default: `https://generativelanguage.googleapis.com/v1beta`)

Control cost/latency with:

- `LLM_UNCLEAR_ONLY=true` (default): call LLM only for low-confidence/UNCLEAR cases
- `LLM_LOW_CONFIDENCE_THRESHOLD=0.65`
- `LLM_ENABLE_SARCASM_TRIGGER=true` (forces LLM on sarcasm cues like `/s`, `yeah right`)
- `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `LLM_MAX_OUTPUT_TOKENS`
- `LLM_INPUT_PRICE_PER_MILLION_TOKENS` / `LLM_OUTPUT_PRICE_PER_MILLION_TOKENS` (for runtime cost estimation in logs)

Behavior:

- base model runs first (deterministic or FinBERT)
- LLM is used as fallback on uncertain/sarcastic cases
- if LLM request fails, service falls back to base model result
- pull logs include per-subreddit LLM metrics (`llm_calls`, tokens, estimated `llm_cost_usd`)

### Proxy rotation (optional)

Set one or more outbound proxies:

- `REDDIT_PROXY_URLS_CSV=http://user:pass@proxy1:8080,http://user:pass@proxy2:8080`
- `REDDIT_PROXY_ROTATION_MODE=round_robin` (`random` also supported)
- `REDDIT_PROXY_FAILURE_COOLDOWN_SECONDS=180`
- `REDDIT_PROXY_INCLUDE_DIRECT_FALLBACK=true`

Notes:

- This improves resilience against temporary IP-specific throttling.
- It does **not** guarantee full 24h completeness because Reddit endpoint limits/ranking still apply.

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

- Top-20 daily listing sample introduces selection bias.
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
