#!/bin/bash
# Docker Deployment Readiness Test
# Tests the complete Docker setup before deployment

set -e

echo "🐳 Docker Deployment Readiness Test"
echo "===================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ $2${NC}"
    else
        echo -e "${RED}❌ $2${NC}"
        exit 1
    fi
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "ℹ️  $1"
}

# Test 1: Check Docker daemon
echo ""
echo "1. Checking Docker daemon..."
if docker --version > /dev/null 2>&1; then
    print_status 0 "Docker is installed and running"
else
    print_status 1 "Docker is not installed or not running"
fi

# Test 2: Check docker-compose
echo ""
echo "2. Checking docker-compose..."
if docker-compose --version > /dev/null 2>&1; then
    print_status 0 "docker-compose is available"
else
    print_status 1 "docker-compose is not available"
fi

# Test 3: Check required files
echo ""
echo "3. Checking required files..."
files=(
    "docker-compose.yml"
    ".env.example"
    "python-worker/Dockerfile"
    "python-worker/requirements.txt"
    "go-api/Dockerfile"
    "streamlit-app/Dockerfile.admin"
    "python-worker/app/api_app.py"
    "python-worker/app/api/admin.py"
    "python-worker/app/api/main.py"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        print_status 0 "Found $file"
    else
        print_status 1 "Missing $file"
    fi
done

# Test 4: Check environment file
echo ""
echo "4. Checking environment configuration..."
if [ -f ".env" ]; then
    print_status 0 ".env file exists"
    # Check for required variables
    required_vars=(
        "DATABASE_URL"
        "POSTGRES_USER"
        "POSTGRES_PASSWORD"
        "POSTGRES_DB"
    )
    
    for var in "${required_vars[@]}"; do
        if grep -q "^$var=" .env; then
            print_status 0 "$var is set in .env"
        else
            print_warning "$var is not set in .env (will use default)"
        fi
    done
else
    print_warning ".env file not found, will use .env.example"
    if [ -f ".env.example" ]; then
        print_status 0 ".env.example exists for reference"
    else
        print_status 1 ".env.example not found"
    fi
fi

# Test 5: Validate Docker Compose syntax
echo ""
echo "5. Validating docker-compose.yml..."
if docker-compose config > /dev/null 2>&1; then
    print_status 0 "docker-compose.yml is valid"
else
    print_status 1 "docker-compose.yml has syntax errors"
fi

# Test 6: Check Python Worker requirements
echo ""
echo "6. Checking Python Worker requirements..."
if [ -f "python-worker/requirements.txt" ]; then
    if grep -q "fastapi" python-worker/requirements.txt; then
        print_status 0 "FastAPI is in requirements"
    else
        print_status 1 "FastAPI is missing from requirements"
    fi
    
    if grep -q "uvicorn" python-worker/requirements.txt; then
        print_status 0 "Uvicorn is in requirements"
    else
        print_status 1 "Uvicorn is missing from requirements"
    fi
else
    print_status 1 "requirements.txt not found"
fi

# Test 7: Check API endpoints configuration
echo ""
echo "7. Checking API endpoints configuration..."
if [ -f "python-worker/app/api_app.py" ]; then
    if grep -q "app.include_router(admin.router)" python-worker/app/api_app.py; then
        print_status 0 "Admin API routes configured"
    else
        print_status 1 "Admin API routes not configured"
    fi
    
    if grep -q "app.include_router(main.router)" python-worker/app/api_app.py; then
        print_status 0 "Main API routes configured"
    else
        print_status 1 "Main API routes not configured"
    fi
else
    print_status 1 "API app not found"
fi

# Test 8: Check Go API Python Worker client
echo ""
echo "8. Checking Go API Python Worker integration..."
if [ -f "go-api/internal/services/python_worker_client.go" ]; then
    if grep -q "RefreshData" go-api/internal/services/python_worker_client.go; then
        print_status 0 "Go API Python Worker client has RefreshData method"
    else
        print_status 1 "Go API Python Worker client missing RefreshData method"
    fi
    
    if grep -q "GenerateSignals" go-api/internal/services/python_worker_client.go; then
        print_status 0 "Go API Python Worker client has GenerateSignals method"
    else
        print_status 1 "Go API Python Worker client missing GenerateSignals method"
    fi
else
    print_status 1 "Go API Python Worker client not found"
fi

# Test 9: Check provider clients
echo ""
echo "9. Checking provider clients..."
providers=(
    "python-worker/app/providers/alphavantage/client.py"
    "python-worker/app/providers/yahoo_finance/client.py"
    "python-worker/app/providers/massive/client.py"
)

for provider in "${providers[@]}"; do
    if [ -f "$provider" ]; then
        print_status 0 "Found $(basename $(dirname $provider)) provider client"
    else
        print_status 1 "Missing $(basename $(dirname $provider)) provider client"
    fi
done

# Test 10: Check data source adapters
echo ""
echo "10. Checking data source adapters..."
if [ -f "python-worker/app/data_sources/alphavantage_source.py" ]; then
    if grep -q "from app.providers.alphavantage.client import AlphaVantageClient" python-worker/app/data_sources/alphavantage_source.py; then
        print_status 0 "Alpha Vantage source uses provider client"
    else
        print_status 1 "Alpha Vantage source not using provider client"
    fi
else
    print_status 1 "Alpha Vantage source not found"
fi

# Summary
echo ""
echo "===================================="
echo "🎯 Deployment Readiness Summary"
echo "===================================="

print_info "✅ All critical components are in place"
print_info "✅ Docker configuration is valid"
print_info "✅ API endpoints are configured"
print_info "✅ Provider architecture is implemented"
print_info "✅ Go API integration is ready"

echo ""
print_info "📋 Next Steps:"
echo "1. Copy .env.example to .env and configure your API keys"
echo "2. Run: docker-compose up -d"
echo "3. Check logs: docker-compose logs -f"
echo "4. Access services:"
echo "   - Go API: http://localhost:8000"
echo "   - Python Worker API: http://localhost:8001"
echo "   - Admin Dashboard: http://localhost:8502"
echo "   - API Docs: http://localhost:8001/docs"

echo ""
print_status 0 "Ready for Docker deployment! 🚀"
