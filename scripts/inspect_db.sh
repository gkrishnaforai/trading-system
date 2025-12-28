#!/bin/bash
# Script to inspect SQLite database tables and data
# Usage: ./scripts/inspect_db.sh [table_name]

set -e

DB_PATH="${DB_PATH:-./db/trading.db}"

if [ ! -f "$DB_PATH" ]; then
    echo "❌ Database file not found at: $DB_PATH"
    echo "💡 Make sure you've run 'make init-db' first"
    exit 1
fi

echo "📊 Inspecting database: $DB_PATH"
echo ""

# List all tables
echo "📋 Available tables:"
sqlite3 "$DB_PATH" ".tables"
echo ""

# If table name provided, show data from that table
if [ -n "$1" ]; then
    TABLE_NAME="$1"
    echo "📊 Data from table: $TABLE_NAME"
    echo "----------------------------------------"
    sqlite3 -header -column "$DB_PATH" "SELECT * FROM $TABLE_NAME LIMIT 20;"
    echo ""
    echo "📈 Row count:"
    sqlite3 "$DB_PATH" "SELECT COUNT(*) as count FROM $TABLE_NAME;"
else
    # Show summary of all tables
    echo "📊 Table Summary:"
    echo "----------------------------------------"
    
    for table in $(sqlite3 "$DB_PATH" ".tables"); do
        count=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM $table;" 2>/dev/null || echo "0")
        echo "  $table: $count rows"
    done
    
    echo ""
    echo "💡 To view data from a specific table, run:"
    echo "   ./scripts/inspect_db.sh <table_name>"
    echo ""
    echo "📋 Example queries:"
    echo "   ./scripts/inspect_db.sh raw_market_data"
    echo "   ./scripts/inspect_db.sh aggregated_indicators"
    echo "   ./scripts/inspect_db.sh stock_news"
    echo "   ./scripts/inspect_db.sh earnings_data"
    echo "   ./scripts/inspect_db.sh industry_peers"
fi

