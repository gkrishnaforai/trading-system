# Supabase Setup Guide

This directory contains the Supabase Docker Compose setup and migration scripts for the Trading System.

## Overview

This setup provides:
- **PostgreSQL 15** database with extensions (pgcrypto, uuid-ossp, pg_stat_statements) ✅
- **Supabase Auth (GoTrue)** authentication service ✅
- **Optional Services** (commented out, can be enabled later):
  - **PostgREST** REST API for PostgreSQL
  - **Realtime** WebSocket server
  - **Storage** file storage service

**Note**: Core services (PostgreSQL + Auth) are enabled. Additional services (PostgREST, Realtime, Storage) can be added later when needed.

## Quick Start

**Note**: All scripts use Docker exec - no local PostgreSQL client installation needed!

### 1. Start Supabase Services

```bash
# Start Supabase stack
docker-compose -f docker-compose.supabase.yml up -d

# Check status
docker-compose -f docker-compose.supabase.yml ps
```

### 2. Create Tables (One-Time Execution)

```bash
# Run all migrations to create tables
./supabase/scripts/create_tables.sh
```

This script will:
- Use Docker exec to run psql inside the container (no local psql needed)
- Connect to Supabase PostgreSQL
- Run all migrations in order
- Create all required tables and indexes

### 3. Seed Sample Data (One-Time Execution)

```bash
# Insert sample users, portfolios, and holdings
./supabase/scripts/seed_data.sh
```

### 4. Verify Setup

```bash
# Check that all tables exist and show row counts
./supabase/scripts/verify_tables.sh
```

## Manual Execution

All scripts can be run manually. They use environment variables from `.env` file or defaults.

### Environment Variables

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
```

### Manual Database Connection

```bash
# Connect to Supabase PostgreSQL
psql -h localhost -p 54322 -U postgres -d postgres

# Or using environment variables
export PGPASSWORD="your-super-secret-and-long-postgres-password"
psql -h localhost -p 54322 -U postgres -d postgres
```

### Manual Migration Execution

```bash
# Run a specific migration
psql -h localhost -p 54322 -U postgres -d postgres -f supabase/migrations/001_initial_schema.sql

# Run all migrations in order
for file in supabase/migrations/*.sql; do
    echo "Applying $file..."
    psql -h localhost -p 54322 -U postgres -d postgres -f "$file"
done
```

### Manual Seed Execution

```bash
# Run seed script
psql -h localhost -p 54322 -U postgres -d postgres -f supabase/scripts/seed.sql
```

## Migration Files

All migrations are in `supabase/migrations/`:

1. `001_initial_schema.sql` - Core tables (users, portfolios, holdings, market data, indicators)
2. `002_add_strategy_preference.sql` - Strategy preferences
3. `003_add_news_earnings_industry.sql` - News, earnings, industry peers tables
4. `004_add_notes_and_alerts.sql` - Notes and alerts system
5. `005_add_watchlists.sql` - Watchlist tables
6. `006_enhance_portfolio_watchlist_for_traders.sql` - Enhanced trader fields
7. `007_add_market_features.sql` - Market features (movers, sectors, etc.)
8. `008_add_blog_generation.sql` - Blog generation tables
9. `009_add_swing_trading.sql` - Swing trading tables
10. `010_add_volume_to_indicators.sql` - Volume indicators

## Database Connection String

For applications, use:

```
postgresql://postgres:your-super-secret-and-long-postgres-password@localhost:54322/postgres
```

## Supabase Services

Once started, services are available at:

- **PostgreSQL**: `localhost:54322`
- **Auth (GoTrue)**: `localhost:9999`
- **REST API (PostgREST)**: `localhost:3000`
- **Realtime**: `localhost:4000`
- **Storage**: `localhost:5000` (optional, not started by default)

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

# Drop and recreate (WARNING: Deletes all data)
docker-compose -f docker-compose.supabase.yml down -v
docker-compose -f docker-compose.supabase.yml up -d
./supabase/scripts/create_tables.sh
```

### Reset database

```bash
# Stop and remove volumes (deletes all data)
docker-compose -f docker-compose.supabase.yml down -v

# Start fresh
docker-compose -f docker-compose.supabase.yml up -d
./supabase/scripts/create_tables.sh
./supabase/scripts/seed_data.sh
```

## Integration with Trading System

Update your application's database connection:

### Go API

```go
DATABASE_URL=postgresql://postgres:password@localhost:54322/postgres
```

### Python Worker

```python
DATABASE_URL=postgresql://postgres:password@localhost:54322/postgres
```

## Next Steps

1. ✅ Start Supabase: `docker-compose -f docker-compose.supabase.yml up -d`
2. ✅ Create tables: `./supabase/scripts/create_tables.sh`
3. ✅ Seed data: `./supabase/scripts/seed_data.sh`
4. ✅ Verify: `./supabase/scripts/verify_tables.sh`
5. ✅ Update application connection strings
6. ✅ Test application with Supabase

## Notes

- All migrations are idempotent (can be run multiple times safely)
- Seed script uses `ON CONFLICT DO NOTHING` to avoid duplicates
- Tables are created in the `public` schema
- All timestamps use `NOW()` instead of `CURRENT_TIMESTAMP`
- JSON columns use `JSONB` for better performance

