#!/bin/bash

# Quick test runner for fix verification
echo "🚀 Running fix verification tests..."

# Check if Python worker is running
if ! curl -s http://127.0.0.1:8001/health > /dev/null; then
    echo "❌ Python worker is not running at http://127.0.0.1:8001"
    echo "Please start the Python worker first:"
    echo "  cd /Users/krishnag/tools/trading-system/python-worker"
    echo "  python start_api_server.py"
    exit 1
fi

echo "✅ Python worker is running"

# Run the test script
cd /Users/krishnag/tools/trading-system/python-worker
python test_fixes.py

echo "✅ Test run completed"
