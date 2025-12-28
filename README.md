# AI Trading System

A full-stack AI-powered trading system with modular, scalable architecture supporting both Python and Go containers for optimal performance and AI capabilities.

## 🏗️ Architecture

### Containers

1. **Go API** (`go-api`)
   - Core trading engine: fast, concurrent, trend calculations, breakout detection
   - Exposes gRPC endpoints for Python worker
   - Manages portfolios, user profiles, CRUD, and DB interaction
   - REST API on port 8000, gRPC on port 50051

2. **Python AI/ML Worker** (`python-worker`)
   - LLM narrative generation
   - Fundamental analysis
   - Technical indicators: MACD, RSI, ATR calculations
   - Communicates via gRPC with Go API

3. **Optional Workers** (`python-worker-2`, etc.)
   - For scaling intensive AI/ML jobs
   - Queue-based async tasks (Redis)
   - Start with: `docker-compose --profile workers up`

4. **Database**
   - SQLite (development) - default
   - PostgreSQL (production) - use `--profile postgres`
   - Supabase (production) - configure via environment variables

5. **Streamlit Dashboard** (`streamlit`) - **Initial UI**
   - Interactive trading dashboard
   - Stock analysis with charts
   - Portfolio view
   - Tiered subscription feature visibility
   - Accessible at http://localhost:8501

6. **Frontend** (`frontend`) - **Future migration to Next.js**
   - Next.js application
   - SEO pages per stock
   - Portfolio UI
   - Blog integration
   - Start with: `docker-compose --profile nextjs up`

7. **Redis**
   - Queue management
   - Caching layer for API responses

## 📊 Trading Strategy

### Trend & Signal Strategy

- **Long-term trend**: Price > 200-day MA / Golden Cross
- **Medium-term trend**: EMA20 vs SMA50 for context
- **Layered confirmation**: Trend + Momentum + Volume + Pullback

### Buy Signals
- Short EMA crosses above long EMA
- Long-term trend confirmed
- MACD positive
- RSI < 70
- Volume spikes
- Pullback zones
- Momentum aligned with trend

### Sell Signals
- Short EMA crosses below long EMA
- Momentum fading
- MACD backcross
- RSI < 50

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Go 1.21+ (for local development)
- Python 3.11+ (for local development)
- Node.js 18+ (for local development - optional, for Next.js frontend)

### Development Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd trading-system
   ```

2. **Initialize database**
   ```bash
   # Make scripts executable
   chmod +x db/scripts/*.sh
   
   # Initialize database schema
   ./db/scripts/init_db.sh
   
   # Seed sample data (optional)
   ./db/scripts/seed_sample_data.sh
   ```

3. **Create environment file** (optional, uses defaults)
   ```bash
   # Create .env file with your configuration
   # See .env.example for available options
   ```

4. **Start services (SQLite + Streamlit - default)**
   ```bash
   docker-compose up -d
   ```

5. **Access the dashboard**
   - Streamlit Dashboard: http://localhost:8501
   - Go API: http://localhost:8000
   - API Health: http://localhost:8000/health

6. **Start with PostgreSQL** (optional)
   ```bash
   docker-compose --profile postgres up -d
   ```

7. **Start with additional workers** (optional)
   ```bash
   docker-compose --profile workers up -d
   ```

### Environment Variables

See `.env.example` for all available configuration options.

Key variables:
- `DATABASE_URL` - SQLite path or PostgreSQL connection string
- `SUPABASE_URL` - Supabase project URL (for production)
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key
- `OPENAI_API_KEY` - OpenAI API key for LLM features
- `ANTHROPIC_API_KEY` - Anthropic API key (optional)
- `LITELLM_PROXY_URL` - LiteLLM proxy URL (optional)

## 📁 Project Structure

```
trading-system/
├── go-api/                 # Go backend
│   ├── cmd/api/           # API server entry point
│   ├── internal/
│   │   ├── handlers/       # HTTP handlers
│   │   ├── services/       # Business logic
│   │   ├── repositories/  # Data access
│   │   ├── models/        # Data models
│   │   └── grpc/          # gRPC service definitions
│   └── pkg/
│       ├── indicators/     # Technical indicators
│       └── signals/       # Trading signals
├── python-worker/          # Python AI/ML worker
│   ├── app/
│   │   ├── services/      # Business logic
│   │   ├── indicators/    # Technical indicators
│   │   ├── llm/           # LLM integration
│   │   └── workers/       # Background workers
│   └── tests/
├── frontend/               # Next.js frontend
│   ├── app/               # Next.js app directory
│   ├── components/        # React components
│   ├── lib/               # Utilities
│   └── public/            # Static assets
├── proto/                  # Protocol Buffer definitions
│   └── trading/v1/        # Trading service protos
├── db/                     # Database
│   ├── migrations/        # SQL migrations
│   └── scripts/           # DB scripts
├── docs/                   # Documentation
├── scripts/                # Utility scripts
└── config/                 # Configuration files
```

## 🔧 Development

### Go API

```bash
cd go-api
go mod init github.com/trading-system/go-api
go run cmd/api/main.go
```

### Python Worker

```bash
cd python-worker
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m app.workers.main
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## 🧪 Testing

```bash
# Run Python unit tests
cd python-worker
pytest tests/ -v

# Or using Docker
docker-compose exec python-worker pytest tests/ -v

# Run Go tests
cd go-api
go test ./...

# Or using Docker
docker-compose exec go-api go test ./...
```

### Test Coverage

- **Indicator Calculations**: Moving averages, RSI, MACD, ATR, Bollinger Bands
- **Signal Generation**: Buy/sell/hold logic, trend detection
- **Portfolio Service**: Signal generation, confidence calculation
- **Database Operations**: CRUD operations, queries

## 📋 Database Setup

### Initial Setup

```bash
# Initialize database schema
./db/scripts/init_db.sh

# Seed sample data
./db/scripts/seed_sample_data.sh
```

### Sample Data

The seed script creates:
- 3 sample users (basic, pro, elite subscriptions)
- 3 sample portfolios
- Sample holdings for testing

### Manual Database Access

```bash
# SQLite
sqlite3 db/trading.db

# PostgreSQL (if using postgres profile)
docker-compose exec postgres psql -U trading -d trading
```

## 🔄 Batch Processing

The Python worker runs a nightly batch job at 1 AM (configurable) that:

1. Fetches market data from Yahoo Finance
2. Calculates technical indicators
3. Generates portfolio signals
4. Updates Redis cache

To run batch manually:
```bash
docker-compose exec python-worker python -m app.workers.batch_worker
```

## 📊 API Endpoints

### Portfolio Endpoints

- `GET /api/v1/portfolio/:user_id/:portfolio_id?subscription_level=basic`
  - Returns portfolio with holdings and signals
  - Filters signals based on subscription level

### Stock Endpoints

- `GET /api/v1/stock/:symbol?subscription_level=basic`
  - Returns latest indicators and signals for a stock
  - Filters advanced metrics based on subscription level

- `GET /api/v1/signal/:symbol?subscription_level=basic`
  - Returns trading signal with explanation

### LLM Endpoints

- `GET /api/v1/llm_blog/:symbol`
  - Returns LLM-generated blog/report for a stock

## 🎯 Subscription Tiers

### Basic
- Core trading signals (buy/sell/hold)
- Basic indicators (MA, RSI, MACD)
- Long-term and medium-term trends

### Pro
- Everything in Basic
- Momentum scores
- Pullback zones
- Stop-loss calculations
- ATR-based risk metrics

### Elite
- Everything in Pro
- Advanced options strategies (covered calls, protective puts)
- Portfolio-level LLM reports
- Advanced fundamental analysis

## 🔧 Configuration

### Environment Variables

Key configuration options (see `.env.example`):

- `DATABASE_URL`: SQLite path or PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `OPENAI_API_KEY`: OpenAI API key for LLM features
- `BATCH_SCHEDULE_HOUR`: Hour for nightly batch (default: 1)
- `BATCH_SCHEDULE_MINUTE`: Minute for nightly batch (default: 0)

### Migration to Supabase

1. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `.env`
2. Update `DATABASE_URL` to Supabase PostgreSQL connection string
3. Run migrations on Supabase
4. Restart services

### Migration to Next.js Frontend

1. Start Next.js frontend: `docker-compose --profile nextjs up`
2. Update `NEXT_PUBLIC_API_URL` in frontend environment
3. Configure Supabase authentication (future)

## 📚 Documentation

- [Architecture Overview](docs/ARCHITECTURE.md)
- [API Documentation](docs/API.md)
- [Trading Strategy](docs/TRADING_STRATEGY.md)
- [Deployment Guide](docs/DEPLOYMENT.md)

## 🔐 Security

- JWT authentication via Supabase
- Environment variables for secrets
- Database connection pooling
- Rate limiting on API endpoints

## 📈 Scaling

- Horizontal scaling: Add more Python worker containers
- Queue-based task distribution via Redis
- Database connection pooling
- Caching layer (Redis)

## 🛠️ Tech Stack

- **Backend**: Go (Gin, gRPC, pgx)
- **AI/ML**: Python (LiteLLM, pandas, numpy)
- **Frontend**: Next.js 14+ (React, TypeScript)
- **Database**: SQLite (dev), PostgreSQL/Supabase (prod)
- **Queue**: Redis
- **Protocol**: gRPC, REST API

## 📝 License

[Your License Here]

## 🤝 Contributing

[Contributing guidelines]

## 📧 Contact

[Contact information]
