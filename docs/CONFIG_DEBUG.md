# Configuration Debugging Guide

## Issue: MASSIVE_ENABLED not being read from .env

### How Configuration is Read

1. **`.env` file** (project root) → Contains `MASSIVE_ENABLED=true`
2. **`docker-compose.yml`** → Must pass environment variables to containers
3. **Container environment** → Python app reads from environment variables
4. **`pydantic-settings`** → Parses environment variables into Settings class

### The Problem

The issue is that **Docker Compose doesn't automatically pass all `.env` variables to containers**. You must explicitly list them in `docker-compose.yml`.

### Solution

I've updated `docker-compose.yml` to include:
```yaml
environment:
  - MASSIVE_API_KEY=${MASSIVE_API_KEY:-}
  - MASSIVE_ENABLED=${MASSIVE_ENABLED:-false}
  - MASSIVE_RATE_LIMIT_CALLS=${MASSIVE_RATE_LIMIT_CALLS:-4}
  - MASSIVE_RATE_LIMIT_WINDOW=${MASSIVE_RATE_LIMIT_WINDOW:-60.0}
  - PRIMARY_DATA_PROVIDER=${PRIMARY_DATA_PROVIDER:-}
  - FALLBACK_DATA_PROVIDER=${FALLBACK_DATA_PROVIDER:-}
  - DEFAULT_DATA_PROVIDER=${DEFAULT_DATA_PROVIDER:-fallback}
```

### How to Verify

1. **Check `.env` file** (in project root):
   ```bash
   cat .env | grep MASSIVE
   ```
   Should show:
   ```
   MASSIVE_ENABLED=true
   MASSIVE_API_KEY=your_key_here
   ```

2. **Check Docker container environment**:
   ```bash
   docker exec trading-system-python-worker env | grep MASSIVE
   ```
   Should show:
   ```
   MASSIVE_ENABLED=true
   MASSIVE_API_KEY=your_key_here
   ```

3. **Run diagnostic script** (inside container):
   ```bash
   docker exec trading-system-python-worker python test_config_reading.py
   ```

4. **Check API endpoint**:
   ```bash
   curl http://localhost:8001/api/v1/data-source/config
   ```
   Should show:
   ```json
   {
     "massive_enabled": true,
     "massive_configured": true,
     "primary_source": "massive",
     ...
   }
   ```

### Boolean Values in .env

Pydantic v2 automatically parses these as `True`:
- `true` (lowercase)
- `True` (capitalized)
- `TRUE` (uppercase)
- `1`
- `yes`
- `on`

These are parsed as `False`:
- `false` (lowercase)
- `False` (capitalized)
- `FALSE` (uppercase)
- `0`
- `no`
- `off`
- (empty string)

### After Making Changes

1. **Restart containers**:
   ```bash
   docker-compose restart python-worker
   ```

2. **Or rebuild** (if code changed):
   ```bash
   docker-compose up -d --build python-worker
   ```

### Common Issues

1. **Variable not in docker-compose.yml**: Add it to the `environment` section
2. **Wrong case**: Use `MASSIVE_ENABLED` (uppercase) in `.env` and `docker-compose.yml`
3. **Container not restarted**: Restart after changing `.env` or `docker-compose.yml`
4. **.env file location**: Must be in project root (same directory as `docker-compose.yml`)

