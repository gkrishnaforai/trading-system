#!/bin/bash
# Verify that all tables exist in Supabase database
# Uses Docker exec to run psql inside the container (no local psql needed)

set -e

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Default values
DB_NAME="${POSTGRES_DB:-postgres}"
DB_USER="${POSTGRES_USER:-postgres}"
CONTAINER_NAME="${CONTAINER_NAME:-trading-system-supabase-db}"

echo "🔍 Verifying tables in Supabase database..."
echo "   Container: $CONTAINER_NAME"
echo "   Database: $DB_NAME"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ docker not found. Please install Docker."
    exit 1
fi

# Check if container is running
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "❌ Container $CONTAINER_NAME is not running."
    echo "   Please start Supabase: docker-compose -f docker-compose.supabase.yml up -d"
    exit 1
fi

# Test connection
if ! docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" > /dev/null 2>&1; then
    echo "❌ Cannot connect to database."
    exit 1
fi

# Expected tables
EXPECTED_TABLES=(
    "users"
    "portfolios"
    "holdings"
    "watchlists"
    "watchlist_items"
    "raw_market_data_daily"
    "raw_market_data_intraday"
    "indicators_daily"
    "indicators_intraday"
    "data_ingestion_state"
    "fundamentals_snapshots"
    "stock_news"
    "earnings_data"
    "industry_peers"
    "alert_types"
    "alerts"
    "alert_notifications"
    "notification_channels"
    "blog_topics"
    "blog_drafts"
    "blog_published"
    "blog_publishing_config"
    "blog_generation_audit"
    "blog_generation_log"
    "workflow_executions"
    "workflow_stage_executions"
    "workflow_symbol_states"
    "workflow_checkpoints"
    "workflow_dlq"
    "workflow_gate_results"
    "data_validation_reports"
    "data_fetch_audit"
)

echo "📊 Checking tables..."
echo ""

MISSING_TABLES=()
for table in "${EXPECTED_TABLES[@]}"; do
    # Check if table exists using Docker exec
    result=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '$table');" 2>/dev/null | tr -d ' \n' || echo "f")
    if [ "$result" = "t" ]; then
        echo "   ✅ $table"
    else
        echo "   ❌ $table (missing)"
        MISSING_TABLES+=("$table")
    fi
done

echo ""

if [ ${#MISSING_TABLES[@]} -eq 0 ]; then
    echo "✅ All tables exist!"
    
    # Show table counts
    echo ""
    echo "📈 Table row counts:"
    for table in "${EXPECTED_TABLES[@]}"; do
        count=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM $table;" 2>/dev/null | tr -d ' \n' || echo "0")
        echo "   $table: $count rows"
    done
else
    echo "❌ Missing tables: ${MISSING_TABLES[*]}"
    echo ""
    echo "💡 Run migrations: ./supabase/scripts/create_tables.sh"
    exit 1
fi
