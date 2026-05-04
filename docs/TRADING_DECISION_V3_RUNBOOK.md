# Trading Decision V3 Runbook

This runbook contains copy/paste commands to:

- Refresh portfolio data via the Go API (job-queue based, non-blocking)
- Generate Trading Decision V3 decisions on-demand
- Inspect decisions (latest by symbol and history by date)

## Conventions

- Go API base URL: `http://127.0.0.1:8000`
- Python Worker base URL (local debug): `http://127.0.0.1:8001`
- `PORTFOLIO_ID` is a UUID.
- `SYMBOL` examples use `IBM`.

---

## 0) Set environment variables

```bash
GO_API_BASE="http://127.0.0.1:8000"
PY_API_BASE="http://127.0.0.1:8001"

PORTFOLIO_ID="532b7f1e-0845-4d0a-aa08-9ae0871ccb79"
SYMBOL="IBM"
```

---

## 1) (Recommended) Refresh portfolio data using Go API job queue

### 1.1 Fetch portfolio symbols (from Go API portfolio endpoint)

This endpoint returns holdings; we extract symbols with `jq`.

```bash
USER_ID="4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"

SYMBOLS_JSON=$(curl -s "$GO_API_BASE/api/v1/portfolio/$USER_ID/$PORTFOLIO_ID" \
  | jq -c '[.holdings[].symbol]')

echo "$SYMBOLS_JSON"
```

### 1.2 Enqueue the portfolio data-load (one job per symbol)

```bash
curl -s -X POST "$GO_API_BASE/api/v1/portfolios/$PORTFOLIO_ID/data-load" \
  -H "Content-Type: application/json" \
  -d "{\"symbols\": $SYMBOLS_JSON, \"data_types\":[\"price_historical\",\"indicators\"], \"force\": true}" \
  | jq
```

This returns a `run_id`.

### 1.3 Check the run + events (includes per-symbol job_started/job_finished)

```bash
RUN_ID="<paste-run-id-here>"

curl -s "$GO_API_BASE/api/v1/data-load/runs/$RUN_ID" | jq
```

### 1.4 Filter run events to a single symbol

```bash
RUN_ID="<paste-run-id-here>"
SYMBOL="IBM"

curl -s "$GO_API_BASE/api/v1/data-load/runs/$RUN_ID" \
  | jq --arg s "$SYMBOL" '.events[] | select(.symbol==$s) | {event_ts, level, provider, operation, duration_ms, message, error_message, context}'
```

---

## 2) Generate Trading Decision V3 decisions (on-demand)

### 2.1 Enqueue Trading Decision V3 via Go API job queue (recommended)

This creates a run and enqueues one job per symbol. Inspect results via `/api/v1/data-load/runs/:run_id`.

```bash
PORTFOLIO_ID="532b7f1e-0845-4d0a-aa08-9ae0871ccb79"

curl -s -X POST "$GO_API_BASE/api/v1/portfolios/$PORTFOLIO_ID/trading-decisions/v3/run" \
  -H "Content-Type: application/json" \
  -d "{}" \
  | jq
```

Optional `as_of_date`:

```bash
AS_OF_DATE="2026-04-29"

curl -s -X POST "$GO_API_BASE/api/v1/portfolios/$PORTFOLIO_ID/trading-decisions/v3/run" \
  -H "Content-Type: application/json" \
  -d "{\"as_of_date\":\"$AS_OF_DATE\"}" \
  | jq
```

Inspect results (job_finished events will include the per-symbol decision details in `context.result`):

```bash
RUN_ID="<paste-run-id-here>"
curl -s "$GO_API_BASE/api/v1/data-load/runs/$RUN_ID" | jq
```

### 2.2 Run V3 decisions for a portfolio (python-worker)

This generates decisions for all symbols in the portfolio and persists them.

```bash
PORTFOLIO_ID="532b7f1e-0845-4d0a-aa08-9ae0871ccb79"

curl -s -X POST "$PY_API_BASE/api/v1/trading-v3/decisions/run-portfolio" \
  -H "Content-Type: application/json" \
  -d "{\"portfolio_id\":\"$PORTFOLIO_ID\",\"refresh\": false}" \
  | jq
```

### 2.2 Inspect one symbol from that run

```bash
SYMBOL="IBM"
PORTFOLIO_ID="532b7f1e-0845-4d0a-aa08-9ae0871ccb79"

curl -s -X POST "$PY_API_BASE/api/v1/trading-v3/decisions/run-portfolio" \
  -H "Content-Type: application/json" \
  -d "{\"portfolio_id\":\"$PORTFOLIO_ID\",\"refresh\": false}" \
  | jq --arg s "$SYMBOL" '.decisions[] | select(.symbol==$s)'
```

---

## 5) Schedule Trading Decision V3 (Go API)

### 5.1 Create a schedule

```bash
PORTFOLIO_ID="532b7f1e-0845-4d0a-aa08-9ae0871ccb79"

curl -s -X POST "$GO_API_BASE/api/v1/schedules" \
  -H "Content-Type: application/json" \
  -d "{\"kind\":\"trading_decision_v3\",\"portfolio_id\":\"$PORTFOLIO_ID\",\"profile\":\"\",\"cron_expression\":\"0 18 * * 1-5\",\"timezone\":\"America/New_York\",\"enabled\":true,\"config\":{}}" \
  | jq
```

Optional `target_date` (becomes `as_of_date` for the scheduled run):

```bash
curl -s -X POST "$GO_API_BASE/api/v1/schedules" \
  -H "Content-Type: application/json" \
  -d "{\"kind\":\"trading_decision_v3\",\"portfolio_id\":\"$PORTFOLIO_ID\",\"profile\":\"\",\"cron_expression\":\"0 18 * * 1-5\",\"timezone\":\"America/New_York\",\"enabled\":true,\"config\":{\"target_date\":\"2026-04-29\"}}" \
  | jq
```

### 5.2 Trigger schedule run immediately

```bash
SCHEDULE_ID="<paste-schedule-id-here>"
curl -s -X POST "$GO_API_BASE/api/v1/schedules/$SCHEDULE_ID/run-now" -H "Content-Type: application/json" -d "{}" | jq
```

### 5.3 Run scheduler tick (process due schedules)

```bash
curl -s -X POST "$GO_API_BASE/api/v1/scheduler/tick" -H "Content-Type: application/json" -d "{}" | jq
```

---

## 3) View decisions after they are persisted

### 3.1 Latest decision for a symbol (no date needed)

This returns the latest persisted Trading Decision V3 for the symbol (by DB timestamp).

```bash
SYMBOL="IBM"
curl -i "$PY_API_BASE/api/v1/trading-v3/decisions/latest/$SYMBOL"
```

Pretty-print JSON if it returns 200:

```bash
SYMBOL="IBM"
curl -s "$PY_API_BASE/api/v1/trading-v3/decisions/latest/$SYMBOL" | jq
```

### 3.2 List available V3 decision dates

```bash
curl -s "$PY_API_BASE/api/v1/trading-v3/decisions/dates?limit=60" | jq
```

### 3.3 List all V3 decisions for a given `as_of_date`

```bash
AS_OF_DATE="2026-04-29"

curl -s "$PY_API_BASE/api/v1/trading-v3/decisions/by-date?as_of_date=$AS_OF_DATE" | jq
```

### 3.4 List V3 decisions for a date, filtered to a portfolio

```bash
AS_OF_DATE="2026-04-29"
PORTFOLIO_ID="532b7f1e-0845-4d0a-aa08-9ae0871ccb79"

curl -s "$PY_API_BASE/api/v1/trading-v3/decisions/by-date?as_of_date=$AS_OF_DATE&portfolio_id=$PORTFOLIO_ID" | jq
```

---

## 4) Common pitfalls

### 4.1 "curl prints nothing"

Use `-i` to see status + content type:

```bash
SYMBOL="IBM"
curl -i "$PY_API_BASE/api/v1/trading-v3/decisions/latest/$SYMBOL"
```

### 4.2 Missing `$SYMBOL` variable

If `$SYMBOL` is empty, you’ll hit an invalid route. Check:

```bash
echo "SYMBOL=[$SYMBOL]"
```

---
