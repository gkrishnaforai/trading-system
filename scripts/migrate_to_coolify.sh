#!/bin/bash

# Database Migration Script for Coolify Deployment
# Usage: ./migrate_to_coolify.sh [schema|data|full]

set -e

MIGRATION_TYPE=${1:-schema}
LOCAL_DB="trading_system"
LOCAL_USER="trading"
SERVER_HOST=${SERVER_HOST:-"your-server.com"}
SERVER_DB_USER=${SERVER_DB_USER:-"postgres"}
SERVER_DB_NAME=${SERVER_DB_NAME:-"trading_system"}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "🚀 Starting database migration to Coolify..."
echo "📊 Migration type: $MIGRATION_TYPE"
echo "⏰ Timestamp: $TIMESTAMP"

# Create backup directory
mkdir -p migrations/$TIMESTAMP
cd migrations/$TIMESTAMP

case $MIGRATION_TYPE in
    "schema")
        echo "📋 Exporting schema only..."
        docker exec trading-system-postgres pg_dump -U $LOCAL_USER --schema-only --no-owner --no-privileges $LOCAL_DB > schema.sql
        
        echo "📤 Transferring schema to server..."
        scp schema.sql $SERVER_HOST:/tmp/
        
        echo "🗄️ Creating database on server..."
        ssh $SERVER_HOST "psql -U $SERVER_DB_USER -c \"DROP DATABASE IF EXISTS $SERVER_DB_NAME; CREATE DATABASE $SERVER_DB_NAME;\""
        
        echo "📥 Importing schema on server..."
        ssh $SERVER_HOST "psql -U $SERVER_DB_USER -d $SERVER_DB_NAME < /tmp/schema.sql"
        
        echo "✅ Schema migration completed!"
        ;;
        
    "data")
        echo "💾 Exporting data only..."
        docker exec trading-system-postgres pg_dump -U $LOCAL_USER --data-only $LOCAL_DB > data.sql
        
        echo "📤 Transferring data to server..."
        scp data.sql $SERVER_HOST:/tmp/
        
        echo "📥 Importing data on server..."
        ssh $SERVER_HOST "psql -U $SERVER_DB_USER -d $SERVER_DB_NAME < /tmp/data.sql"
        
        echo "✅ Data migration completed!"
        ;;
        
    "full")
        echo "📦 Exporting full database..."
        docker exec trading-system-postgres pg_dump -U $LOCAL_USER $LOCAL_DB | gzip > full_dump.sql.gz
        
        echo "📤 Transferring full dump to server..."
        scp full_dump.sql.gz $SERVER_HOST:/tmp/
        
        echo "🗄️ Creating fresh database on server..."
        ssh $SERVER_HOST "psql -U $SERVER_DB_USER -c \"DROP DATABASE IF EXISTS $SERVER_DB_NAME; CREATE DATABASE $SERVER_DB_NAME;\""
        
        echo "📥 Importing full database on server..."
        ssh $SERVER_HOST "gunzip -c /tmp/full_dump.sql.gz | psql -U $SERVER_DB_USER -d $SERVER_DB_NAME"
        
        echo "✅ Full migration completed!"
        ;;
        
    *)
        echo "❌ Invalid migration type. Use: schema, data, or full"
        exit 1
        ;;
esac

echo "🔍 Verifying migration..."
ssh $SERVER_HOST "psql -U $SERVER_DB_USER -d $SERVER_DB_NAME -c \"SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema = 'public';\""

echo "🎉 Migration to Coolify completed successfully!"
echo "📁 Migration files saved in: migrations/$TIMESTAMP/"
