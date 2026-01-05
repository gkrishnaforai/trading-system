# System UI  Go API  Python Worker  Redis  Postgres (Architecture)

## Purpose

This document is the single source of truth for how UI clients (React and Streamlit) interact with the backend services, how data flows through the system, and how Redis + Postgres are used to reduce latency and minimize calls to external market-data providers.

Use this document as context for any LLM-assisted code generation or architectural change requests.

## High-level principles (DRY / SOLID)

- **Single backend contract**: UI clients call **Go API only**. Streamlit is treated as an **admin/backoffice client**, React as the **product UI**.
- **Clean layering**:
  - Provider/network logic lives in provider clients (python-worker) or service clients (go-api).
  - Business logic lives in services.
  - DB access lives in repositories.
- **Cache-aside is default** for Redis usage, with careful TTLs and minimal invalidation complexity.
- **Postgres is the system of record**. Redis is an optimization layer.

## Components

### 1) React UI (product)
- **Web-first**: Next.js (App Router) is the primary product UI.
- Calls Go API REST endpoints (single backend contract).
- Uses client-side caching with TanStack Query (React Query) for UI responsiveness.
- Charts:
  - TradingView widgets for advanced charting
  - Recharts for dashboard summaries and lightweight visualizations

Mobile plan (not now):
- Expo React Native later (alerts + push notifications are the main mobile driver)
- Shared UI via Tamagui is optional; do not introduce it if it slows the web MVP

Web-only next steps:
- Add a single API base URL env var (`NEXT_PUBLIC_API_URL`) and a shared API client wrapper.
- Add TanStack Query with default retry/backoff policy aligned with server-side caching.
- Implement MVP pages:
  - Watchlists (CRUD + add/remove)
  - Portfolios (CRUD + holdings)
  - Earnings calendar (date-range views)
  - Stock blog pages (SEO-friendly routes)

### 2) Streamlit (admin/backoffice)
- Calls Go API REST endpoints.
- Used for:
  - operations (refreshes)
  - monitoring
  - diagnostics
  - backoffice workflows

### 3) Go API (core API gateway)
- **The single HTTP entrypoint** for all UI clients.
- Owns:
  - user/watchlist/portfolio CRUD
  - subscription gating (basic/pro/elite)
  - caching policy (Redis)
  - proxying to python-worker admin endpoints where appropriate

### 4) Python worker (data ingestion + AI/ML)
- Owns:
  - provider clients (Yahoo Finance, Massive, Alpha Vantage, etc.)
  - data refresh manager and ingestion workflows
  - persistence of ingested datasets into Postgres tables
- Exposes admin endpoints consumed by Go API admin proxy.

### 5) Postgres (system of record)
- Stores:
  - watchlists, portfolios, holdings
  - raw market data, indicators, fundamentals, earnings, news
  - refresh/audit state

### 6) Redis (performance + coordination)
- Used for:
  - Go API response caching
  - reducing repeated DB reads for hot queries
  - optional job/queue coordination (future)

## Network / request flows

### A) Normal product flow (React)

1. React calls Go API: `GET /api/v1/...`
2. Go API:
   - checks Redis cache (cache-aside)
   - on miss, queries Postgres (repositories)
   - optionally triggers python-worker refresh via proxy or refresh endpoints
   - returns response

### B) Admin flow (Streamlit)

Same as React, but it additionally uses admin endpoints:
- e.g. Go API proxies `/api/v1/admin/*` to python-worker `/admin/*`

### C) Data refresh flow

- Streamlit triggers refresh via Go API:
  - `POST /api/v1/admin/refresh` (proxy) or future typed endpoints
- Go API proxies to python-worker, python-worker:
  - calls provider clients
  - normalizes
  - writes to Postgres
  - updates refresh state

## Key API contracts (current)

### 1) Earnings calendar (admin)
- Go API -> python-worker proxy
  - `GET /api/v1/admin/earnings-calendar?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
  - `POST /api/v1/admin/earnings-calendar/refresh`
  - `POST /api/v1/admin/earnings-calendar/refresh-for-date`

### 2) Symbol scope resolve (UI helper)
- Go API native endpoint
  - `GET /api/v1/symbol-scope/resolve?user_id=...&watchlist_id=...&portfolio_id=...&subscription_level=elite`
- Returns a deduped list of symbols to drive other endpoints (earnings, overview, etc.).

## Redis caching (industry-standard)

### Pattern: Cache-aside (lazy loading)
- On read:
  1. check Redis
  2. if hit: return
  3. if miss: query DB, then set Redis with TTL

This is the most common pattern for read-heavy systems and is recommended by Redis and AWS guidance.

### What gets cached
- **Go API response objects** (JSON-serializable structs)
- **Symbol scope results** (watchlist/portfolio symbol lists)

### When Redis gets hydrated
- Lazily on cache misses (first request after startup)
- Optionally via prefetch during:
  - nightly batch
  - post-refresh hooks
  - UI warmup (admin)

### TTL guidance (starting point)
- **Symbol scope** (watchlist/portfolio membership): `30s120s`
  - membership changes are rare but must feel fresh
- **Earnings calendar window queries**: `30s5m`
  - earnings updates are not second-by-second
- **Quote-like data** (if added): `5s60s`
- **Fundamentals snapshots**: `6h24h`

### Invalidation guidance
- Prefer **TTL-based invalidation** for most reads.
- Use explicit invalidation only for:
  - watchlist item add/remove
  - holding add/remove

## Postgres usage

### Source of truth
- Postgres is always authoritative.
- Provider calls should write to Postgres; read endpoints should prefer Postgres over provider calls.

### Recommended DB indexes (examples)
- `earnings_calendar(earnings_date, symbol)`
- `watchlist_items(watchlist_id, stock_symbol)`
- `holdings(portfolio_id, stock_symbol)`

## Subscription gating

- Subscription tiers: `basic`, `pro`, `elite`
- Backend enforces gating.
- UI can assume elite for admin/demo, but backend remains authoritative.

## Operational concerns

### Timeouts
- UI -> Go API: 3060s
- Go API -> python-worker proxy: 3060s
- python-worker -> provider: provider-specific, with retries/backoff

### Observability
- Structured logs at each boundary:
  - request id
  - cache hit/miss
  - DB query timing
  - provider timing

---

## References
- Redis caching patterns (cache-aside, write-through, etc.): https://redis.io/solutions/caching/
- AWS caching patterns: https://docs.aws.amazon.com/whitepapers/latest/database-caching-strategies-using-redis/caching-patterns.html
- Redis cache invalidation concepts: https://redis.io/glossary/cache-invalidation/
