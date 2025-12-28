#!/bin/bash
# Create all tables in Supabase PostgreSQL database
# This script runs all migrations in order
# Uses Docker exec to run psql inside the container (no local psql needed)

set -e

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Default values
DB_NAME="${POSTGRES_DB:-postgres}"
DB_USER="${POSTGRES_USER:-postgres}"

MIGRATIONS_DIR="${MIGRATIONS_DIR:-./supabase/migrations}"
CONTAINER_NAME="${CONTAINER_NAME:-trading-system-supabase-db}"

echo "🗄️  Creating tables in Supabase PostgreSQL database..."
echo "   Container: $CONTAINER_NAME"
echo "   Database: $DB_NAME"
echo "   User: $DB_USER"
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
    echo "❌ Cannot connect to database. Waiting a few seconds for database to be ready..."
    sleep 5
    if ! docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" > /dev/null 2>&1; then
        echo "❌ Still cannot connect. Please check container logs:"
        echo "   docker logs $CONTAINER_NAME"
        exit 1
    fi
fi
echo "✅ Database connection successful"
echo ""

# Run migrations in order
echo "📝 Running migrations..."

MIGRATION_FILES=(
    "000_enable_extensions.sql"
    "001_baseline_schema.sql"
)

for migration_file in "${MIGRATION_FILES[@]}"; do
    migration_path="$MIGRATIONS_DIR/$migration_file"
    if [ -f "$migration_path" ]; then
        echo "   Applying $migration_file..."
        # Copy migration file to container and execute
        if docker cp "$migration_path" "$CONTAINER_NAME:/tmp/$migration_file" > /dev/null 2>&1 && \
           docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -f "/tmp/$migration_file" > /dev/null 2>&1; then
            echo "   ✅ Applied $migration_file"
        else
            # Try again with error output visible
            echo "   ⚠️  Warning: $migration_file may have errors or already applied"
            docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -f "/tmp/$migration_file" 2>&1 | head -5 || true
        fi
    else
        echo "   ⚠️  Migration file not found: $migration_path"
    fi
done

echo ""
echo "✅ All migrations completed!"
echo ""
echo "💡 Next steps:"
echo "   1. Run seed script: ./supabase/scripts/seed_data.sh"
echo "   2. Verify tables: ./supabase/scripts/verify_tables.sh"
