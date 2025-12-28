# Supabase Quick Start Guide

**Note**: 
- This setup uses standard PostgreSQL 15 with extensions
- All scripts use Docker exec - **no local PostgreSQL client installation needed!**
- The full Supabase stack (Auth, PostgREST, Realtime, Storage) is optional and commented out

## One-Time Setup (Manual Execution)

### Step 1: Start Supabase

```bash
# Start Supabase services
docker-compose -f docker-compose.supabase.yml up -d

# Wait for services to be ready (about 10 seconds)
sleep 10
```

### Step 2: Create All Tables

```bash
# Run all migrations
./supabase/scripts/create_tables.sh
```

This will:
- Connect to Supabase PostgreSQL
- Run all 10 migrations in order
- Create all tables and indexes

### Step 3: Seed Sample Data

```bash
# Insert sample users, portfolios, holdings
./supabase/scripts/seed_data.sh
```

This will:
- Insert 3 sample users (basic, pro, elite)
- Insert 3 sample portfolios
- Insert 9 sample holdings

### Step 4: Verify Setup

```bash
# Check tables and show row counts
./supabase/scripts/verify_tables.sh
```

## All-in-One Command

```bash
# Complete setup in one command
./supabase/scripts/run_all_migrations.sh
```

Or using Make:

```bash
make supabase-setup
```

## Manual Execution (Alternative)

If you prefer to run SQL manually:

### Connect to Database

```bash
export PGPASSWORD="your-super-secret-and-long-postgres-password"
psql -h localhost -p 54322 -U postgres -d postgres
```

### Run Migrations

```sql
-- In psql, run each migration file
\i supabase/migrations/001_initial_schema.sql
\i supabase/migrations/002_add_strategy_preference.sql
\i supabase/migrations/003_add_news_earnings_industry.sql
\i supabase/migrations/004_add_notes_and_alerts.sql
\i supabase/migrations/005_add_watchlists.sql
\i supabase/migrations/010_add_volume_to_indicators.sql
```

### Seed Data

```sql
\i supabase/scripts/seed.sql
```

## Environment Variables

Create `.env` file:

```bash
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-super-secret-and-long-postgres-password
POSTGRES_DB=postgres
SUPABASE_DB_PORT=54322
```

## Connection String

For applications:

```
postgresql://postgres:your-super-secret-and-long-postgres-password@localhost:54322/postgres
```

## Troubleshooting

### Database not running

```bash
docker-compose -f docker-compose.supabase.yml ps
docker-compose -f docker-compose.supabase.yml logs supabase-db
```

### Reset everything

```bash
docker-compose -f docker-compose.supabase.yml down -v
docker-compose -f docker-compose.supabase.yml up -d
./supabase/scripts/create_tables.sh
./supabase/scripts/seed_data.sh
```

## Next Steps

1. Update application `DATABASE_URL` to use Supabase
2. Restart services: `docker-compose restart go-api python-worker`
3. Test the application

