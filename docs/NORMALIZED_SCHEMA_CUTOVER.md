# Normalized Schema Cutover (Dev)

This runbook documents the clean cutover to the normalized, provider-agnostic schema centered around `stocks(id UUID)` and `stock_id` foreign keys.

## Goals

- Apply the authoritative baseline migration: `supabase/migrations/001_baseline_schema.sql`
- Ensure time-series data lands in `stock_market_metrics(stock_id, date, source)`
- Ensure user-scoped data uses UUIDs and `stock_id` joins (`portfolio_positions`, `watchlist_stocks`)

## Local environment

- Postgres container: `trading-system-postgres`
- DB / user: `trading_system` / `trading`

## Option A: destructive reset (fastest for dev)

1) Drop and recreate `public`:

```sh
docker exec -i trading-system-postgres psql -U trading -d trading_system -v ON_ERROR_STOP=1 <<'SQL'
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO trading;
GRANT ALL ON SCHEMA public TO public;
SQL
```

2) Apply baseline migration:

```sh
docker exec -i trading-system-postgres psql -U trading -d trading_system -v ON_ERROR_STOP=1 \
  < /Users/krishnag/tools/trading-system/supabase/migrations/001_baseline_schema.sql
```

3) Verify core tables:

```sh
docker exec -i trading-system-postgres psql -U trading -d trading_system -c "\\dt" 
```

4) Verify `stock_market_metrics.updated_at` exists:

```sh
docker exec -i trading-system-postgres psql -U trading -d trading_system -c "\\d+ stock_market_metrics"
```

## Seed symbols (optional)

The Python worker can upsert `stocks(symbol)` automatically, but you can seed a few for quick checks:

```sh
docker exec -i trading-system-postgres psql -U trading -d trading_system -v ON_ERROR_STOP=1 <<'SQL'
INSERT INTO stocks (symbol, company_name) VALUES
  ('AAPL', 'Apple Inc.'),
  ('MSFT', 'Microsoft Corporation'),
  ('NVDA', 'NVIDIA Corporation'),
  ('TSLA', 'Tesla, Inc.'),
  ('AMZN', 'Amazon.com, Inc.')
ON CONFLICT (symbol) DO UPDATE SET company_name = EXCLUDED.company_name;
SQL
```

## Python worker: verify Yahoo daily price refresh

Run only the scheduled price refresh integration test:

```sh
docker exec trading-system-python-worker sh -lc \
  "pytest -q tests/test_data_refresh_integration.py -k test_scheduled_refresh_price_data -s"
```

Expected:

- Each symbol reports `Scheduled refresh successful`
- `Database rows: 250` (approx; depends on provider/period)

Verify data landed:

```sh
docker exec -i trading-system-postgres psql -U trading -d trading_system -v ON_ERROR_STOP=1 <<'SQL'
SELECT s.symbol, COUNT(*) AS rows
FROM stock_market_metrics m
JOIN stocks s ON s.id = m.stock_id
GROUP BY s.symbol
ORDER BY s.symbol;
SQL
```

## Go API: smoke checks

From `go-api/`:

```sh
go test ./...
```

Notes:

- `MarketDataRepository` reads from normalized tables where available.
- Indicators and LLM-generated reports are currently treated as not-yet-available in Go API until the corresponding normalized tables/migrations are added.

## Common failures

- `relation "stocks" does not exist`:
  - Baseline migration was not applied to the target DB.
- `column "updated_at" does not exist`:
  - DB schema is older than current baseline. Re-apply baseline.
- Python worker container not using updated code:
  - Ensure the container is rebuilt/recreated if it is not bind-mounted to the workspace.
