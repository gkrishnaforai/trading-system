#!/bin/bash

# Trading System Admin Dashboard - Quick Start Script

echo "🚀 Starting Trading System Admin Dashboard..."
echo "=========================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# Set environment variables if not set
if [ -z "$PYTHON_API_URL" ]; then
    export PYTHON_API_URL="http://localhost:8001"
fi

if [ -z "$GO_API_URL" ]; then
    export GO_API_URL="http://localhost:8000"
fi

echo "📊 Configuration:"
echo "  - Python API URL: $PYTHON_API_URL"
echo "  - Go API URL: $GO_API_URL"
echo ""

# Check if we want to run with or without backend services
echo "Choose deployment mode:"
echo "1) Admin Dashboard Only (requires external APIs)"
echo "2) Full Stack (includes databases and APIs)"
echo ""

read -p "Enter choice (1 or 2): " choice

case $choice in
    1)
        echo "🎯 Starting Admin Dashboard Only..."
        echo "Access the dashboard at: http://localhost:8501"
        echo ""
        echo "⚠️  Make sure your backend services are running at:"
        echo "  - Python API: $PYTHON_API_URL"
        echo "  - Go API: $GO_API_URL"
        echo ""
        
        # Run just the admin dashboard
        streamlit run admin_main.py --server.port=8501 --server.address=0.0.0.0
        ;;
    2)
        echo "🏗️  Starting Full Stack Services..."
        echo "This will start:"
        echo "  - PostgreSQL Database"
        echo "  - Python Worker API"
        echo "  - Go API"
        echo "  - Admin Dashboard"
        echo ""
        echo "Access the dashboard at: http://localhost:8501"
        echo ""
        
        # Run full stack with docker-compose
        docker-compose -f docker-compose.admin.yml up --build
        ;;
    *)
        echo "❌ Invalid choice. Please run the script again."
        exit 1
        ;;
esac
