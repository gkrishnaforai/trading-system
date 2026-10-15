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

# minimal env — the watcher only reads these
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

## If the Coolify copy is still running

Remove it — it was blind (no sock) and would only double-report.
`docker rm -f <coolify-watch-container>` or delete the app in Coolify.
