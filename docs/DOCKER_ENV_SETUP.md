# Docker Environment Variables Setup

## Overview

Docker Compose automatically reads variables from `.env` file in the project root when you use the `${VAR_NAME}` syntax in `docker-compose.yml`.

## How It Works

1. **`.env` file** (project root): Contains your environment variables
   ```bash
   FINNHUB_API_KEY=your_api_key_here
   OPENAI_API_KEY=your_openai_key
   ```

2. **`docker-compose.yml`**: References variables with `${VAR_NAME:-default}` syntax
   ```yaml
   environment:
     - FINNHUB_API_KEY=${FINNHUB_API_KEY:-}
   ```

3. **Docker Compose** automatically:
   - Reads `.env` file from project root
   - Substitutes `${VAR_NAME}` with values from `.env`
   - Passes them as environment variables to containers

## Current Configuration

### ✅ Python Worker Service

The `python-worker` service now includes:
- `FINNHUB_API_KEY=${FINNHUB_API_KEY:-}` - For analyst ratings

### All Environment Variables

The following variables are read from `.env`:

**Python Worker:**
- `FINNHUB_API_KEY` - Finnhub API key for analyst ratings
- `OPENAI_API_KEY` - OpenAI API key for LLM features
- `ANTHROPIC_API_KEY` - Anthropic API key for LLM features
- `LITELLM_PROXY_URL` - LiteLLM proxy URL
- `LITELLM_MASTER_KEY` - LiteLLM master key
- `DATABASE_URL` - Database connection string
- `SUPABASE_URL` - Supabase URL (if using Supabase)
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key
- `SUPABASE_DB_URL` - Supabase database URL

**Go API:**
- `DATABASE_URL` - Database connection string
- `SUPABASE_URL` - Supabase URL
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key
- `SUPABASE_DB_URL` - Supabase database URL
- `JWT_SECRET` - JWT secret for authentication

## Setup Instructions

### 1. Create/Edit `.env` File

Create `.env` file in project root (`/Users/krishnag/tools/trading-system/.env`):

```bash
# Analyst Ratings (Finnhub)
FINNHUB_API_KEY=your_finnhub_api_key_here

# LLM APIs (Optional)
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here

# Database (Optional - defaults to SQLite)
DATABASE_URL=sqlite:///./db/trading.db

# Supabase (Optional - for production)
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_key
SUPABASE_DB_URL=your_supabase_db_url
```

### 2. Restart Docker Containers

After updating `.env` or `docker-compose.yml`:

```bash
# Rebuild and restart containers
docker-compose down
docker-compose up -d --build

# Or just restart (if no code changes)
docker-compose restart python-worker
```

### 3. Verify Environment Variables

Check if variables are set in container:

```bash
# Check Python worker container
docker exec trading-system-python-worker env | grep FINNHUB_API_KEY

# Or check all environment variables
docker exec trading-system-python-worker env | grep -E "(FINNHUB|OPENAI|ANTHROPIC)"
```

### 4. Test Analyst Ratings

```bash
# Fetch ratings via API
curl -X POST http://localhost:8001/api/v1/stock/NVDA/analyst-ratings/fetch

# View ratings
curl http://localhost:8001/api/v1/stock/NVDA/analyst-ratings
```

## Important Notes

### ⚠️ Security

1. **Never commit `.env` to git** - It's already in `.gitignore`
2. **Use different keys for dev/prod** - Don't use production keys in development
3. **Rotate keys regularly** - Especially if exposed

### 📝 How Docker Compose Reads `.env`

- Docker Compose **automatically** reads `.env` from project root
- Variables are substituted when you use `${VAR_NAME}` syntax
- Default values can be set: `${VAR_NAME:-default_value}`
- If variable not in `.env`, it uses the default (or empty string)

### 🔄 Hot Reload

- **Environment variables**: Require container restart
- **Code changes**: Require rebuild (`docker-compose up -d --build`)
- **Config changes**: Require restart (`docker-compose restart`)

## Troubleshooting

### Variable Not Available in Container

1. **Check `.env` file exists** in project root
2. **Check variable name** matches exactly (case-sensitive in some cases)
3. **Restart container**: `docker-compose restart python-worker`
4. **Check logs**: `docker logs trading-system-python-worker`

### Variable Not Read from `.env`

1. **Verify syntax** in `docker-compose.yml`: `${VAR_NAME:-default}`
2. **Check `.env` format**: `VAR_NAME=value` (no spaces around `=`)
3. **Restart Docker Compose**: `docker-compose down && docker-compose up -d`

### Test Variable Access

```bash
# In Python worker container
docker exec -it trading-system-python-worker python -c "import os; print(os.getenv('FINNHUB_API_KEY'))"

# Should print your API key (or None if not set)
```

## Summary

✅ **`.env` file is automatically read** by Docker Compose
✅ **`FINNHUB_API_KEY` is now configured** in `docker-compose.yml`
✅ **Just add your key to `.env`** and restart containers
✅ **No need to copy `.env` into container** - Docker Compose handles it

