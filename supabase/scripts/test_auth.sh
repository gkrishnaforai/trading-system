#!/bin/bash
# Test Supabase Auth (GoTrue) service
# Checks if auth service is running and accessible

set -e

CONTAINER_NAME="${CONTAINER_NAME:-trading-system-supabase-auth}"
AUTH_PORT="${SUPABASE_AUTH_PORT:-9999}"

echo "🔐 Testing Supabase Auth service..."
echo "   Container: $CONTAINER_NAME"
echo "   Port: $AUTH_PORT"
echo ""

# Check if container is running
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "❌ Auth container is not running."
    echo "   Start it with: docker-compose -f docker-compose.supabase.yml up -d supabase-auth"
    exit 1
fi

echo "✅ Auth container is running"
echo ""

# Test health endpoint
echo "🔌 Testing health endpoint..."
if curl -f -s "http://localhost:$AUTH_PORT/health" > /dev/null 2>&1; then
    echo "✅ Auth service is healthy"
    echo ""
    echo "📋 Auth endpoints available:"
    echo "   - Health: http://localhost:$AUTH_PORT/health"
    echo "   - Sign up: POST http://localhost:$AUTH_PORT/signup"
    echo "   - Sign in: POST http://localhost:$AUTH_PORT/token"
    echo "   - User info: GET http://localhost:$AUTH_PORT/user"
else
    echo "❌ Auth service health check failed"
    echo "   Check logs: docker logs $CONTAINER_NAME"
    exit 1
fi

echo ""
echo "💡 To test authentication:"
echo "   curl -X POST http://localhost:$AUTH_PORT/signup \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"email\":\"test@example.com\",\"password\":\"password123\"}'"

