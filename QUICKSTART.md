# Quick Start Guide

## 🚀 5-Minute Setup

### 1. Initialize Database

```bash
make init-db
make seed-db
```

### 2. Start Services

```bash
docker-compose up -d
```

### 3. Access Dashboard

- **Streamlit Dashboard**: http://localhost:8501
- **API**: http://localhost:8000/health

## 📊 Using the System

### Initial Data Setup

**Important**: Before using the system, you need to populate the database with market data:

```bash
# Option 1: Run batch worker to fetch data for all symbols in holdings
docker-compose exec python-worker python -m app.workers.batch_worker

# Option 2: Fetch data for a specific symbol manually
docker-compose exec python-worker python -c "
from app.database import init_database
from app.services.data_fetcher import DataFetcher
from app.services.indicator_service import IndicatorService

init_database()
df = DataFetcher()
is_service = IndicatorService()

# Fetch and save data
df.fetch_and_save_stock('AAPL')
is_service.calculate_indicators('AAPL')
"
```

### Streamlit Dashboard

1. Open http://localhost:8501
2. Select subscription level (basic/pro/elite) in sidebar
3. Enter stock symbol (e.g., AAPL, MSFT, GOOGL)
4. View:
   - Trading signals
   - Technical indicators
   - Charts with moving averages
   - Pullback zones (Pro/Elite)
   - Stop-loss levels (Pro/Elite)

### API Usage

#### Get Stock Data

```bash
curl "http://localhost:8000/api/v1/stock/AAPL?subscription_level=basic"
```

#### Get Trading Signal

```bash
curl "http://localhost:8000/api/v1/signal/AAPL?subscription_level=pro"
```

#### Get Portfolio

```bash
curl "http://localhost:8000/api/v1/portfolio/user1/portfolio1?subscription_level=basic"
```

## 🔄 Running Batch Jobs & On-Demand Data Fetch

### Automatic (Nightly)

The Python worker automatically runs nightly at 1 AM (configurable).

### On-Demand Historical Data Fetch

**Via Streamlit UI:**

1. Go to "Stock Analysis" or "Reports" page
2. Enter stock symbol
3. Click "📥 Fetch Data" button
4. Select period (1y, 6mo, 3mo, etc.)
5. Data and indicators will be fetched and calculated automatically

**Via Command Line:**

```bash
# Using Makefile
make fetch-data SYMBOL=AAPL PERIOD=1y

# Or directly
docker-compose exec python-worker python -c "
from app.database import init_database
from app.services.data_fetcher import DataFetcher
from app.services.indicator_service import IndicatorService

init_database()
df = DataFetcher()
df.fetch_and_save_stock('AAPL', period='1y')
is_service = IndicatorService()
is_service.calculate_indicators('AAPL')
"
```

**Via API:**

```bash
curl -X POST http://localhost:8001/api/v1/fetch-historical-data \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "period": "1y", "calculate_indicators": true}'
```

### Manual Batch Run

```bash
docker-compose exec python-worker python -c "from app.workers.batch_worker import BatchWorker; w = BatchWorker(); w.run_nightly_batch()"
```

Or trigger a one-time batch:

```bash
docker-compose exec python-worker python -c "from app.workers.batch_worker import BatchWorker; w = BatchWorker(); w.run_nightly_batch()"
```

## 🧪 Testing

```bash
# Python tests
make test

# Or individually
docker-compose exec python-worker pytest tests/ -v
```

## 📝 Sample Data

After running `make seed-db`, you'll have:

- **Users**: user1 (basic), user2 (pro), user3 (elite)
- **Portfolios**: portfolio1, portfolio2, portfolio3
- **Holdings**: Sample positions in AAPL, MSFT, GOOGL, TSLA

## 🔧 Troubleshooting

### Database not found

```bash
make init-db
```

### Services won't start

```bash
docker-compose down
docker-compose up -d --build
```

### Check logs

```bash
make logs
# Or specific service
docker-compose logs python-worker
docker-compose logs go-api
```

## 📚 Next Steps

1. **Add your API keys** in `.env` for LLM features
2. **Run batch job** to fetch real market data
3. **Explore the dashboard** with different subscription levels
4. **Review the code** to understand the architecture
5. **Customize indicators** in `python-worker/app/indicators/`
6. **Add new signals** in `python-worker/app/indicators/signals.py`

## 🎯 Subscription Tiers

| Feature            | Basic | Pro | Elite |
| ------------------ | ----- | --- | ----- |
| Core Signals       | ✅    | ✅  | ✅    |
| Basic Indicators   | ✅    | ✅  | ✅    |
| Momentum Scores    | ❌    | ✅  | ✅    |
| Pullback Zones     | ❌    | ✅  | ✅    |
| Stop-Loss          | ❌    | ✅  | ✅    |
| Options Strategies | ❌    | ❌  | ✅    |
| LLM Reports        | ❌    | ❌  | ✅    |
