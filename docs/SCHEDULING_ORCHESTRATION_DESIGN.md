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

## Operational Commands & Scheduler Management

This section provides practical commands for managing schedules and scheduler operations in production.

### Portfolio Schedule Management (Go API)

#### View All Schedules
```bash
# Get overview of all schedules
curl -s http://localhost:8000/api/v1/portfolio-schedules/status/overview | jq .

# List all schedules with filtering
curl -s http://localhost:8000/api/v1/portfolio-schedules/list | jq '.schedules[]'

# List only active schedules
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?status=active | jq '.schedules[]'

# List schedules for specific portfolio
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?portfolio_id=<portfolio_id> | jq '.schedules[]'
```

#### Disable All Schedules (Emergency Stop)
```bash
# Disable all active portfolio schedules
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?status=active | \
jq -r '.schedules[] | .id' | \
while read schedule_id; do
    echo "Disabling schedule: $schedule_id"
    curl -X POST http://localhost:8000/api/v1/portfolio-schedules/$schedule_id/toggle
    echo ""
done

# One-liner version
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?status=active | \
jq -r '.schedules[] | .id' | \
xargs -I {} curl -X POST http://localhost:8000/api/v1/portfolio-schedules/{}/toggle
```

#### Enable All Schedules
```bash
# Enable all paused portfolio schedules
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?status=paused | \
jq -r '.schedules[] | .id' | \
while read schedule_id; do
    echo "Enabling schedule: $schedule_id"
    curl -X POST http://localhost:8000/api/v1/portfolio-schedules/$schedule_id/toggle
    echo ""
done
```

#### Delete All Schedules (Destructive)
```bash
# ⚠️ WARNING: This will delete all schedules permanently
curl -s http://localhost:8000/api/v1/portfolio-schedules/list | \
jq -r '.schedules[] | .id' | \
while read schedule_id; do
    echo "Deleting schedule: $schedule_id"
    curl -X DELETE http://localhost:8000/api/v1/portfolio-schedules/$schedule_id
    echo ""
done
```

#### Individual Schedule Operations
```bash
# Toggle specific schedule (enable/disable)
curl -X POST http://localhost:8000/api/v1/portfolio-schedules/{schedule_id}/toggle

# Update specific schedule
curl -X PUT http://localhost:8000/api/v1/portfolio-schedules/{schedule_id} \
  -H 'Content-Type: application/json' \
  -d '{
    "schedule_type": "daily",
    "schedule_time": "09:00",
    "is_active": true,
    "notification_preferences": {
      "email": true,
      "push": false
    }
  }'

# Delete specific schedule
curl -X DELETE http://localhost:8000/api/v1/portfolio-schedules/{schedule_id}

# Get schedule details
curl -s http://localhost:8000/api/v1/portfolio-schedules/{schedule_id} | jq .
```

### System-Wide Scheduler Control

#### Check Scheduler Health
```bash
# Check portfolio scheduler status
curl -s http://localhost:8000/api/v1/portfolio-schedules/status/overview | jq '.scheduler_running'

# Check Python worker scheduler (local debugging)
curl -s http://localhost:8001/admin/scheduler/status | jq .
```

#### Manual Schedule Triggers
```bash
# Trigger data load for portfolio using profile
curl -s -X POST 'http://localhost:8000/api/v1/portfolios/<portfolio_id>/data-load' \
  -H 'Content-Type: application/json' \
  -d '{
    "symbols": ["AAPL", "MSFT"],
    "profile": "daily_analysis",
    "force": false
  }'

# Trigger analysis run (when implemented)
curl -s -X POST 'http://localhost:8000/api/v1/portfolios/<portfolio_id>/analysis-run' \
  -H 'Content-Type: application/json' \
  -d '{
    "symbols": ["AAPL", "MSFT"],
    "profile": "daily_signals",
    "force": false,
    "target_date": "2026-02-18"
  }'
```

### Production Scripts

#### Complete Emergency Stop Script
```bash
#!/bin/bash
# emergency_stop_schedules.sh

echo "🛑 EMERGENCY: Disabling All Scheduled Runs..."

# 1. Disable all portfolio schedules
echo "Disabling portfolio schedules..."
active_schedules=$(curl -s http://localhost:8000/api/v1/portfolio-schedules/list?status=active | \
jq -r '.schedules[] | .id' 2>/dev/null)

if [ ! -z "$active_schedules" ]; then
    echo "$active_schedules" | while read schedule_id; do
        if [ ! -z "$schedule_id" ]; then
            echo "  - Disabling portfolio schedule: $schedule_id"
            curl -X POST http://localhost:8000/api/v1/portfolio-schedules/$schedule_id/toggle >/dev/null 2>&1
        fi
    done
else
    echo "  No active portfolio schedules found"
fi

# 2. Check final status
echo ""
echo "📊 Final Status:"
curl -s http://localhost:8000/api/v1/portfolio-schedules/status/overview | jq '.total_schedules, .active_schedules, .paused_schedules'

echo ""
echo "✅ All scheduled runs have been disabled!"
echo "🔍 Verify with: curl -s http://localhost:8000/api/v1/portfolio-schedules/status/overview | jq '.active_schedules'"
```

#### Scheduler Health Check Script
```bash
#!/bin/bash
# scheduler_health_check.sh

echo "🔍 Scheduler Health Check..."

# Check Go API scheduler status
echo "Go API Scheduler Status:"
go_status=$(curl -s http://localhost:8000/api/v1/portfolio-schedules/status/overview 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "$go_status" | jq '.scheduler_running, .total_schedules, .active_schedules, .paused_schedules'
else
    echo "❌ Go API not responding"
fi

echo ""

# Check Python worker scheduler (if accessible)
echo "Python Worker Scheduler Status:"
py_status=$(curl -s http://localhost:8001/admin/scheduler/status 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "$py_status" | jq .
else
    echo "❌ Python Worker not responding or endpoint not available"
fi

echo ""

# Check upcoming runs
echo "Upcoming Runs (next 24h):"
curl -s http://localhost:8000/api/v1/portfolio-schedules/status/overview | jq '.upcoming_runs'
```

#### Bulk Schedule Creation Script
```bash
#!/bin/bash
# create_portfolio_schedules.sh

PORTFOLIO_ID=$1
if [ -z "$PORTFOLIO_ID" ]; then
    echo "Usage: $0 <portfolio_id>"
    exit 1
fi

echo "📅 Creating Standard Schedules for Portfolio: $PORTFOLIO_ID"

# Create daily analysis schedule (9:00 AM)
echo "Creating daily analysis schedule..."
curl -s -X POST http://localhost:8000/api/v1/portfolio-schedules/ \
  -H 'Content-Type: application/json' \
  -d '{
    "portfolio_id": "'$PORTFOLIO_ID'",
    "schedule_type": "daily",
    "schedule_time": "09:00",
    "notification_preferences": {
      "email": true,
      "push": false
    }
  }' | jq .

# Create weekly analysis schedule (Monday 9:00 AM)
echo "Creating weekly analysis schedule..."
curl -s -X POST http://localhost:8000/api/v1/portfolio-schedules/ \
  -H 'Content-Type: application/json' \
  -d '{
    "portfolio_id": "'$PORTFOLIO_ID'",
    "schedule_type": "weekly",
    "schedule_time": "09:00",
    "schedule_day": 1,
    "notification_preferences": {
      "email": true,
      "push": false
    }
  }' | jq .

echo ""
echo "✅ Standard schedules created!"
echo "🔍 Verify with: curl -s http://localhost:8000/api/v1/portfolio-schedules/list?portfolio_id=$PORTFOLIO_ID | jq '.schedules[]'"
```

### Monitoring & Observability

#### Real-time Schedule Monitoring
```bash
# Watch schedule status changes
watch -n 30 'curl -s http://localhost:8000/api/v1/portfolio-schedules/status/overview | jq ".active_schedules, .paused_schedules, .upcoming_runs"'

# Monitor specific portfolio schedules
watch -n 60 'curl -s http://localhost:8000/api/v1/portfolio-schedules/list?portfolio_id=<portfolio_id> | jq ".schedules[] | {id: .id, type: .schedule_type, active: .is_active, next_run: .next_run}"'
```

#### Audit & Troubleshooting
```bash
# Get schedule run history (when implemented)
curl -s "http://localhost:8000/api/v1/portfolio-schedules/{schedule_id}/runs?limit=10" | jq '.runs[]'

# Check for failed schedules
curl -s http://localhost:8000/api/v1/portfolio-schedules/list | \
jq '.schedules[] | select(.job_status == "error") | {id: .id, type: .schedule_type, last_error: .last_error}'
```

### Quick Reference Commands

| Action | Command |
|--------|---------|
| **List all schedules** | `curl -s http://localhost:8000/api/v1/portfolio-schedules/list | jq .` |
| **Check scheduler status** | `curl -s http://localhost:8000/api/v1/portfolio-schedules/status/overview | jq .` |
| **Disable all schedules** | `curl -s .../list?status=active \| jq -r '.schedules[] | .id' \| xargs -I {} curl -X POST .../{}/toggle` |
| **Enable all schedules** | `curl -s .../list?status=paused \| jq -r '.schedules[] | .id' \| xargs -I {} curl -X POST .../{}/toggle` |
| **Create daily schedule** | `curl -X POST .../portfolio-schedules/ -d '{"portfolio_id":"...", "schedule_type":"daily", "schedule_time":"09:00"}'` |
| **Toggle schedule** | `curl -X POST .../portfolio-schedules/{id}/toggle` |
| **Delete schedule** | `curl -X DELETE .../portfolio-schedules/{id}` |

### Environment-Specific Endpoints

| Environment | Go API Base | Python Worker Base |
|-------------|-------------|-------------------|
| **Local** | `http://localhost:8000` | `http://localhost:8001` |
| **Development** | `https://dev-api.trading-system.com` | `https://dev-worker.trading-system.com` |
| **Production** | `https://api.trading-system.com` | `https://worker.trading-system.com` |

Replace base URLs in commands above for different environments.

## User Guide: Schedule & Alert Management

This section provides a complete user guide for managing schedules and alerts using curl commands.

### Quick Start: Check System Status

```bash
# Check what's currently running
curl -s -X POST "http://localhost:8000/api/v1/scheduler/tick?limit=25" | jq .

# List all system schedules
curl -s http://localhost:8000/api/v1/schedules | jq '.schedules[] | {profile: .profile, enabled: .enabled, next_run: .next_run_at}'

# List all portfolio schedules
curl -s http://localhost:8000/api/v1/portfolio-schedules/status/overview | jq .
```

### System Schedule Management (Data Loading)

These schedules handle market data, fundamentals, news, and other system-wide data loading.

#### View All System Schedules
```bash
# List all schedules with full details
curl -s http://localhost:8000/api/v1/schedules | jq '.schedules[]'

# List only active schedules
curl -s http://localhost:8000/api/v1/schedules | jq '.schedules[] | select(.enabled == true)'

# List only disabled schedules
curl -s http://localhost:8000/api/v1/schedules | jq '.schedules[] | select(.enabled == false)'

# Get specific schedule details
curl -s http://localhost:8000/api/v1/schedules/{schedule_id} | jq .
```

#### Start/Stop System Schedules
```bash
# STOP a schedule (disable)
curl -X PATCH http://localhost:8000/api/v1/schedules/{schedule_id} \
  -H 'Content-Type: application/json' \
  -d '{"enabled": false}'

# START a schedule (enable)
curl -X PATCH http://localhost:8000/api/v1/schedules/{schedule_id} \
  -H 'Content-Type: application/json' \
  -d '{"enabled": true}'

# STOP all active schedules
curl -s http://localhost:8000/api/v1/schedules | \
jq -r '.schedules[] | select(.enabled == true) | .schedule_id' | \
while read schedule_id; do
    echo "Stopping schedule: $schedule_id"
    curl -X PATCH http://localhost:8000/api/v1/schedules/$schedule_id \
      -H 'Content-Type: application/json' \
      -d '{"enabled": false}'
    echo ""
done

# START all disabled schedules
curl -s http://localhost:8000/api/v1/schedules | \
jq -r '.schedules[] | select(.enabled == false) | .schedule_id' | \
while read schedule_id; do
    echo "Starting schedule: $schedule_id"
    curl -X PATCH http://localhost:8000/api/v1/schedules/$schedule_id \
      -H 'Content-Type: application/json' \
      -d '{"enabled": true}'
    echo ""
done
```

#### Immediate Schedule Execution
```bash
# Run a schedule immediately (ignores next_run time)
curl -X POST http://localhost:8000/api/v1/schedules/{schedule_id}/run-now

# Make a schedule due now (will run on next tick)
curl -X POST http://localhost:8000/api/v1/schedules/{schedule_id}/make-due-now
```

#### Delete System Schedules
```bash
# Delete a specific schedule (permanent)
curl -X DELETE http://localhost:8000/api/v1/schedules/{schedule_id}

# ⚠️ DANGER: Delete ALL schedules
curl -s http://localhost:8000/api/v1/schedules | \
jq -r '.schedules[] | .schedule_id' | \
while read schedule_id; do
    echo "Deleting schedule: $schedule_id"
    curl -X DELETE http://localhost:8000/api/v1/schedules/$schedule_id
    echo ""
done
```

#### Update Schedule Configuration
```bash
# Update schedule time/cron expression
curl -X PATCH http://localhost:8000/api/v1/schedules/{schedule_id} \
  -H 'Content-Type: application/json' \
  -d '{
    "cron_expression": "0 9 * * 1-5",
    "timezone": "America/New_York"
  }'

# Update schedule configuration
curl -X PATCH http://localhost:8000/api/v1/schedules/{schedule_id} \
  -H 'Content-Type: application/json' \
  -d '{
    "config": {
      "symbols": ["AAPL", "MSFT", "GOOGL"],
      "force": false
    }
  }'
```

### Portfolio Schedule Management (Analysis)

These schedules handle portfolio-specific analysis, signals, and rebalancing.

#### View Portfolio Schedules
```bash
# Get portfolio schedule overview
curl -s http://localhost:8000/api/v1/portfolio-schedules/status/overview | jq .

# List all portfolio schedules
curl -s http://localhost:8000/api/v1/portfolio-schedules/list | jq '.schedules[]'

# List schedules for specific portfolio
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?portfolio_id={portfolio_id} | jq '.schedules[]'

# List only active portfolio schedules
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?status=active | jq '.schedules[]'

# List only paused portfolio schedules
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?status=paused | jq '.schedules[]'
```

#### Start/Stop Portfolio Schedules
```bash
# TOGGLE a portfolio schedule (enable/disable)
curl -X POST http://localhost:8000/api/v1/portfolio-schedules/{schedule_id}/toggle

# STOP all active portfolio schedules
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?status=active | \
jq -r '.schedules[] | .id' | \
while read schedule_id; do
    echo "Stopping portfolio schedule: $schedule_id"
    curl -X POST http://localhost:8000/api/v1/portfolio-schedules/$schedule_id/toggle
    echo ""
done

# START all paused portfolio schedules
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?status=paused | \
jq -r '.schedules[] | .id' | \
while read schedule_id; do
    echo "Starting portfolio schedule: $schedule_id"
    curl -X POST http://localhost:8000/api/v1/portfolio-schedules/$schedule_id/toggle
    echo ""
done
```

#### Create Portfolio Schedules
```bash
# Create daily analysis schedule
curl -X POST http://localhost:8000/api/v1/portfolio-schedules/ \
  -H 'Content-Type: application/json' \
  -d '{
    "portfolio_id": "your-portfolio-id",
    "schedule_type": "daily",
    "schedule_time": "09:00",
    "notification_preferences": {
      "email": true,
      "push": false
    }
  }'

# Create weekly analysis schedule
curl -X POST http://localhost:8000/api/v1/portfolio-schedules/ \
  -H 'Content-Type: application/json' \
  -d '{
    "portfolio_id": "your-portfolio-id",
    "schedule_type": "weekly",
    "schedule_time": "09:00",
    "schedule_day": 1,
    "notification_preferences": {
      "email": true,
      "push": false
    }
  }'

# Create monthly analysis schedule
curl -X POST http://localhost:8000/api/v1/portfolio-schedules/ \
  -H 'Content-Type: application/json' \
  -d '{
    "portfolio_id": "your-portfolio-id",
    "schedule_type": "monthly",
    "schedule_time": "09:00",
    "schedule_day": 1,
    "notification_preferences": {
      "email": true,
      "push": false
    }
  }'
```

#### Update Portfolio Schedules
```bash
# Update portfolio schedule
curl -X PUT http://localhost:8000/api/v1/portfolio-schedules/{schedule_id} \
  -H 'Content-Type: application/json' \
  -d '{
    "schedule_type": "daily",
    "schedule_time": "10:00",
    "notification_preferences": {
      "email": true,
      "push": true
    }
  }'
```

#### Delete Portfolio Schedules
```bash
# Delete specific portfolio schedule
curl -X DELETE http://localhost:8000/api/v1/portfolio-schedules/{schedule_id}

# Delete all portfolio schedules for a portfolio
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?portfolio_id={portfolio_id} | \
jq -r '.schedules[] | .id' | \
while read schedule_id; do
    echo "Deleting portfolio schedule: $schedule_id"
    curl -X DELETE http://localhost:8000/api/v1/portfolio-schedules/$schedule_id
    echo ""
done
```

### Alert Management

Alerts are generated based on schedule runs and data changes. You can monitor and manage alerts through the API.

#### View Recent Alerts
```bash
# Get recent alerts (when endpoint is available)
curl -s http://localhost:8000/api/v1/alerts/recent | jq '.alerts[]'

# Get alerts for specific symbol
curl -s http://localhost:8000/api/v1/alerts/symbol/{symbol} | jq '.alerts[]'

# Get alerts for specific portfolio
curl -s http://localhost:8000/api/v1/alerts/portfolio/{portfolio_id} | jq '.alerts[]'
```

#### Alert Configuration
```bash
# Get alert configurations
curl -s http://localhost:8000/api/v1/alerts/configurations | jq '.configurations[]'

# Update alert preferences
curl -X PUT http://localhost:8000/api/v1/alerts/preferences \
  -H 'Content-Type: application/json' \
  -d '{
    "email_enabled": true,
    "push_enabled": false,
    "alert_types": ["price_change", "grade_change", "signal_change"]
  }'
```

### Monitoring & Troubleshooting

#### Real-time Monitoring
```bash
# Watch scheduler activity in real-time
watch -n 30 'curl -s -X POST http://localhost:8000/api/v1/scheduler/tick?limit=25 | jq ".processed, .triggered, .failed"'

# Watch schedule status changes
watch -n 60 'curl -s http://localhost:8000/api/v1/schedules | jq ".schedules[] | select(.enabled == true) | {profile: .profile, next_run: .next_run_at}"'

# Watch portfolio schedule activity
watch -n 60 'curl -s http://localhost:8000/api/v1/portfolio-schedules/status/overview | jq ".active_schedules, .paused_schedules"'
```

#### Check Schedule Run History
```bash
# Get run history for system schedule
curl -s http://localhost:8000/api/v1/schedules/{schedule_id}/runs?limit=10 | jq '.runs[]'

# Get detailed run information
curl -s http://localhost:8000/api/v1/runs/{run_id} | jq .

# Get events for a specific run
curl -s http://localhost:8000/api/v1/runs/{run_id}/events | jq '.events[]'
```

#### Health Checks
```bash
# Check scheduler health
curl -s -X POST http://localhost:8000/api/v1/scheduler/tick?limit=1 | jq '.success'

# Check Go API health
curl -s http://localhost:8000/health | jq .

# Check Python Worker health
curl -s http://localhost:8001/health | jq .
```

### Emergency Procedures

#### Complete System Stop
```bash
#!/bin/bash
# emergency_stop_all.sh

echo "🛑 EMERGENCY: Stopping ALL scheduled activity..."

# 1. Stop all system schedules
echo "Stopping system schedules..."
curl -s http://localhost:8000/api/v1/schedules | \
jq -r '.schedules[] | select(.enabled == true) | .schedule_id' | \
while read schedule_id; do
    echo "  - Stopping system schedule: $schedule_id"
    curl -X PATCH http://localhost:8000/api/v1/schedules/$schedule_id \
      -H 'Content-Type: application/json' \
      -d '{"enabled": false}' >/dev/null 2>&1
done

# 2. Stop all portfolio schedules
echo "Stopping portfolio schedules..."
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?status=active | \
jq -r '.schedules[] | .id' | \
while read schedule_id; do
    echo "  - Stopping portfolio schedule: $schedule_id"
    curl -X POST http://localhost:8000/api/v1/portfolio-schedules/$schedule_id/toggle >/dev/null 2>&1
done

# 3. Verify everything is stopped
echo ""
echo "📊 Final Status:"
echo "System schedules active:"
curl -s http://localhost:8000/api/v1/schedules | jq '.schedules[] | select(.enabled == true) | length'
echo "Portfolio schedules active:"
curl -s http://localhost:8000/api/v1/portfolio-schedules/status/overview | jq '.active_schedules'

echo ""
echo "✅ All scheduled activity has been stopped!"
```

#### Complete System Start
```bash
#!/bin/bash
# emergency_start_all.sh

echo "🚀 EMERGENCY: Starting ALL scheduled activity..."

# 1. Start all disabled system schedules
echo "Starting system schedules..."
curl -s http://localhost:8000/api/v1/schedules | \
jq -r '.schedules[] | select(.enabled == false) | .schedule_id' | \
while read schedule_id; do
    echo "  - Starting system schedule: $schedule_id"
    curl -X PATCH http://localhost:8000/api/v1/schedules/$schedule_id \
      -H 'Content-Type: application/json' \
      -d '{"enabled": true}' >/dev/null 2>&1
done

# 2. Start all paused portfolio schedules
echo "Starting portfolio schedules..."
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?status=paused | \
jq -r '.schedules[] | .id' | \
while read schedule_id; do
    echo "  - Starting portfolio schedule: $schedule_id"
    curl -X POST http://localhost:8000/api/v1/portfolio-schedules/$schedule_id/toggle >/dev/null 2>&1
done

# 3. Verify everything is started
echo ""
echo "📊 Final Status:"
echo "System schedules active:"
curl -s http://localhost:8000/api/v1/schedules | jq '.schedules[] | select(.enabled == true) | length'
echo "Portfolio schedules active:"
curl -s http://localhost:8000/api/v1/portfolio-schedules/status/overview | jq '.active_schedules'

echo ""
echo "✅ All scheduled activity has been started!"
```

### Common Use Cases

#### "I want to stop all data loading for maintenance"
```bash
# Stop all system data loading schedules
curl -s http://localhost:8000/api/v1/schedules | \
jq -r '.schedules[] | select(.enabled == true) | .schedule_id' | \
while read schedule_id; do
    curl -X PATCH http://localhost:8000/api/v1/schedules/$schedule_id \
      -H 'Content-Type: application/json' \
      -d '{"enabled": false}'
done
```

#### "I want to pause portfolio analysis but keep data loading"
```bash
# Stop only portfolio schedules (keep system schedules running)
curl -s http://localhost:8000/api/v1/portfolio-schedules/list?status=active | \
jq -r '.schedules[] | .id' | \
while read schedule_id; do
    curl -X POST http://localhost:8000/api/v1/portfolio-schedules/$schedule_id/toggle
done
```

#### "I want to run a specific schedule right now"
```bash
# Run system schedule immediately
curl -X POST http://localhost:8000/api/v1/schedules/{schedule_id}/run-now

# Check the run status
curl -s http://localhost:8000/api/v1/runs/{run_id} | jq '.status'
```

#### "I want to see what's supposed to run today"
```bash
# Get today's schedule overview
curl -s http://localhost:8000/api/v1/schedules | \
jq '.schedules[] | select(.enabled == true) | {profile: .profile, next_run: .next_run_at, cron: .cron_expression}'

# Get portfolio schedules for today
curl -s http://localhost:8000/api/v1/portfolio-schedules/list | \
jq '.schedules[] | select(.is_active == true) | {schedule_type: .schedule_type, next_run: .next_run}'
```

### Quick Reference Card

| Action | System Schedules | Portfolio Schedules |
|--------|------------------|-------------------|
| **List All** | `curl -s .../schedules \| jq .` | `curl -s .../portfolio-schedules/list \| jq .` |
| **List Active** | `jq 'select(.enabled == true)'` | `?status=active` |
| **Start/Stop** | `PATCH .../schedules/{id} {"enabled": true\|false}` | `POST .../portfolio-schedules/{id}/toggle` |
| **Run Now** | `POST .../schedules/{id}/run-now` | Not available |
| **Delete** | `DELETE .../schedules/{id}` | `DELETE .../portfolio-schedules/{id}` |
| **Create** | `POST .../schedules` | `POST .../portfolio-schedules/` |
| **Update** | `PATCH .../schedules/{id}` | `PUT .../portfolio-schedules/{id}` |

### Environment Variables

```bash
# For different environments
export GO_API_URL="http://localhost:8000"  # Local
# export GO_API_URL="https://dev-api.trading-system.com"  # Dev
# export GO_API_URL="https://api.trading-system.com"  # Production

# Use in commands
curl -s ${GO_API_URL}/api/v1/schedules | jq .
```

## References

- `docs/REDIS_STREAMS_JOB_QUEUE.md`
- `docs/EOD_WORKFLOW_IMPLEMENTATION.md`
- Go: `go-api/internal/services/job_profiles.go`
