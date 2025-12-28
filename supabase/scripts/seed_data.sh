#!/bin/bash
# Seed Supabase database with sample data
# This script creates sample users, portfolios, and holdings
# Uses Docker exec to run psql inside the container (no local psql needed)

set -e

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Default values
DB_NAME="${POSTGRES_DB:-postgres}"
DB_USER="${POSTGRES_USER:-postgres}"

SEED_FILE="${SEED_FILE:-./supabase/scripts/seed.sql}"
CONTAINER_NAME="${CONTAINER_NAME:-trading-system-supabase-db}"

echo "🌱 Seeding Supabase database with sample data..."
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

echo "✅ Container is running"
echo ""

# Test connection using Docker exec
echo "🔌 Testing database connection..."
if ! docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" > /dev/null 2>&1; then
    echo "❌ Cannot connect to database."
    exit 1
fi
echo "✅ Database connection successful"
echo ""

# Run seed script
if [ -f "$SEED_FILE" ]; then
    echo "📥 Running seed script: $SEED_FILE"
    # Copy seed file to container and execute
    docker cp "$SEED_FILE" "$CONTAINER_NAME:/tmp/seed.sql" > /dev/null 2>&1
    if docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -f "/tmp/seed.sql"; then
        echo ""
        echo "✅ Seed data inserted successfully!"
    else
        echo ""
        echo "❌ Error seeding database. Please check the seed file."
        exit 1
    fi
else
    echo "❌ Seed file not found: $SEED_FILE"
    exit 1
fi

echo ""
echo "💡 Verify data: ./supabase/scripts/verify_tables.sh"
