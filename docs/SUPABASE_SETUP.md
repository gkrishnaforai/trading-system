# Supabase Setup Guide

Complete guide for setting up Supabase with Docker Compose for the Trading System.

## Overview

Supabase provides a complete backend stack:
- **PostgreSQL** database with extensions (pgcrypto, uuid-ossp)
- **GoTrue** authentication service
- **PostgREST** REST API for PostgreSQL
- **Realtime** WebSocket server for live updates
- **Storage** file storage service

## Quick Start

### 1. Start Supabase

```bash
# Start all Supabase services
make supabase-up

# Or manually
docker-compose -f docker-compose.supabase.yml up -d
```

### 2. Create Tables (One-Time Execution)

```bash
# Run all migrations
make supabase-create-tables

# Or manually
./supabase/scripts/create_tables.sh
```

### 3. Seed Sample Data (One-Time Execution)

```bash
# Insert sample users, portfolios, holdings
make supabase-seed

# Or manually
./supabase/scripts/seed_data.sh
```

### 4. Verify Setup

```bash
# Check tables and row counts
make supabase-verify

# Or manually
./supabase/scripts/verify_tables.sh
```

### Complete Setup (All Steps)

```bash
# Run everything in one command
make supabase-setup
```

## Manual Execution

All scripts can be executed manually for one-time setup:

### Create Tables

```bash
# Using the script
./supabase/scripts/create_tables.sh

# Or manually with psql
export PGPASSWORD="your-super-secret-and-long-postgres-password"
for file in supabase/migrations/*.sql; do
    psql -h localhost -p 54322 -U postgres -d postgres -f "$file"
done
```

### Seed Data

```bash
# Using the script
./supabase/scripts/seed_data.sh

# Or manually with psql
export PGPASSWORD="your-super-secret-and-long-postgres-password"
psql -h localhost -p 54322 -U postgres -d postgres -f supabase/scripts/seed.sql
```

### Verify Tables

```bash
# Using the script
./supabase/scripts/verify_tables.sh

# Or manually with psql
export PGPASSWORD="your-super-secret-and-long-postgres-password"
psql -h localhost -p 54322 -U postgres -d postgres -c "\dt"
```

## Environment Variables

Create a `.env` file in the project root:

```bash
# PostgreSQL Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-super-secret-and-long-postgres-password
POSTGRES_DB=postgres

# Supabase Service Ports
SUPABASE_DB_PORT=54322
SUPABASE_AUTH_PORT=9999
SUPABASE_REST_PORT=3000
SUPABASE_REALTIME_PORT=4000
SUPABASE_STORAGE_PORT=5000

# JWT Configuration
SUPABASE_JWT_SECRET=your-super-secret-jwt-token-with-at-least-32-characters-long

# Supabase Keys (for local development)
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU
```

## Database Connection

### Connection String

```
postgresql://postgres:your-super-secret-and-long-postgres-password@localhost:54322/postgres
```

### Using psql

```bash
export PGPASSWORD="your-super-secret-and-long-postgres-password"
psql -h localhost -p 54322 -U postgres -d postgres
```

## Migration Files

All migrations are in `supabase/migrations/`:

1. `001_initial_schema.sql` - Core tables
2. `002_add_strategy_preference.sql` - Strategy preferences
3. `003_add_news_earnings_industry.sql` - News, earnings, industry peers
4. `004_add_notes_and_alerts.sql` - Notes and alerts system
5. `005_add_watchlists.sql` - Watchlist tables
6. `006_enhance_portfolio_watchlist_for_traders.sql` - Enhanced trader fields
7. `007_add_market_features.sql` - Market features
8. `008_add_blog_generation.sql` - Blog generation
9. `009_add_swing_trading.sql` - Swing trading
10. `010_add_volume_to_indicators.sql` - Volume indicators

## Supabase Services

Once started, services are available at:

- **PostgreSQL**: `localhost:54322`
- **Auth (GoTrue)**: `localhost:9999`
- **REST API (PostgREST)**: `localhost:3000`
- **Realtime**: `localhost:4000`
- **Storage**: `localhost:5000`

## Integration with Trading System

### Update Go API

Update `docker-compose.yml` or `.env`:

```yaml
environment:
  - DATABASE_URL=postgresql://postgres:password@supabase-db:5432/postgres
```

### Update Python Worker

Update `docker-compose.yml` or `.env`:

```yaml
environment:
  - DATABASE_URL=postgresql://postgres:password@supabase-db:5432/postgres
```

## Troubleshooting

### Cannot connect to database

```bash
# Check if Supabase is running
docker-compose -f docker-compose.supabase.yml ps

# Check logs
docker-compose -f docker-compose.supabase.yml logs supabase-db

# Restart services
docker-compose -f docker-compose.supabase.yml restart
```

### Migration errors

```bash
# Check if tables already exist
psql -h localhost -p 54322 -U postgres -d postgres -c "\dt"

# Check specific migration
psql -h localhost -p 54322 -U postgres -d postgres -f supabase/migrations/001_initial_schema.sql
```

### Reset database

```bash
# Stop and remove volumes (WARNING: Deletes all data)
docker-compose -f docker-compose.supabase.yml down -v

# Start fresh
make supabase-setup
```

## Differences from SQLite

### Data Types

- `TEXT` → `VARCHAR(255)` or `TEXT`
- `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL PRIMARY KEY`
- `REAL` → `DOUBLE PRECISION`
- `JSON` → `JSONB` (better performance)
- `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` → `TIMESTAMP DEFAULT NOW()`

### SQL Syntax

- `INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO NOTHING`
- `date('now', '-30 days')` → `CURRENT_DATE - INTERVAL '30 days'`
- `IF NOT EXISTS` works the same

## Next Steps

1. ✅ Start Supabase: `make supabase-up`
2. ✅ Create tables: `make supabase-create-tables`
3. ✅ Seed data: `make supabase-seed`
4. ✅ Verify: `make supabase-verify`
5. ✅ Update application connection strings
6. ✅ Test application with Supabase

## Notes

- All migrations are idempotent (safe to run multiple times)
- Seed script uses `ON CONFLICT DO NOTHING` to avoid duplicates
- Tables are created in the `public` schema
- All timestamps use `NOW()` instead of `CURRENT_TIMESTAMP`
- JSON columns use `JSONB` for better performance in PostgreSQL

