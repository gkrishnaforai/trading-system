# Migration Notes

## Completed Migrations

✅ **001_initial_schema.sql** - Core tables (users, portfolios, holdings, market data, indicators)
✅ **002_add_strategy_preference.sql** - Strategy preferences
✅ **003_add_news_earnings_industry.sql** - News, earnings, industry peers
✅ **004_add_notes_and_alerts.sql** - Notes and alerts system
✅ **005_add_watchlists.sql** - Watchlist tables
✅ **010_add_volume_to_indicators.sql** - Volume indicators

## Pending Migrations (Can be added later)

The following migrations are large enhancement migrations that add many columns to existing tables. They can be converted and added later if needed:

- **006_enhance_portfolio_watchlist_for_traders.sql** - Adds ~50+ columns to portfolios, holdings, watchlists
- **007_add_market_features.sql** - Market movers, sector performance, etc.
- **008_add_blog_generation.sql** - Blog generation tables
- **009_add_swing_trading.sql** - Swing trading tables

## Converting SQLite to PostgreSQL

Key differences:

1. **Data Types**:
   - `TEXT` → `VARCHAR(255)` or `TEXT`
   - `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL PRIMARY KEY`
   - `REAL` → `DOUBLE PRECISION`
   - `JSON` → `JSONB`

2. **SQL Syntax**:
   - `INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO NOTHING`
   - `date('now', '-30 days')` → `CURRENT_DATE - INTERVAL '30 days'`
   - `CURRENT_TIMESTAMP` → `NOW()`

3. **ALTER TABLE**:
   - `ADD COLUMN` → `ADD COLUMN IF NOT EXISTS` (PostgreSQL 9.6+)

## Adding Pending Migrations

To add migrations 006-009:

1. Read the SQLite migration file
2. Convert data types (TEXT → VARCHAR, REAL → DOUBLE PRECISION, etc.)
3. Convert SQL syntax (INSERT OR IGNORE → ON CONFLICT DO NOTHING)
4. Save as `supabase/migrations/00X_*.sql`
5. Add to `MIGRATION_FILES` array in `create_tables.sh`

