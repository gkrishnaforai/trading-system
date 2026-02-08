#!/bin/bash
# Clean existing stock grades tables and re-run migration
# Use this if you need to start fresh with the stock grades system

set -e

echo "🧹 Cleaning existing stock grades tables..."

# Check if we're in the right directory
if [ ! -f "run_stock_grades_migrations.py" ]; then
    echo "❌ Error: Please run this script from the python-worker directory"
    exit 1
fi

# Drop existing tables in correct order (to handle foreign key constraints)
echo "🗑️  Dropping existing tables..."

python -c "
import sys
sys.path.insert(0, '.')
try:
    from app.database import get_db
    db = get_db()
    
    # Drop tables in correct order to handle foreign key constraints
    tables_to_drop = [
        'consensus_alert_queue',
        'user_stock_alert_preferences', 
        'notification_templates',
        'alert_rules',
        'alert_types',
        'consensus_change_events',
        'stock_consensus_history',
        'consensus_update_schedule',
        'stock_grade_consensus',
        'grade_change_events',
        'stock_grades',
        'data_source_mappings',
        'analyst_firm_rankings'
    ]
    
    for table in tables_to_drop:
        try:
            db.execute_update(f'DROP TABLE IF EXISTS {table} CASCADE')
            print(f'✅ Dropped table: {table}')
        except Exception as e:
            print(f'⚠️  Could not drop {table}: {e}')
    
    # Drop functions
    functions_to_drop = [
        'trigger_grade_change_event',
        'trigger_consensus_change_event', 
        'queue_consensus_alert',
        'refresh_consensus_views',
        'schedule_consensus_view_refresh',
        'update_updated_at_column'
    ]
    
    for func in functions_to_drop:
        try:
            db.execute_update(f'DROP FUNCTION IF EXISTS {func}() CASCADE')
            print(f'✅ Dropped function: {func}')
        except Exception as e:
            print(f'⚠️  Could not drop function {func}: {e}')
    
    print('✅ Cleanup completed')
    
except Exception as e:
    print(f'❌ Cleanup failed: {e}')
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ Cleanup failed"
    exit 1
fi

echo ""
echo "🚀 Running fresh migration..."

# Run the migration
./migrate_stock_grades.sh

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Stock grades system successfully cleaned and migrated!"
    echo ""
    echo "📋 Next Steps:"
    echo "   1. Start API server: python start_api_server.py"
    echo "   2. Test endpoints: curl http://localhost:8001/api/v2/stock-grades/coverage-stats"
    echo "   3. Load sample data: curl -X POST http://localhost:8001/api/v2/stock-grades/refresh/AAPL"
else
    echo ""
    echo "❌ Migration failed after cleanup"
    exit 1
fi
