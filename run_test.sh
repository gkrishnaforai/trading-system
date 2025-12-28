#!/bin/bash
# Helper script to run workflow tests

set -e

echo "🔧 Copying test scripts to container..."
docker cp test_workflow_stages.py trading-system-python-worker:/app/test_workflow_stages.py
docker cp verify_workflow_data.py trading-system-python-worker:/app/verify_workflow_data.py

echo ""
echo "🚀 Running comprehensive workflow test..."
docker exec -it trading-system-python-worker python3 /app/test_workflow_stages.py

