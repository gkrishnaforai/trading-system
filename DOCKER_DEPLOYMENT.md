# 🐳 Docker Deployment Guide

## 📋 Prerequisites

- Docker and docker-compose installed
- Sufficient system resources (4GB+ RAM recommended)
- API keys for data providers (optional for testing)

## 🚀 Quick Start

### 1. Environment Setup
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configuration
nano .env
```

### 2. Start All Services
```bash
# Start all core services
docker-compose up -d

# Or start specific services
docker-compose up -d postgres redis go-api python-worker

# Include admin dashboard
docker-compose up -d postgres redis go-api python-worker admin-dashboard
```

### 3. Verify Deployment
```bash
# Check all services are running
docker-compose ps

# Check logs
docker-compose logs -f

# Test endpoints
curl http://localhost:8000/health  # Go API
curl http://localhost:8001/health  # Python Worker API
```

## 🏗️ Service Architecture

### Core Services
- **postgres**: PostgreSQL database (port 5432)
- **redis**: Redis cache and queue (port 6379)
- **go-api**: Client-facing API (port 8000)
- **python-worker**: Data processing API (port 8001)

### Optional Services
- **admin-dashboard**: StreamLit admin interface (port 8502)
- **streamlit**: Legacy dashboard (port 8501)
- **frontend**: Next.js frontend (port 3000, with --profile nextjs)

## 📊 Access Points

| Service | URL | Description |
|---------|-----|-------------|
| Go API | http://localhost:8000 | Client-facing REST API |
| Go API gRPC | localhost:50051 | gRPC endpoint |
| Python Worker API | http://localhost:8001 | Data processing API |
| Python Worker Docs | http://localhost:8001/docs | FastAPI documentation |
| Admin Dashboard | http://localhost:8502 | Administrative interface |
| PostgreSQL | localhost:5432 | Database |
| Redis | localhost:6379 | Cache/Queue |

## 🔧 Configuration

### Environment Variables

#### Database
```bash
DATABASE_URL=postgresql://trading:trading-dev@postgres:5432/trading-system?sslmode=disable
POSTGRES_USER=trading
POSTGRES_PASSWORD=trading-dev
POSTGRES_DB=trading-system
```

#### Data Providers
```bash
# Massive.com (premium data)
MASSIVE_API_KEY=your-massive-api-key
MASSIVE_ENABLED=true

# Alpha Vantage (free tier)
ALPHAVANTAGE_API_KEY=your-alphavantage-api-key

# Provider selection
PRIMARY_DATA_PROVIDER=massive
FALLBACK_DATA_PROVIDER=yahoo_finance
DEFAULT_DATA_PROVIDER=fallback
```

#### LLM Services
```bash
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
```

### Service URLs
```bash
PYTHON_WORKER_URL=http://python-worker:8001
REDIS_URL=redis://redis:6379/0
```

## 🎯 Deployment Options

### Development Mode
```bash
# Start with development settings
ENVIRONMENT=development docker-compose up -d
```

### Production Mode
```bash
# Start with production settings
ENVIRONMENT=production docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Scaling Workers
```bash
# Start additional Python workers
docker-compose --profile workers up -d

# Scale specific services
docker-compose up -d --scale python-worker=3
```

## 🔍 Monitoring & Logs

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f python-worker
docker-compose logs -f go-api

# Last 100 lines
docker-compose logs --tail=100 -f
```

### Health Checks
```bash
# Check service health
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8001/admin/health

# Docker health status
docker-compose ps
```

### Database Access
```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U trading -d trading-system

# View tables
\dt

# Check data
SELECT COUNT(*) FROM raw_market_data_daily;
```

## 🛠️ Troubleshooting

### Common Issues

#### Port Conflicts
```bash
# Check what's using ports
lsof -i :8000
lsof -i :8001

# Kill conflicting processes
sudo lsof -ti:8000 | xargs kill -9
```

#### Database Connection Issues
```bash
# Reset database
docker-compose down
docker volume rm trading-system_postgres_data
docker-compose up -d postgres

# Wait for database to be ready
docker-compose logs -f postgres
```

#### API Not Responding
```bash
# Restart specific service
docker-compose restart python-worker
docker-compose restart go-api

# Check service logs
docker-compose logs python-worker
```

### Performance Issues

#### High Memory Usage
```bash
# Check resource usage
docker stats

# Adjust limits in docker-compose.yml
deploy:
  resources:
    limits:
      memory: 2.0G
```

#### Slow API Response
```bash
# Check database connections
docker-compose exec postgres psql -U trading -d trading-system -c "SELECT count(*) FROM pg_stat_activity;"

# Clear Redis cache
docker-compose exec redis redis-cli FLUSHALL
```

## 🔄 Updates & Maintenance

### Update Services
```bash
# Pull latest images
docker-compose pull

# Rebuild local images
docker-compose build --no-cache

# Restart with updates
docker-compose up -d --force-recreate
```

### Backup Data
```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U trading trading-system > backup.sql

# Backup Redis
docker-compose exec redis redis-cli BGSAVE
```

### Clean Up
```bash
# Remove unused containers
docker container prune

# Remove unused images
docker image prune

# Clean volumes (caution!)
docker volume prune
```

## 🌐 Production Considerations

### Security
- Change default passwords
- Use HTTPS with SSL certificates
- Enable authentication
- Configure firewall rules

### Performance
- Use external PostgreSQL for production
- Configure Redis persistence
- Enable caching headers
- Use load balancer for scaling

### Monitoring
- Set up log aggregation
- Configure metrics collection
- Set up alerting
- Monitor resource usage

## 📞 Support

For issues:
1. Check logs: `docker-compose logs`
2. Verify configuration: `docker-compose config`
3. Test connectivity: `curl http://localhost:8000/health`
4. Review this guide and troubleshooting section

## ✅ Deployment Checklist

- [ ] Environment variables configured
- [ ] API keys added (if using premium data)
- [ ] Docker and docker-compose installed
- [ ] Sufficient system resources
- [ ] Ports 8000, 8001, 5432, 6379 available
- [ ] Run deployment test: `./test-docker-deployment.sh`
- [ ] Start services: `docker-compose up -d`
- [ ] Verify all services healthy
- [ ] Test API endpoints
- [ ] Access admin dashboard

Ready for production! 🚀
