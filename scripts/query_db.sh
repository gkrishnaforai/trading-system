#!/bin/bash
# Script to run custom SQL queries on the database
# Usage: ./scripts/query_db.sh "SELECT * FROM raw_market_data WHERE stock_symbol='AAPL' LIMIT 5;"

set -e

DB_PATH="${DB_PATH:-./db/trading.db}"

if [ ! -f "$DB_PATH" ]; then
    echo "❌ Database file not found at: $DB_PATH"
    exit 1
fi

if [ -z "$1" ]; then
    echo "Usage: ./scripts/query_db.sh \"<SQL_QUERY>\""
    echo ""
    echo "Examples:"
    echo "  ./scripts/query_db.sh \"SELECT * FROM raw_market_data WHERE stock_symbol='AAPL' LIMIT 5;\""
    echo "  ./scripts/query_db.sh \"SELECT stock_symbol, COUNT(*) FROM raw_market_data GROUP BY stock_symbol;\""
    echo "  ./scripts/query_db.sh \"SELECT * FROM stock_news WHERE stock_symbol='AAPL' ORDER BY published_date DESC LIMIT 5;\""
    exit 1
fi

QUERY="$1"
echo "🔍 Running query:"
echo "$QUERY"
echo ""
echo "📊 Results:"
echo "----------------------------------------"
sqlite3 -header -column "$DB_PATH" "$QUERY"

