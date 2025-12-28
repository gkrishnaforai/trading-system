#!/bin/bash
# Initialize database with schema

set -e

DB_PATH="${DB_PATH:-./db/trading.db}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-./db/migrations}"

echo "🗄️  Initializing database at $DB_PATH"

# Create db directory if it doesn't exist
mkdir -p "$(dirname "$DB_PATH")"

# Check if SQLite is available
if ! command -v sqlite3 &> /dev/null; then
    echo "❌ sqlite3 not found. Please install SQLite."
    exit 1
fi

# Run migrations
echo "📝 Running migrations..."

if [ -f "$MIGRATIONS_DIR/001_initial_schema.sql" ]; then
    sqlite3 "$DB_PATH" < "$MIGRATIONS_DIR/001_initial_schema.sql"
    echo "✅ Applied migration 001_initial_schema.sql"
else
    echo "❌ Migration file not found: $MIGRATIONS_DIR/001_initial_schema.sql"
    exit 1
fi

if [ -f "$MIGRATIONS_DIR/002_add_strategy_preference.sql" ]; then
    sqlite3 "$DB_PATH" < "$MIGRATIONS_DIR/002_add_strategy_preference.sql"
    echo "✅ Applied migration 002_add_strategy_preference.sql"
fi

if [ -f "$MIGRATIONS_DIR/003_add_news_earnings_industry.sql" ]; then
    sqlite3 "$DB_PATH" < "$MIGRATIONS_DIR/003_add_news_earnings_industry.sql"
    echo "✅ Applied migration 003_add_news_earnings_industry.sql"
fi

if [ -f "$MIGRATIONS_DIR/004_add_notes_and_alerts.sql" ]; then
    sqlite3 "$DB_PATH" < "$MIGRATIONS_DIR/004_add_notes_and_alerts.sql"
    echo "✅ Applied migration 004_add_notes_and_alerts.sql"
fi

if [ -f "$MIGRATIONS_DIR/005_add_watchlists.sql" ]; then
    sqlite3 "$DB_PATH" < "$MIGRATIONS_DIR/005_add_watchlists.sql"
    echo "✅ Applied migration 005_add_watchlists.sql"
fi

if [ -f "$MIGRATIONS_DIR/006_enhance_portfolio_watchlist_for_traders.sql" ]; then
    sqlite3 "$DB_PATH" < "$MIGRATIONS_DIR/006_enhance_portfolio_watchlist_for_traders.sql"
    echo "✅ Applied migration 006_enhance_portfolio_watchlist_for_traders.sql"
fi

if [ -f "$MIGRATIONS_DIR/007_add_market_features.sql" ]; then
    sqlite3 "$DB_PATH" < "$MIGRATIONS_DIR/007_add_market_features.sql"
    echo "✅ Applied migration 007_add_market_features.sql"
fi

if [ -f "$MIGRATIONS_DIR/008_add_blog_generation.sql" ]; then
    sqlite3 "$DB_PATH" < "$MIGRATIONS_DIR/008_add_blog_generation.sql"
    echo "✅ Applied migration 008_add_blog_generation.sql"
fi

if [ -f "$MIGRATIONS_DIR/009_add_swing_trading.sql" ]; then
    sqlite3 "$DB_PATH" < "$MIGRATIONS_DIR/009_add_swing_trading.sql"
    echo "✅ Applied migration 009_add_swing_trading.sql"
fi

echo "✅ Database initialized successfully"

echo "✅ Database setup complete!"

