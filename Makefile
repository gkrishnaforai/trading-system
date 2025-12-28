.PHONY: help build up down logs clean test proto setup init-db seed-db inspect-db query-db supabase-up supabase-down supabase-create-tables supabase-seed supabase-verify

help:
	@echo "AI Trading System - Available commands:"
	@echo "  make setup         - Complete setup (database, sample data)"
	@echo "  make build         - Build all Docker images"
	@echo "  make up            - Start all services"
	@echo "  make down          - Stop all services"
	@echo "  make logs          - View logs"
	@echo "  make clean         - Clean up containers and volumes"
	@echo "  make test          - Run tests"
	@echo "  make init-db       - Initialize database schema (SQLite)"
	@echo "  make seed-db       - Seed sample data (SQLite)"
	@echo "  make update-holdings - Update portfolio1 with default stocks"
	@echo "  make proto         - Generate Protocol Buffer code"
	@echo "  make fetch-data    - Fetch historical data (SYMBOL=AAPL PERIOD=1y)"
	@echo "  make inspect-db    - Show table summary (or TABLE=table_name for specific table)"
	@echo "  make query-db      - Run custom SQL query (QUERY=\"SELECT ...\")"
	@echo "  make view-fundamentals - View fundamentals for a symbol (SYMBOL=AAPL)"
	@echo "  make apply-migration-003 - Apply migration 003 (creates news/earnings/peers tables)"
	@echo "  make test-endpoints - Test all API endpoints (SYMBOL=AAPL)"
	@echo ""
	@echo "Supabase Commands:"
	@echo "  make supabase-up           - Start Supabase services"
	@echo "  make supabase-down         - Stop Supabase services"
	@echo "  make supabase-create-tables - Create all tables (one-time execution)"
	@echo "  make supabase-seed          - Seed sample data (one-time execution)"
	@echo "  make supabase-verify        - Verify tables and show row counts"
	@echo "  make supabase-setup         - Complete Supabase setup (up + create + seed + verify)"

setup:
	@./scripts/setup.sh

init-db:
	@./db/scripts/init_db.sh

seed-db:
	@./db/scripts/seed_sample_data.sh

seed-stocks:
	@echo "🌱 Seeding stock symbols and fetching data..."
	@docker-compose exec python-worker python db/scripts/seed_stock_symbols.py || \
		echo "⚠️ Note: Run 'make up' first to start services, then 'make seed-stocks'"

update-holdings:
	@./db/scripts/update_portfolio1_holdings.sh

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

clean:
	docker-compose down -v
	docker system prune -f

test:
	@echo "Running Python tests..."
	docker-compose exec python-worker pytest tests/ -v || echo "Python tests failed"
	@echo "Running Go tests..."
	docker-compose exec go-api go test ./... || echo "Go tests failed"

proto:
	# Generate Go code
	protoc --go_out=go-api/internal/grpc --go_opt=paths=source_relative \
		--go-grpc_out=go-api/internal/grpc --go-grpc_opt=paths=source_relative \
		proto/trading/v1/*.proto
	# Generate Python code
	python -m grpc_tools.protoc -Iproto --python_out=python-worker/app \
		--grpc_python_out=python-worker/app proto/trading/v1/*.proto

fetch-data:
	@if [ -z "$(SYMBOL)" ]; then \
		echo "Error: SYMBOL is required"; \
		echo "Usage: make fetch-data SYMBOL=AAPL [PERIOD=1y]"; \
		echo "Example: make fetch-data SYMBOL=AAPL PERIOD=1y"; \
		exit 1; \
	fi
	@PERIOD=$${PERIOD:-1y}; \
	docker-compose exec python-worker python -c "from app.database import init_database; from app.services.data_fetcher import DataFetcher; from app.services.indicator_service import IndicatorService; import sys; init_database(); df = DataFetcher(); success = df.fetch_and_save_stock('$(SYMBOL)', period='$$PERIOD'); is_service = IndicatorService(); is_service.calculate_indicators('$(SYMBOL)') if success else None; print('✅ Data fetched and indicators calculated' if success else '❌ Failed')"

inspect-db:
	@chmod +x scripts/inspect_db.sh
	@./scripts/inspect_db.sh $(TABLE)

query-db:
	@if [ -z "$(QUERY)" ]; then \
		echo "Error: QUERY is required"; \
		echo "Usage: make query-db QUERY=\"SELECT * FROM raw_market_data LIMIT 5;\""; \
		echo "Example: make query-db QUERY=\"SELECT stock_symbol, COUNT(*) FROM raw_market_data GROUP BY stock_symbol;\""; \
		exit 1; \
	fi
	@chmod +x scripts/query_db.sh
	@./scripts/query_db.sh "$(QUERY)"

view-fundamentals:
	@chmod +x scripts/view_fundamentals.sh
	@./scripts/view_fundamentals.sh $(SYMBOL)

apply-migration-003:
	@echo "📝 Applying migration 003 (news, earnings, industry_peers tables)..."
	@sqlite3 db/trading.db < db/migrations/003_add_news_earnings_industry.sql
	@echo "✅ Migration 003 applied successfully!"
	@echo "💡 Now refresh data again to populate the new tables:"
	@echo "   curl -X POST http://localhost:8001/api/v1/refresh-data -H 'Content-Type: application/json' -d '{\"symbol\": \"AAPL\", \"data_types\": [\"news\", \"earnings\", \"industry_peers\"], \"force\": true}'"

test-endpoints:
	@chmod +x scripts/test_all_endpoints.sh
	@./scripts/test_all_endpoints.sh $(SYMBOL)

# Supabase Commands
supabase-up:
	@echo "🚀 Starting Supabase services..."
	@docker-compose -f docker-compose.supabase.yml up -d
	@echo "✅ Supabase services started"
	@echo "💡 Wait a few seconds for services to be ready, then run: make supabase-create-tables"

supabase-down:
	@echo "🛑 Stopping Supabase services..."
	@docker-compose -f docker-compose.supabase.yml down
	@echo "✅ Supabase services stopped"

supabase-create-tables:
	@chmod +x supabase/scripts/create_tables.sh
	@./supabase/scripts/create_tables.sh

supabase-seed:
	@chmod +x supabase/scripts/seed_data.sh
	@./supabase/scripts/seed_data.sh

supabase-verify:
	@chmod +x supabase/scripts/verify_tables.sh
	@./supabase/scripts/verify_tables.sh

supabase-test-auth:
	@chmod +x supabase/scripts/test_auth.sh
	@./supabase/scripts/test_auth.sh

test-validation:
	@echo "🧪 Testing data validation system with TQQQ..."
	@docker-compose exec python-worker python scripts/test_validation.py || echo "⚠️ Services may not be running. Start with: docker-compose up -d"

supabase-setup:
	@echo "🚀 Complete Supabase setup..."
	@$(MAKE) supabase-up
	@echo "⏳ Waiting for database to be ready..."
	@sleep 5
	@$(MAKE) supabase-create-tables
	@$(MAKE) supabase-seed
	@$(MAKE) supabase-verify
	@echo "🎉 Supabase setup complete!"
