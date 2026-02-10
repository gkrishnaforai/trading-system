# Scheduling & Orchestration Design (Profiles + Runs)

## Goal

Provide an industry-standard, operator-friendly scheduling/orchestration model for:

- Data loads (prices, fundamentals, news, etc.)
- Derived computations (technical indicators, financial ratios)
- Stock technical/fundamental analysis (signal generation)
- Alerts (event-driven notifications)
- Portfolio balancing/rebalance recommendations

This document is written to be a stable reference that can be used by an LLM (and humans) to implement, extend, and evolve the scheduler.

## Current Architecture (Authoritative)

- **UI clients (Streamlit now, Next.js later)** call **Go API only**.
- **Go API** is the orchestrator/BFF:
  - Creates a durable `run_id`
  - Writes run + audit rows
  - Enqueues jobs into Redis Streams (one job per symbol)
  - Exposes run status/history for polling and operator UX
- **python-worker** is the executor:
  - Consumes jobs from Redis Streams
  - Executes refresh/analysis logic
  - Writes data to DB
  - Emits events/audits

This matches the pattern already implemented for data loads and job profiles.

## Why Profiles

A scheduler should trigger **intent**, not a long list of `data_types`.

A **profile** is a named configuration that the Go API resolves into:

- `data_types` (what to fetch/compute)
- optionally additional semantics (future): windows, lookbacks, concurrency caps, alert modes

Profiles:

- Keep scheduling DRY
- Make scheduler calls stable
- Allow safe evolution by changing profile definitions (not every scheduler client)

Go API already supports Job Profiles via:

- `GET /api/v1/admin/job-profiles`
- `POST /api/v1/portfolios/:portfolio_id/data-load` with `{ "profile": "..." }`

See also: `docs/REDIS_STREAMS_JOB_QUEUE.md`.

## Key Entities & Invariants

### `run_id`

A run is the durable unit of work. It is:

- created by Go API
- shared across every job/event/alert emitted for that run
- used for:
  - idempotency & retries
  - operator visibility
  - alert correlation

### Job execution semantics

- **At-least-once** delivery via Redis Streams
- Best-effort distributed lock per job
- Retry with backoff and a DLQ after max attempts
- Cancellation supported

## Data Types (Conceptual)

A `data_type` is a unit of refresh work for a symbol. Examples (not exhaustive):

- `price_current`
- `price_intraday_5m`
- `price_historical`
- `indicators`
- `fundamentals`
- `financial_ratios`
- `key_metrics_ttm`
- `financial_scores`
- `news`
- `earnings`

The scheduler does not need to know the full set. It should rely on profiles.

## Two Scheduler Profiles (Recommended)

You asked for profiles similar to the Data Load Run Tester approach.

### 1) Intraday Schedule (Market Hours)

**Intent**: Keep alerts and time-sensitive info fresh during market hours.

Recommended base profile:

- `intraday_alerts` (already defined in Go `job_profiles.go`)

Optional variant:

- `intraday_alerts_with_intraday_prices` (already defined)

Recommended schedule:

- Every 5-15 minutes during market hours

Recommended request shape (scheduler → Go API):

```bash
curl -s -X POST 'http://localhost:8000/api/v1/portfolios/<portfolio_id>/data-load' \
  -H 'Content-Type: application/json' \
  -d '{
    "symbols": ["AAPL", "MSFT"],
    "profile": "intraday_alerts_with_intraday_prices",
    "force": false
  }'
```

Notes:

- Intraday profile should prefer lightweight data types (price current/intraday, news, grades) and avoid heavy fundamentals recomputation.

### 2) Daily Schedule (EOD)

**Intent**: End-of-day refresh of daily OHLCV, recompute indicators, refresh slow-moving fundamentals, and generate daily signals.

Recommended base profile:

- `daily_analysis` (already defined in Go `job_profiles.go`)

Recommended schedule:

- Once per day after market close (+ buffer)

Recommended request shape:

```bash
curl -s -X POST 'http://localhost:8000/api/v1/portfolios/<portfolio_id>/data-load' \
  -H 'Content-Type: application/json' \
  -d '{
    "symbols": ["AAPL", "MSFT"],
    "profile": "daily_analysis",
    "force": false
  }'
```

Notes:

- This profile can be heavier and include recomputation (price_historical, indicators, earnings, fundamentals, ratios).

## Overrides (Composable)

The existing endpoint supports override lists:

- `include_data_types`
- `exclude_data_types`

This is the recommended mechanism for “scheduler variations” without defining many new profiles.

Example: daily run excluding heavy fundamentals (temporary):

```bash
curl -s -X POST 'http://localhost:8000/api/v1/portfolios/<portfolio_id>/data-load' \
  -H 'Content-Type: application/json' \
  -d '{
    "symbols": ["AAPL"],
    "profile": "daily_analysis",
    "exclude_data_types": ["fundamentals"],
    "force": false
  }'
```

## Extending Profiles Beyond Data Load (Signals + Portfolio Rebalance)

Today, the profile mechanism is implemented for **data-load jobs**.

Industry-standard next step is to introduce **analysis profiles** with the same pattern:

- `analysis_profile`: resolves to analysis steps (signals, reports, rebalance recommendations)
- results persisted with `run_id` correlation

### Proposed analysis profiles

- `daily_signals`
  - generate universal signals for each symbol/date
  - emit `signal_generated` events
  - evaluate alert rules (signal changes)

- `intraday_signals` (optional)
  - generate intraday signals (if supported)

- `weekly_rebalance`
  - compute portfolio rebalance recommendations
  - persist proposal + rationale
  - (optional) require user approval

### Proposed endpoint contracts (Go API)

These are recommended contracts for the scheduler to call. They keep the scheduler ignorant of details.

1) Start analysis run:

- `POST /api/v1/portfolios/:portfolio_id/analysis-run`

Payload:

```json
{
  "symbols": ["AAPL", "MSFT"],
  "profile": "daily_signals",
  "force": false,
  "target_date": "2026-02-08"
}
```

Response:

```json
{
  "success": true,
  "run_id": "<uuid>",
  "status": "running"
}
```

2) Poll run:

- `GET /api/v1/analysis/runs/:run_id`

3) Events:

- `GET /api/v1/analysis/runs/:run_id/events`

This mirrors the data-load run inspector pattern.

## Alerts: Event-Driven Standard

Avoid “poll and compare everywhere”. Prefer:

- analysis/data-load produces durable **events**
- alert evaluators consume events and decide notifications

Event examples:

- `signal_generated`
- `signal_changed`
- `price_spike`
- `grade_change`
- `rebalance_recommended`

All events should carry:

- `correlation_id = run_id`
- `symbol`
- `event_ts`
- `payload` (minimal, with pointers/ids for details)

## Scheduler Implementation Options

### Option A (recommended first): External scheduler calling Go API

- Docker: cron on host or a small scheduler container
- Kubernetes: CronJob
- Cloud: EventBridge / Cloud Scheduler

The scheduler only makes HTTP calls to Go API profile endpoints.

### Option B: Embedded scheduler in Go API

Possible, but requires leader-election / singleton guarantees to prevent duplicate schedules.

## Operational Requirements (Non-Negotiable)

- Single orchestrator for run creation (Go API)
- Durable run status and event logs
- Idempotent writes (upsert by keys)
- Retry with bounded attempts + DLQ
- Observability:
  - run summary
  - per-symbol events
  - last scheduler tick/health

## Suggested Initial Rollout Plan

1. Keep using existing Job Profiles for **data load** (`intraday_alerts*`, `daily_analysis`).
2. Add a minimal scheduler (cron/CronJob) that calls Go API to trigger those profiles for a given portfolio/watchlist.
3. Add “analysis profiles” next, using the same model.
4. Add portfolio rebalance recommendations as an analysis profile (`weekly_rebalance`).

## References

- `docs/REDIS_STREAMS_JOB_QUEUE.md`
- `docs/EOD_WORKFLOW_IMPLEMENTATION.md`
- Go: `go-api/internal/services/job_profiles.go`
- Streamlit: `streamlit-app/pages/18_Data_Load_Run_Tester.py`
