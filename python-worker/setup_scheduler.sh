#!/bin/bash

# Data Refresh Scheduler Database Setup Script
# Easy one-command setup for the scheduler database system

set -e  # Exit on any error

echo "🚀 Data Refresh Scheduler Database Setup"
echo "=========================================="

# Check if we're in the right directory
if [ ! -f "migrations/create_scheduler_tables.sql" ]; then
    echo "❌ Migration file not found!"
    echo "📁 Make sure you're running this from the python-worker directory"
    exit 1
fi

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "🔧 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies if needed
if [ ! -f "venv/pyvenv.cfg" ] || [ "requirements.txt" -nt "venv/pyvenv.cfg" ]; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

# Check database connection
echo "🔍 Checking database connection..."
python3 -c "
import sys
sys.path.insert(0, '.')
try:
    from app.database import db
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
    echo "❌ Database connection failed. Please check your DATABASE_URL configuration."
    exit 1
fi

# Run the setup script
echo "🗄️ Running database setup..."
python3 setup_scheduler_database.py

echo ""
echo "🎉 SETUP COMPLETED SUCCESSFULLY!"
echo ""
echo "📋 NEXT STEPS:"
echo "   1. Start the Python Worker:"
echo "      python start_api_server.py"
echo ""
echo "   2. Test the scheduler:"
echo "      curl http://localhost:8001/api/v1/scheduler/status"
echo ""
echo "   3. Start the scheduler:"
echo "      curl -X POST http://localhost:8001/api/v1/scheduler/start"
echo ""
echo "   4. Schedule all symbols:"
echo "      curl -X POST http://localhost:8001/api/v1/scheduler/schedule-all"
echo ""
echo "🔧 Available API Endpoints:"
echo "   • POST /api/v1/scheduler/start"
echo "   • POST /api/v1/scheduler/stop"
echo "   • GET  /api/v1/scheduler/status"
echo "   • POST /api/v1/scheduler/schedule-all"
echo "   • GET  /api/v1/scheduler/upcoming"
echo "   • GET  /api/v1/scheduler/history"
echo ""
echo "📊 Database Views Created:"
echo "   • active_refresh_schedules - Current active schedules"
echo "   • daily_refresh_performance - Daily performance stats"
echo "   • symbol_refresh_summary - Symbol performance summary"
echo ""
echo "✅ Your database is now ready for automated data refresh scheduling!"
