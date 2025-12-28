# Supabase Troubleshooting Guide

## Common Issues

### 1. Storage Image Not Found

**Error:**
```
Error: failed to resolve reference "docker.io/supabase/storage-api:v1.7.5": not found
```

**Solution:**
Storage service is now optional and commented out in `docker-compose.supabase.yml`. The core database functionality (PostgreSQL, Auth, PostgREST, Realtime) works without storage.

If you need storage:
1. Check available image versions: https://hub.docker.com/r/supabase/storage-api/tags
2. Uncomment the storage service in `docker-compose.supabase.yml`
3. Update the image version to an available tag

### 2. Version Warning

**Warning:**
```
WARN[0000] the attribute `version` is obsolete
```

**Solution:**
The `version` field has been removed from `docker-compose.supabase.yml`. This warning can be ignored or the file has already been updated.

### 3. Cannot Connect to Database

**Error:**
```
Cannot connect to database
```

**Solution:**
```bash
# Check if Supabase is running
docker-compose -f docker-compose.supabase.yml ps

# Check database logs
docker-compose -f docker-compose.supabase.yml logs supabase-db

# Restart services
docker-compose -f docker-compose.supabase.yml restart
```

### 4. Port Already in Use

**Error:**
```
Bind for 0.0.0.0:54322 failed: port is already allocated
```

**Solution:**
```bash
# Change port in .env file
SUPABASE_DB_PORT=54323

# Or stop conflicting service
docker ps | grep 54322
docker stop <container_id>
```

### 5. Migration Errors

**Error:**
```
relation "users" already exists
```

**Solution:**
Migrations are idempotent (safe to run multiple times). If you see this, the table already exists. You can:
- Ignore the warning (table already created)
- Or reset the database:
  ```bash
  docker-compose -f docker-compose.supabase.yml down -v
  docker-compose -f docker-compose.supabase.yml up -d
  ./supabase/scripts/create_tables.sh
  ```

### 6. psql Not Found

**Error:**
```
psql: command not found
```

**Solution:**
Install PostgreSQL client:
```bash
# macOS
brew install postgresql

# Ubuntu/Debian
sudo apt-get install postgresql-client

# Or use Docker
docker run -it --rm postgres:15 psql -h host.docker.internal -p 54322 -U postgres -d postgres
```

## Image Version Updates

If you encounter image version issues, check available versions:

- **PostgreSQL**: https://hub.docker.com/r/supabase/postgres/tags
- **GoTrue**: https://hub.docker.com/r/supabase/gotrue/tags
- **PostgREST**: https://hub.docker.com/r/postgrest/postgrest/tags
- **Realtime**: https://hub.docker.com/r/supabase/realtime/tags
- **Storage**: https://hub.docker.com/r/supabase/storage-api/tags

Update versions in `docker-compose.supabase.yml` as needed.

## Reset Everything

If you need to start completely fresh:

```bash
# Stop and remove all containers and volumes
docker-compose -f docker-compose.supabase.yml down -v

# Remove any orphaned containers
docker ps -a | grep supabase
docker rm -f <container_ids>

# Start fresh
make supabase-setup
```

## Health Checks

Check service health:

```bash
# Database
docker exec trading-system-supabase-db pg_isready -U postgres

# Auth
curl http://localhost:9999/health

# REST API
curl http://localhost:3000/

# Realtime
curl http://localhost:4000/api/health
```

## Getting Help

1. Check service logs: `docker-compose -f docker-compose.supabase.yml logs <service-name>`
2. Check Docker status: `docker-compose -f docker-compose.supabase.yml ps`
3. Verify environment variables in `.env` file
4. Check Supabase documentation: https://supabase.com/docs/guides/hosting/docker

