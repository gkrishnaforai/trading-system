#!/bin/bash
# Quick Docker Setup Verification
# Run this after Docker Desktop is restarted

echo "🐳 Docker Setup Verification"
echo "=========================="

# Test Docker connection
echo "1. Testing Docker daemon..."
if docker ps > /dev/null 2>&1; then
    echo "✅ Docker daemon is running"
else
    echo "❌ Docker daemon is not responding"
    echo "Please restart Docker Desktop and try again"
    exit 1
fi

# Test docker-compose
echo ""
echo "2. Testing docker-compose..."
if docker-compose --version > /dev/null 2>&1; then
    echo "✅ docker-compose is available"
else
    echo "❌ docker-compose not available"
    exit 1
fi

# Validate our configuration
echo ""
echo "3. Validating trading system configuration..."
if docker-compose config > /dev/null 2>&1; then
    echo "✅ docker-compose.yml is valid"
else
    echo "❌ docker-compose.yml has errors"
    exit 1
fi

# Show what will be started
echo ""
echo "4. Services that will be started:"
docker-compose config --services

echo ""
echo "=========================="
echo "✅ Ready to start services!"
echo ""
echo "Run: docker-compose up -d"
echo ""
echo "Access points:"
echo "- Go API: http://localhost:8000"
echo "- Python Worker API: http://localhost:8001" 
echo "- Admin Dashboard: http://localhost:8502"
echo "- API Docs: http://localhost:8001/docs"
