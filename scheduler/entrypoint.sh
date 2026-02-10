#!/usr/bin/env bash
set -euo pipefail

GO_API_URL="${GO_API_URL:-http://go-api:8000}"
INTERVAL="${SCHEDULER_TICK_INTERVAL_SECONDS:-30}"
LIMIT="${SCHEDULER_TICK_LIMIT:-25}"

if [[ -z "${GO_API_URL}" ]]; then
  echo "GO_API_URL is required"
  exit 1
fi

echo "⏰ Scheduler poller starting"
echo "- GO_API_URL: ${GO_API_URL}"
echo "- Interval: ${INTERVAL}s"
echo "- Limit: ${LIMIT}"

while true; do
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[$ts] tick"
  set +e
  curl -sS -X POST "${GO_API_URL}/api/v1/scheduler/tick?limit=${LIMIT}" -H 'Content-Type: application/json' -d '{}' || true
  echo ""
  set -e
  sleep "${INTERVAL}"
done
