# Redis Streams Job Queue + Worker Architecture

## Purpose

Enable parallel, robust execution of portfolio data-load jobs using Redis Streams consumer groups, with industry-standard semantics:

- At-least-once delivery
- Visibility timeout / reclaim of stuck work
- Retries + dead-letter queue (DLQ)
- Idempotency + best-effort duplicate suppression
- Operator observability (without requiring manual intervention)

This module is used by the Go API (orchestrator/BFF) to enqueue work and by Python job-workers (executors) to consume and execute jobs.

## Components

- **Go API**
  - Creates/owns `run_id` (data ingestion run)
  - Enqueues one job per symbol into Redis Streams
  - Tracks run audit/status via DB + Redis counters
  - Exposes admin endpoints consumed by Streamlit (optional UX)

- **Redis (Streams)**
  - Primary job queue stream: `ts:jobs`
  - DLQ stream: `ts:jobs:dlq`
  - Consumer group: `python-workers`

- **Python job-worker container**
  - Entry point: `python-worker/app/workers/redis_stream_job_worker.py`
  - Consumes from stream group and executes refresh logic
  - Performs reclaim, retry/DLQ, idempotency checks, cancellation

## Horizontal Scaling (Multiple Workers)

This design supports **multiple worker replicas** consuming from the same Redis Streams consumer group (`python-workers`) for parallelism.

- Each worker instance uses a **unique consumer name**.
- Redis will distribute new messages across consumers in the group.
- Stuck/unacked work is recovered via `XAUTOCLAIM`.

### Docker Compose scaling

The `python-worker-job-worker` service is intentionally configured **without** a fixed `container_name` so Docker Compose can scale it.

Scale the number of worker replicas with:

```bash
docker-compose --profile workers up -d --scale python-worker-job-worker=3 python-worker-job-worker
```

Verify multiple replicas are running:

```bash
docker ps --filter name=python-worker-job-worker
```

Verify Redis sees multiple consumers:

```bash
docker exec -it trading-system-redis redis-cli XINFO CONSUMERS ts:jobs python-workers
```

## Redis Keys / Streams

### Streams

- **Job stream**: `ts:jobs`
  - Stream entries contain fields:
    - `job_id`: stable UUID for the logical job (per symbol/job)
    - `job_type`: currently `portfolio_data_load`
    - `payload`: JSON string (see schema)
    - `enqueued_at`: timestamp

- **DLQ stream**: `ts:jobs:dlq`
  - Used when `attempt >= max_attempts`
  - Fields include:
    - `job_id`
    - `source_msg_id`
    - `job_type`
    - `payload`
    - `error` (truncated)
    - `failed_at`

### Idempotency / locking

- `ts:job:done:{job_id}`
  - Set on success (TTL: `JOB_DONE_TTL_SECONDS`, default 7 days)
  - If present, duplicate deliveries are immediately `XACK`'d.

- `ts:job:lock:{job_id}`
  - Best-effort distributed lock (TTL: `JOB_LOCK_TTL_SECONDS`, default 30 minutes)
  - Prevents concurrent execution of the same logical job across workers.

### Run-level counters

- `ts:run:remaining:{run_id}`
  - Remaining job count. Decremented once per logical job completion.

- `ts:run:has_failures:{run_id}`
  - Flag set if any job fails.

### Worker health (lightweight metrics)

- `ts:jobs:worker:health` (Redis hash)
  - Updated periodically by worker
  - Contains:
    - `ts` (UTC)
    - `consumer`
    - `stream`
    - `group`
    - `reclaimed`
    - `errors`
    - `dlq`
    - `claim_errors`

## Job Payload Schema

`payload` is JSON for `DataLoadJobPayload`:

```json
{
  "run_id": "<uuid>",
  "portfolio_id": "<uuid or null>",
  "symbol": "CRWD",
  "data_types": ["indicators", "price_current", "price_targets"],
  "force": true,
  "attempt": 1,
  "max_attempts": 3
}
```

## Job Profiles (DRY data-type selection)

The Go API supports **job profiles** so clients can request a high-level intent (e.g., intraday alerts) instead of manually listing every `data_type`.

Profiles are resolved by the Go API into a concrete `data_types` list, then one job per symbol is enqueued into Redis Streams.

### Discover available profiles

Go API:

```bash
curl -s 'http://localhost:8000/api/v1/admin/job-profiles' | jq
```

This returns a map of `profile -> data_types`.

### Enqueue using a profile

```bash
curl -s -X POST 'http://localhost:8000/api/v1/portfolios/<portfolio_id>/data-load' \
  -H 'Content-Type: application/json' \
  -d '{
    "symbols": ["AAPL", "MSFT"],
    "profile": "intraday_alerts",
    "force": false
  }' | jq
```

### Composable overrides: include/exclude

You can extend or trim a profile using overrides. This keeps the system DRY while still allowing customization.

Rules:

- `exclude_data_types` removes items from the resolved base list.
- `include_data_types` adds items (unless excluded).
- Duplicates are removed (best-effort).

```bash
curl -s -X POST 'http://localhost:8000/api/v1/portfolios/<portfolio_id>/data-load' \
  -H 'Content-Type: application/json' \
  -d '{
    "symbols": ["AAPL"],
    "profile": "intraday_alerts",
    "include_data_types": ["earnings"],
    "exclude_data_types": ["news"],
    "force": false
  }' | jq
```

### Manual mode (advanced)

If you prefer explicit control, you can still provide `data_types` directly:

```bash
curl -s -X POST 'http://localhost:8000/api/v1/portfolios/<portfolio_id>/data-load' \
  -H 'Content-Type: application/json' \
  -d '{
    "symbols": ["AAPL"],
    "data_types": ["price_current", "news"],
    "force": false
  }' | jq
```

## Normal Flow (Happy Path)

1. **Go API** validates/sanitizes symbols and creates a `run_id`.
2. Go API enqueues one stream entry per symbol into `ts:jobs`.
3. **Python job-worker** runs `XREADGROUP group=python-workers streams={ts:jobs: ">"}`.
4. For each message:
   - Parse payload
   - Check cancellation
   - Idempotency checks:
     - If `ts:job:done:{job_id}` exists, `XACK` and exit
     - Try lock `ts:job:lock:{job_id}` (best-effort)
   - Execute refresh
   - On success:
     - `XACK`
     - Set `ts:job:done:{job_id}`
     - Release lock
     - Decrement `ts:run:remaining:{run_id}` exactly once
     - If remaining reaches 0, mark run finished (success/failed)

## Failure / Exception Handling

### 1) Worker crash / restart mid-job (stuck pending)

Redis Streams consumer groups keep unacked messages in the PEL (pending entries list).

**Recovery:** worker periodically reclaims stale pending messages using `XAUTOCLAIM`:

- Parameters:
  - `JOB_PENDING_MIN_IDLE_MS` (default 60000)
  - `JOB_PENDING_CLAIM_BATCH` (default 10)
  - `JOB_PENDING_CLAIM_INTERVAL_SECONDS` (default 5)

Claimed messages are processed the same as new messages.

### 2) Redis DNS / connection instability (startup churn)

Worker performs:

- `wait_for_redis()` on startup: ping with exponential backoff
- Redis client recreation on common DNS / connection errors
- Throttled loop error logs (`JOB_LOOP_ERROR_LOG_INTERVAL_SECONDS`)

This prevents log spam and allows automatic recovery once Docker networking stabilizes.

### 3) Job execution failure

On exception during processing:

- `XACK` the current message (avoid stuck PEL)
- Mark run as having failures (`ts:run:has_failures:{run_id}`)
- If `attempt < max_attempts`:
  - Re-enqueue the job with incremented `attempt` (backoff)
  - Keep the same `job_id` to preserve idempotency
- Else:
  - Send to DLQ stream `ts:jobs:dlq`

### 4) Lock not acquired (duplicate / concurrent execution)

If the worker cannot acquire `ts:job:lock:{job_id}`:

- `XACK` the message (avoid PEL churn)
- Re-enqueue the same `job_id` + same payload with a defer marker:
  - `deferred_reason=lock_not_acquired`

This keeps the queue healthy under contention and relies on idempotency to prevent duplicates.

### 5) Cancellation

Worker checks DB for `cancel_requested_at` on the `run_id`.

If cancel is requested:

- Log audit event `job_canceled`
- `XACK` the message
- Decrement remaining (and finish run if remaining becomes 0)

## Delivery Semantics

- **At-least-once**: a job may be executed more than once due to crash/reclaim.
- **Idempotency**:
  - `ts:job:done:{job_id}` prevents repeated side effects after success.
  - Lock reduces concurrent duplication.

## Operational Observability / Alerting

This system is intended to self-heal without manual intervention.

Recommended alert conditions:

- `XPENDING ts:jobs python-workers` count > 0 for > N minutes
- Oldest pending idle time exceeds a threshold (e.g., > 5–10 minutes)
- DLQ growth rate above baseline
- `claim_errors` increasing (from `ts:jobs:worker:health`)

Streamlit UI can visualize these metrics, but recovery is automatic via reclaim/retry/DLQ.

## Runbook (Redis CLI)

All commands below assume you can run `redis-cli` inside the Redis container:

```bash
docker exec -it trading-system-redis redis-cli
```

### Quick health checks

```redis
XINFO STREAM ts:jobs
XINFO GROUPS ts:jobs
XINFO CONSUMERS ts:jobs python-workers
XPENDING ts:jobs python-workers
```

Interpretation:

- `lag=0` in `XINFO GROUPS` means no undispatched backlog (new messages are caught up).
- `XPENDING > 0` means messages are stuck/in-flight in the PEL.

### Inspect pending messages (who owns them, idle time, delivery count)

```redis
XPENDING ts:jobs python-workers - + 10
XPENDING ts:jobs python-workers - + 10 <consumer-name>
```

### Inspect a specific stream entry (message payload)

```redis
XRANGE ts:jobs <msg-id> <msg-id>
```

### Inspect recent messages (tail)

```redis
XREVRANGE ts:jobs + - COUNT 20
XREVRANGE ts:jobs:dlq + - COUNT 20
```

### Manual reclaim (break-glass)

In normal operation the worker does this automatically. For emergency recovery:

```redis
XAUTOCLAIM ts:jobs python-workers <consumer-name> 60000 0-0 COUNT 10
```

Notes:

- `min-idle-time` is in milliseconds (example above: 60s).
- Claimed messages must still be processed and `XACK`'d by a live worker.

### Inspect DLQ entries

```redis
XINFO STREAM ts:jobs:dlq
XREVRANGE ts:jobs:dlq + - COUNT 20
```

### Worker health snapshot

```redis
HGETALL ts:jobs:worker:health
```

Useful fields:

- `reclaimed`: count of messages reclaimed via `XAUTOCLAIM`
- `claim_errors`: failures encountered while reclaiming
- `errors`: job execution failures (worker-side)
- `dlq`: jobs sent to DLQ

## Relevant Files

- Go API:
  - `go-api/internal/handlers/data_load_handler.go` (enqueue + symbol validation)
  - `go-api/internal/handlers/job_queue_admin_handler.go` (status endpoint)
  - `go-api/cmd/api/main.go` (route wiring)

- Python worker:
  - `python-worker/app/workers/redis_stream_job_worker.py` (consumer/reclaim/retry/DLQ/idempotency)

- Docker:
  - `docker-compose.yml` (job-worker runs as separate service `python-worker-job-worker`)


1) Stop it (if running)
bash
docker stop trading-system-python-worker-job-worker-2
2) Remove it
bash
docker rm trading-system-python-worker-job-worker-2
3) Re-run scale
bash
docker-compose --profile workers up -d --scale python-worker-job-worker=3 python-worker-job-worker
Verify it worked
Check containers
bash
docker ps --filter name=python-worker-job-worker --format "table {{.Names}}\t{{.Status}}"
Check Redis sees multiple consumers
bash
docker exec -it trading-system-redis redis-cli XINFO CONSUMERS ts:jobs python-workers



## Notes for Future Enhancements

- Add hard execution timeouts per job and move to DLQ on timeout.
- Add structured Prometheus metrics export in Go API.
- Add per-run summary aggregation and correlation IDs in logs.
- Add concurrency controls (multiple consumers in same group) and optional per-provider rate limiting.
