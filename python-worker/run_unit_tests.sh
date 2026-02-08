#!/bin/bash

echo "🚀 Running unit tests against PostgreSQL container..."

# Check if we can connect to PostgreSQL
echo "🔍 Checking PostgreSQL connection..."
cd /Users/krishnag/tools/trading-system/python-worker

python -c "
from app.database import db
try:
    result = db.execute_query('SELECT 1 as test')
    print('✅ PostgreSQL connection successful')
except Exception as e:
    print(f'❌ PostgreSQL connection failed: {e}')
    print('Please ensure PostgreSQL container is running and DATABASE_URL is set correctly')
    exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ Cannot connect to PostgreSQL. Please check your database connection."
    exit 1
fi

echo "✅ PostgreSQL connection verified"
echo ""

# Run the unit tests
python test_fixes_unit.py

echo ""
echo "✅ Unit test run completed"
