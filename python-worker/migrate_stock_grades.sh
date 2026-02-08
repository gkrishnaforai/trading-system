#!/bin/bash
# Stock Grades Migration Wrapper Script
# Easy-to-use wrapper for running stock grades database migrations

set -e  # Exit on any error

echo "🚀 Stock Grades Database Migration Runner"
echo "=========================================="

# Check if we're in the right directory
if [ ! -f "run_stock_grades_migrations.py" ]; then
    echo "❌ Error: Please run this script from the python-worker directory"
    echo "   Current directory: $(pwd)"
    exit 1
fi

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "⚠️  Warning: No virtual environment detected"
    echo "   Consider activating: source venv/bin/activate"
fi

# Check database connection
echo "🔍 Checking database connection..."
python -c "
import sys
sys.path.insert(0, '.')
try:
    from app.database import get_db
    db = get_db()
    # Use synchronous query for connection test
    result = db.execute_query('SELECT 1 as test')
    if result and result[0]['test'] == 1:
        print('✅ Database connection verified')
    else:
        print('❌ Database connection failed')
        sys.exit(1)
except Exception as e:
    print(f'❌ Database connection error: {e}')
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ Database connection failed. Please check your DATABASE_URL"
    exit 1
fi

# Parse command line arguments
FORCE_FLAG=""
DRY_RUN_FLAG=""
VERIFY_FLAG=""

for arg in "$@"; do
    case $arg in
        --force)
            FORCE_FLAG="--force"
            ;;
        --dry-run)
            DRY_RUN_FLAG="--dry-run"
            ;;
        --verify-only)
            VERIFY_FLAG="--verify-only"
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --force        Continue despite errors"
            echo "  --dry-run       Show what would be executed without running"
            echo "  --verify-only   Only verify existing migration"
            echo "  --help          Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                    # Run migrations normally"
            echo "  $0 --force           # Run despite errors"
            echo "  $0 --dry-run         # Preview migrations"
            echo "  $0 --verify-only     # Check existing migration"
            exit 0
            ;;
        *)
            echo "❌ Unknown option: $arg"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Run the migration
echo "🔄 Running stock grades migrations..."
echo "   Command: python run_stock_grades_migrations.py $FORCE_FLAG $DRY_RUN_FLAG $VERIFY_FLAG"
echo ""

python run_stock_grades_migrations.py $FORCE_FLAG $DRY_RUN_FLAG $VERIFY_FLAG

# Check result
if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Migration completed successfully!"
    echo ""
    echo "📋 Next Steps:"
    echo "   1. Start API server: python start_api_server.py"
    echo "   2. Test endpoints: curl http://localhost:8001/api/v2/stock-grades/coverage-stats"
    echo "   3. Load sample data: curl -X POST http://localhost:8001/api/v2/stock-grades/refresh/AAPL"
    echo ""
    echo "📚 Documentation: See STOCK_GRADES_SYSTEM.md for detailed usage"
else
    echo ""
    echo "❌ Migration failed!"
    echo ""
    echo "🔧 Troubleshooting:"
    echo "   1. Check database connection: psql \$DATABASE_URL -c 'SELECT 1;'"
    echo "   2. Check logs for detailed error messages"
    echo "   3. Try with --force flag if appropriate"
    echo "   4. See STOCK_GRADES_SYSTEM.md for help"
    exit 1
fi
