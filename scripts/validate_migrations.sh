#!/usr/bin/env bash
set -euo pipefail

# Validates db/migrations/*.sql against a fresh Postgres container.
# - Fails fast on the first SQL error.
# - Does NOT touch your existing docker-compose Postgres volume.
#
# Usage:
#   ./scripts/validate_migrations.sh
#   ./scripts/validate_migrations.sh --keep
#   ./scripts/validate_migrations.sh --dump-schema ./db/final_schema.sql

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATIONS_DIR="$ROOT_DIR/db/migrations"

CONTAINER_NAME="trading-system-migrations-test"
PG_USER="trading"
PG_PASSWORD="trading-dev"
PG_DB="trading_system"
PG_PORT_HOST="55432"

KEEP_CONTAINER="false"
DUMP_SCHEMA_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep)
      KEEP_CONTAINER="true"
      shift
      ;;
    --dump-schema)
      DUMP_SCHEMA_PATH="${2:-}"
      if [[ -z "$DUMP_SCHEMA_PATH" ]]; then
        echo "--dump-schema requires a path argument" >&2
        exit 2
      fi
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ ! -d "$MIGRATIONS_DIR" ]]; then
  echo "Migrations directory not found: $MIGRATIONS_DIR" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found on PATH" >&2
  exit 1
fi

echo "==> Validating migrations in: $MIGRATIONS_DIR"

cleanup() {
  if [[ "$KEEP_CONTAINER" == "true" ]]; then
    echo "==> Keeping container '$CONTAINER_NAME' running (as requested)."
    echo "    Connect with: docker exec -it $CONTAINER_NAME psql -U $PG_USER -d $PG_DB"
    return
  fi

  echo "==> Cleaning up container '$CONTAINER_NAME'"
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Remove any previous container with same name
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

echo "==> Starting fresh Postgres container..."
docker run -d \
  --name "$CONTAINER_NAME" \
  -e POSTGRES_USER="$PG_USER" \
  -e POSTGRES_PASSWORD="$PG_PASSWORD" \
  -e POSTGRES_DB="$PG_DB" \
  -p "$PG_PORT_HOST":5432 \
  -v "$MIGRATIONS_DIR":/migrations:ro \
  postgres:15-alpine \
  >/dev/null

echo "==> Waiting for Postgres to become ready..."
for _ in $(seq 1 60); do
  if docker exec "$CONTAINER_NAME" pg_isready -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; then
    break
  fi
  sleep 1

done

if ! docker exec "$CONTAINER_NAME" pg_isready -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; then
  echo "Postgres did not become ready in time" >&2
  docker logs "$CONTAINER_NAME" | tail -200 >&2 || true
  exit 1
fi

echo "==> Applying migrations (fail-fast)..."
# Apply in filename sort order (001..019)
shopt -s nullglob
migration_files=("$MIGRATIONS_DIR"/*.sql)
shopt -u nullglob

if [[ ${#migration_files[@]} -eq 0 ]]; then
  echo "No migration files found in: $MIGRATIONS_DIR" >&2
  exit 1
fi

IFS=$'\n' migration_files_sorted=($(printf '%s\n' "${migration_files[@]}" | sort))
unset IFS

for host_path in "${migration_files_sorted[@]}"; do
  base="$(basename "$host_path")"
  echo "----> $base"
  docker exec -i "$CONTAINER_NAME" \
    psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 -f "/migrations/$base" \
    >/dev/null
done

echo "==> All migrations applied successfully."

if [[ -n "$DUMP_SCHEMA_PATH" ]]; then
  echo "==> Dumping final schema to: $DUMP_SCHEMA_PATH"
  mkdir -p "$(dirname "$DUMP_SCHEMA_PATH")"
  docker exec "$CONTAINER_NAME" \
    pg_dump -U "$PG_USER" -d "$PG_DB" --schema-only --no-owner --no-privileges \
    > "$DUMP_SCHEMA_PATH"
  echo "==> Schema dump complete."
fi

echo "==> OK"
