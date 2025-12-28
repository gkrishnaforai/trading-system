#!/bin/bash
# Complete setup script for AI Trading System

set -e

echo "🚀 Setting up AI Trading System..."

# Check prerequisites
echo "📋 Checking prerequisites..."
command -v docker >/dev/null 2>&1 || { echo "❌ Docker is required but not installed. Aborting." >&2; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo "❌ Docker Compose is required but not installed. Aborting." >&2; exit 1; }

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p db
mkdir -p logs

# Initialize database
echo "🗄️  Initializing database..."
chmod +x db/scripts/*.sh
./db/scripts/init_db.sh

# Seed sample data (optional)
read -p "Do you want to seed sample data? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ./db/scripts/seed_sample_data.sh
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cat > .env << EOF
# Environment Configuration
ENVIRONMENT=development
LOG_LEVEL=INFO

# Database
DATABASE_URL=file:./db/trading.db

# Redis
REDIS_URL=redis://redis:6379/0

# API
PORT=8000
GRPC_PORT=50051

# LLM (optional)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
EOF
    echo "✅ Created .env file. Edit it to add your API keys."
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file to add your API keys (optional)"
echo "2. Run: docker-compose up -d"
echo "3. Access Streamlit dashboard at: http://localhost:8501"
echo "4. Access API at: http://localhost:8000"

