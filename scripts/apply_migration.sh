#!/usr/bin/env bash
# Apply a single supabase migration to the VPS Postgres container and
# mark it applied in schema_migrations (so worker startup skips it).
#
# Usage:  ./scripts/apply_migration.sh 142_fv_decision_layer.sql
# Env:    VPS_HOST (default root@86.38.205.58), DB_NAME, DB_USER,
#         PG_CONTAINER (default: auto-detect 'postgres' container)
set -euo pipefail

MIGRATION="${1:?usage: apply_migration.sh <migration_file.sql>}"
HOST="${VPS_HOST:-root@86.38.205.58}"
DB="${DB_NAME:-trading_system}"
DBUSER="${DB_USER:-trading}"
FILE="supabase/migrations/${MIGRATION}"

[[ -f "$FILE" ]] || { echo "❌ not found: $FILE"; exit 1; }

echo "🔍 resolving postgres container on $HOST…"
PG="${PG_CONTAINER:-$(ssh -o BatchMode=yes "$HOST" \
  "docker ps --format '{{.Names}}' | grep -iE 'postgres' | head -1")}"
[[ -n "$PG" ]] || { echo "❌ no postgres container running on $HOST"; exit 1; }
echo "   container: $PG  ·  db: $DB  ·  user: $DBUSER"

echo "▶ applying $MIGRATION…"
ssh -o BatchMode=yes "$HOST" \
  "docker exec -i $PG psql -U $DBUSER -d $DB -v ON_ERROR_STOP=1" < "$FILE"

echo "▶ marking applied in schema_migrations…"
ssh -o BatchMode=yes "$HOST" \
  "docker exec -i $PG psql -U $DBUSER -d $DB -c \
   \"INSERT INTO schema_migrations (migration_name) \
    VALUES ('$MIGRATION') ON CONFLICT DO NOTHING;\""

echo "✅ $MIGRATION applied — verify:"
ssh -o BatchMode=yes "$HOST" \
  "docker exec -i $PG psql -U $DBUSER -d $DB -c \
   \"SELECT migration_name, applied_at FROM schema_migrations \
    WHERE migration_name='$MIGRATION';\""
