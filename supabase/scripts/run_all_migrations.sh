#!/bin/bash
# Run all migrations and seed data in one command
# Convenience script for one-time setup
# Uses Docker exec (no local psql needed)

set -e

echo "🚀 Setting up Supabase database..."
echo ""

# Check if Supabase is running
CONTAINER_NAME="trading-system-supabase-db"
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "⚠️  Supabase database not running. Starting..."
    docker-compose -f docker-compose.supabase.yml up -d supabase-db
    echo "⏳ Waiting for database to be ready..."
    sleep 10
fi

# Run migrations
echo "📝 Step 1: Creating tables..."
./supabase/scripts/create_tables.sh

echo ""
echo "🌱 Step 2: Seeding data..."
./supabase/scripts/seed_data.sh

echo ""
echo "✅ Step 3: Verifying setup..."
./supabase/scripts/verify_tables.sh

echo ""
echo "🎉 Setup complete!"
echo ""
echo "💡 Next steps:"
echo "   1. Update application DATABASE_URL to use Supabase"
echo "   2. Restart services: docker-compose restart go-api python-worker"
echo "   3. Test the application"
