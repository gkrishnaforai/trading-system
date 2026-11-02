# custodian-watch

External container-health supervisor. Watches every compose-managed
container on the host, keeps its own SQLite state, emails on failure,
serves a tiny status API. Deliberately deployed **outside** the app it
monitors and outside Coolify — Coolify strips `/var/run/docker.sock`
binds from compose deployments, and a watchdog shouldn't die with the
thing it watches.

## Deploy (host, once)

```bash
cd /opt && git clone https://github.com/gkrishnaforai/trading-system.git
cd trading-system

# minimal env — the watcher only reads these (file is optional for
# startup, but without it there are no email alerts and the API is
# unauthenticated)
cat > .env <<'EOF'
POSTGRES_USER=trading
POSTGRES_PASSWORD=<db-password>
POSTGRES_DB=trading_system
PGBOUNCER_PORT=6432
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=<gmail-user>
SMTP_PASSWORD=<app-password>
ALERT_EMAIL=<where alerts go>
WATCH_TOKEN=<bearer token for the status API>
WATCH_HOST_PORT=8100
# optional: HEALTHCHECKS_URL=https://hc-ping.com/<uuid>  (dead-man switch)
EOF

docker compose -f custodian-watch/docker-compose.yml up -d --build
```

That's it — `restart: unless-stopped` keeps it up across reboots.
Update later with `git pull && docker compose -f custodian-watch/docker-compose.yml up -d --build`.

## Access

```
http://<host>:8100/?token=<WATCH_TOKEN>    HTML incident board
http://<host>:8100/incidents               JSON (Bearer token or ?token=)
http://<host>:8100/job-failures            scheduled-job failures + repair ledger
http://<host>:8100/containers              live docker state per service
http://<host>:8100/health                  public liveness
```

## What it detects

| signature | meaning |
|---|---|
| `container:<name>:unhealthy` | healthcheck failing — log tail attached, classified (migration fatal / OOM / port / disk) |
| `container:<name>:exited` | restart-policy container died with non-zero exit |
| `container:<name>:restart-loop` | restart count climbing while unhealthy |
| `stack:no-watched-containers` | no app containers at all (deploy wiped the stack) |
| `watch:docker-socket-unreachable` | the watcher itself is blind — check the sock mount |

## Scheduled-job auto-repair

The board's **scheduled jobs — failures & auto-repair** section joins
`job_runs` (the durable failure ledger) with `custodian_incidents` and
`custodian_actions`. The worker's in-process custodian is the repair
executor: it re-kicks failed jobs, retries up to 3 times with a 15-minute
cooldown, and marks the incident `escalated` when the failure persists
after the last retry. custodian-watch stays
read-only for job repair so it can still supervise when the worker is
partially degraded and so two processes cannot race the same restart.
`WATCH_JOB_REPAIR_HOURS` controls how much repair history the section
shows (default 24).

## If the Coolify copy is still running

Remove it — it was blind (no sock) and would only double-report.
`docker rm -f <coolify-watch-container>` or delete the app in Coolify.
