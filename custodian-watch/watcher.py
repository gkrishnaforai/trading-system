"""custodian-watch — the external supervisor sidecar.

The in-worker custodian (app/support/custodian.py) watches jobs and
data freshness from inside the system. This process watches the SYSTEM
itself from a separate container: container health, exits, restart
loops — including the failure modes that take the worker down with
them (deploy crash-loops, migration fatals, dead postgres).

Independence rules:
  - state lives in its own SQLite file on a named volume — works when
    the postgres pod is down
  - alerts go out over SMTP directly — no DB needed to notify
  - mirroring into postgres custodian_incidents is best-effort so the
    board still shows incidents when the DB is healthy
  - no depends_on — it must be up during deploys, watching

Sensors (docker socket, read-only):
  container:<name>:unhealthy    healthcheck failed
  container:<name>:exited       restart-policy container died (rc != 0)
  container:<name>:restart-loop restart_count climbing while not healthy

Notify: one email per incident (alerted_at gates repeats), then silent
until resolved-and-recurs. Optional HEALTHCHECKS_URL ping each pass =
dead-man's switch for host-level death.
"""
from __future__ import annotations

import http.client
import json
import logging
import os
import re
import smtplib
import socket
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s custodian-watch %(message)s")
logger = logging.getLogger("custodian-watch")

DOCKER_SOCK = os.getenv("DOCKER_SOCK", "/var/run/docker.sock")
# DOCKER_HOST=tcp://<socket-proxy>:2375 — read-only docker API through a
# socket-proxy sidecar, for platforms that strip the raw sock bind
DOCKER_HOST = os.getenv("DOCKER_HOST", "")
DB_PATH = os.getenv("WATCH_DB", "/data/custodian.db")
POLL_SECONDS = int(os.getenv("WATCH_POLL_SECONDS", "60"))
HEALTHCHECKS_URL = os.getenv("HEALTHCHECKS_URL", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
HEARTBEAT = "/data/heartbeat"
# PORT last: PaaS (Coolify) may inject its own routed port — honoring it
# makes the proxy<->listener agree without config drift.
WATCH_PORT = int(os.getenv("WATCH_PORT") or os.getenv("PORT") or "8100")
WATCH_TOKEN = os.getenv("WATCH_TOKEN", "")   # Bearer token for the API
# keep_firing_for (Prometheus semantics): a log-derived finding stays
# open this long after its evidence line rotates out of the tail — a
# failing job that spams then goes quiet is not "recovered"
KEEP_FIRING_S = int(os.getenv("WATCH_LOG_KEEP_FIRING_S", "1800"))
JOB_REPAIR_HOURS = int(os.getenv("WATCH_JOB_REPAIR_HOURS", "24"))

_STARTED = time.time()
_LAST_PASS: dict[str, Any] = {"at": None, "findings": 0, "error": None,
                              "docker_ok": None, "watched": None,
                              "log_scanned": None, "rules": None,
                              "job_feed": None}
_JOB_FEED_OK = False

# restart-count growth per poll that counts as a crash loop
RESTART_LOOP_DELTA = 2
# a container lingering in 'created' this long means start() failed
# (port bind/mount/env) — normal compose-up passes through in seconds
CREATED_WEDGE_S = int(os.getenv("WATCH_CREATED_WEDGE_S", "300"))

_MANUAL_STEPS = [
    ("watch:docker-socket",
     "The watcher cannot read /var/run/docker.sock — it is blind. "
     "Check the socket mount on the custodian-watch container and that "
     "the host allows it (some platforms strip sock mounts)."),
    ("stack:no-watched",
     "No compose-managed containers exist outside the watcher — either "
     "the app's deploy was rolled back/removed (check Coolify deploy "
     "logs) or WATCH_PROJECT is filtering them out. docker ps -a on "
     "the host shows which."),
    ("app:",
     "Config/provider failure inside a healthy container — docker sees "
     "nothing wrong, the data pipeline is dead. 1. Read the attached "
     "log lines for the provider name. 2. API-key errors → fix the key "
     "in .env and 'docker compose up -d --force-recreate' the service "
     "(env is baked at create time; restart alone won't pick it up). "
     "3. 429s → check plan tier or reduce call volume. 4. Incident "
     "auto-resolves when the lines stop appearing in the tail."),
    ("job:",
     "A scheduled job exhausted its in-worker retry budget. 1. Check "
     "job_runs for the repeated error. 2. Check custodian_actions for "
     "the attempted restarts. 3. Fix the job/provider/schema root "
     "cause, then rerun from the Job Scheduler page."),
    ("container:",
     "1. Coolify/Docker logs for the named container — the log tail is "
     "attached.  2. 'Failed to apply migration' → fix the migration SQL "
     "and redeploy.  3. OOMKilled → raise the service memory limit or "
     "reduce concurrency.  4. Port/bind errors → check compose ports vs "
     "host.  5. Persistent crash loop → redeploy previous good image "
     "from Coolify."),
]


def _steps(sig: str) -> str:
    for pre, s in _MANUAL_STEPS:
        if sig.startswith(pre):
            return s
    return "Inspect container logs; fix root cause; incident resolves when the signature clears."


# ── docker API over the unix socket (stdlib only) ─────────────────────


class _DockerConn(http.client.HTTPConnection):
    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(20)
        self.sock.connect(DOCKER_SOCK)


def _docker(path: str) -> bytes:
    if DOCKER_HOST.startswith(("tcp://", "http://")):
        host = DOCKER_HOST.split("://", 1)[1]
        c = http.client.HTTPConnection(host, timeout=20)
    else:
        c = _DockerConn("localhost")
    try:
        c.request("GET", path)
        r = c.getresponse()
        body = r.read()
        if r.status != 200:
            raise RuntimeError(f"docker GET {path} -> {r.status}")
        return body
    finally:
        c.close()


def _list_containers() -> list[dict]:
    return json.loads(_docker("/containers/json?all=1"))


def _inspect(cid: str) -> dict:
    return json.loads(_docker(f"/containers/{cid}/json"))


def _logs(cid: str, tail: int = 60) -> str:
    """Fetch container logs, stripping docker's 8-byte stream framing."""
    raw = _docker(f"/containers/{cid}/logs?stdout=1&stderr=1&tail={tail}")
    out = bytearray()
    i = 0
    while i + 8 <= len(raw):
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        out += raw[i + 8:i + 8 + size]
        i += 8 + size
    return (out.decode("utf-8", "replace") or raw.decode("utf-8", "replace"))


def _project_name() -> str:
    """This container's own compose project — watched = everything ELSE
    with a compose project label (the watcher is a separate deploy unit
    by design; it must survive the app deploys it monitors)."""
    try:
        me = _inspect(socket.gethostname())
        return (me.get("Config", {}).get("Labels", {})
                .get("com.docker.compose.project", ""))
    except Exception:
        return ""


def _watched(containers: list[dict], own_project: str) -> list[dict]:
    """Containers the watcher supervises: any compose-managed container
    not in the watcher's own project. WATCH_PROJECT narrows to one."""
    want = os.getenv("WATCH_PROJECT", "")
    out = []
    for c in containers:
        proj = (c.get("Labels") or {}).get("com.docker.compose.project", "")
        if not proj or proj == own_project:
            continue                    # helpers + self
        if want and proj != want:
            continue
        out.append(c)
    return out


# ── sqlite state ───────────────────────────────────────────────────────


def _db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # API thread reads while loop writes
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS incidents (
            signature   TEXT PRIMARY KEY,
            source      TEXT NOT NULL,
            severity    TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'open',
            detail      TEXT,
            diagnosis   TEXT,
            manual_steps TEXT,
            occurrences INTEGER NOT NULL DEFAULT 1,
            first_seen  TEXT NOT NULL,
            last_seen   TEXT NOT NULL,
            resolved_at TEXT,
            alerted_at  TEXT);
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signature TEXT NOT NULL,
            action TEXT NOT NULL,
            result TEXT,
            created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS container_state (
            name TEXT PRIMARY KEY,
            restart_count INTEGER,
            status TEXT,
            health TEXT,
            updated TEXT);
        CREATE TABLE IF NOT EXISTS runbook (
            kind        TEXT PRIMARY KEY,   -- 'log-scan:api-key', 'docker:unhealthy'
            detector    TEXT,               -- which sensor caught it
            title       TEXT,
            system_diagnosis TEXT,          -- latest auto diagnosis
            sample_log  TEXT,               -- latest log tail / error
            resolution_steps TEXT,          -- user-written, preserved
            times_seen  INTEGER NOT NULL DEFAULT 1,
            last_signature TEXT,
            last_seen   TEXT,
            created_at  TEXT);
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT);""")
    # columns added after first deploy — ALTER is idempotent-by-exception
    for ddl in ("ALTER TABLE incidents ADD COLUMN resolution_note TEXT",
                "ALTER TABLE incidents ADD COLUMN resolved_by TEXT"):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── sensors ───────────────────────────────────────────────────────────


def _classify(tail: str, ins: dict) -> tuple[str, str]:
    """Log tail + inspect → (diagnosis, severity)."""
    t = tail.lower()
    st = ins.get("State", {})
    if st.get("OOMKilled") or "out of memory" in t or "oomkilled" in t:
        return ("OOM-killed — raise the service memory limit or reduce "
                "concurrency", "high")
    if "failed to apply migration" in t or "failed to initialize database" in t:
        return ("boot fatal — a migration crashed the process "
                "(fail-fast by design); fix the named migration and "
                "redeploy", "high")
    if "address already in use" in t or "bind: " in t:
        return ("port conflict — host port already bound", "high")
    if "no space left" in t:
        return ("host disk full", "high")
    return ("container unhealthy/exited — see attached log tail", "high")


# log-scan rules for HEALTHY containers — a bad provider key or a
# rate-limited plan leaves the process alive while the data pipeline
# silently dies; docker health alone can't see it.
#
# Rules are YAML, stored in sqlite (survives rebuilds on the named
# volume) and editable at /rules on the board — add a signature without
# a code change. Schema per rule:
#   kind            label in the `app:<container>:<kind>` signature
#   pattern         python regex, matched case-insensitive per line
#   severity        high | medium | low
#   diagnosis       shown on the board; prepend provider name when found
#   needs_provider  require a provider token in the line (kills
#                   proxy/access-log 401 false positives)
#   keep_firing_s   per-rule override of KEEP_FIRING_S
_DEFAULT_RULES_YAML = """\
# custodian-watch log-scan rules — edit via GET/POST /rules
# provider_pattern gates 'needs_provider' rules (provider must be named)
provider_pattern: 'fmp|financial.?modeling|alpha.?vantage|massive|polygon|tiingo|finnhub|fred\\b|yahoo'
rules:
  # --- provider / data feed ---
  - kind: api-key
    severity: high
    needs_provider: false
    pattern: 'invalid api ?key|api ?key.*invalid|not.*valid.*api.?key'
    diagnosis: 'provider rejected its API key — fix the key in .env and recreate the service (env changes need up -d --force-recreate, not restart)'
  - kind: http-auth
    severity: high
    needs_provider: true
    pattern: 'status=(401|403)\\b|http.{0,10}(401|403)|unauthorized|forbidden|payment required'
    diagnosis: 'provider auth errors (401/403) — verify API key / entitlements in .env; some FMP endpoints are plan-gated'
  - kind: rate-limit
    severity: medium
    needs_provider: true
    keep_firing_s: 3600
    pattern: 'rate.?limit|status=429|too many requests'
    diagnosis: 'provider rate-limiting — check plan tier / call volume; persistent 429s need budget rework, not retries'
  # --- database ---
  - kind: db-conn
    severity: high
    needs_provider: false
    pattern: 'could not connect to (server|database)|connection refused.*(5432|6432)|psycopg.*operationalerror|timeout.*connecting.*(postgres|database)'
    diagnosis: 'app cannot reach postgres — check pgbouncer/postgres health and DATABASE_URL'
  - kind: db-auth
    severity: high
    needs_provider: false
    pattern: 'password authentication failed|no pg_hba.conf entry|pooler error|authentication.*failed.*(db|postgres|pgbouncer|database)'
    diagnosis: 'database auth rejected — wrong user/password in DATABASE_URL or stale pgbouncer auth_file; container stays healthy while every query fails'
  - kind: db-pool-exhausted
    severity: high
    needs_provider: false
    pattern: 'pool.*exhausted|timeout waiting for connection|too many connections for role|remaining connection slots'
    diagnosis: 'database connection pool full — reduce app concurrency or raise pgbouncer pool_size'
  - kind: db-migration-error
    severity: high
    needs_provider: false
    pattern: 'failed to apply migration|failed to run migrations|migration.*(failed|error)|dirty database|relation.*does not exist|column.*does not exist|unterminated quoted string'
    diagnosis: 'migration/schema failure — the log tail names the bad migration file; fix the SQL and redeploy'
  # --- web / proxy ---
  - kind: gateway-error
    severity: high
    needs_provider: false
    pattern: '502 bad gateway|504 gateway time-out|upstream prematurely closed connection'
    diagnosis: 'proxy cannot reach the backend — upstream container crashed, rebooting, or not listening on the routed port'
  - kind: worker-timeout
    severity: medium
    needs_provider: false
    pattern: 'worker timeout|critical worker timeout|gunicorn.*timeout|uwsgi.*harakiri'
    diagnosis: 'web worker killed mid-request — raise the worker timeout or fix the slow endpoint named in the tail'
  # --- language runtimes ---
  - kind: go-panic
    severity: high
    needs_provider: false
    pattern: 'panic:|fatal error: runtime|goroutine \\d+ \\['
    diagnosis: 'go process panicked — read the goroutine stack in the log tail; usually nil deref or config cast'
  - kind: python-runtime-crash
    severity: high
    needs_provider: false
    pattern: 'modulenotfounderror|importerror|nameerror: name|syntaxerror'
    diagnosis: 'python crash — missing dep in requirements or a code bug; the log tail has the import/stack line'
  - kind: code-bug
    severity: high
    needs_provider: false
    pattern: '(attributeerror|typeerror|keyerror|indexerror|zerodivisionerror): '
    diagnosis: 'unhandled code exception in logs — a code bug, not config; the traceback line names the file:line'
  - kind: next-ssr-error
    severity: high
    needs_provider: false
    pattern: 'unhandledrejection|digest: \d+|prerender.error|export encountered errors|⨯|error occurred prerendering|server-side exception'
    diagnosis: 'Next.js server render failure — the browser sees "Application error"; the named digest/page in the tail points at the SSR code path (common cause: calling a non-component export from a use-client module)'
  - kind: auth-token-expired
    severity: medium
    needs_provider: false
    keep_firing_s: 900
    pattern: 'auth: token expired'
    diagnosis: 'JWT expiry rejections — client session rot: the frontend should re-login on exp; a sustained burst means every authed write (portfolio CRUD) is 401ing'
  - kind: api-5xx
    severity: medium
    needs_provider: false
    keep_firing_s: 900
    pattern: '" (500|502|503)( |$)|] (500|502|503)( |$)|status=5\\d\\d|internal server error'
    diagnosis: 'HTTP 5xx in app logs — requests failing server-side; check which endpoint and its traceback'
  # --- jobs / broker ---
  - kind: broker-conn
    severity: high
    needs_provider: false
    pattern: 'redis.*connectionerror|connection refused.*(6379|amqp)|kombu\\.exceptions'
    diagnosis: 'worker cannot reach the broker (redis) — check redis container health and REDIS_URL'
  - kind: job-failed
    severity: medium
    needs_provider: false
    keep_firing_s: 7200
    pattern: 'job .{0,40}failed|failed.{0,20}job|task .{0,40}failed'
    diagnosis: 'a scheduled job failed — the job stays registered but its output goes stale; the log tail names it'
  # --- infra ---
  - kind: dns-resolution-error
    severity: high
    needs_provider: false
    pattern: 'name or service not known|temporary failure in name resolution|eai_again'
    diagnosis: 'container DNS failure — docker bridge or host resolv.conf misconfigured'
  - kind: disk-full
    severity: high
    needs_provider: false
    pattern: 'no space left on device|disk quota exceeded'
    diagnosis: 'host disk full — docker system df; prune images/logs or expand volume'
  - kind: fs-degraded
    severity: high
    needs_provider: false
    pattern: 'read-only file system|input/output error'
    diagnosis: 'filesystem degraded — disk remounted read-only on error; check host dmesg / SMART'
  - kind: tls-cert
    severity: medium
    needs_provider: false
    pattern: 'certificate.*(expired|verify failed)|x509|ssl.*handshake.*fail|tls.*handshake.*fail'
    diagnosis: 'TLS failure — expired cert or host clock skew; check cert validity and host time'
  - kind: oom-logs
    severity: high
    needs_provider: false
    pattern: 'killed process.*out of memory|memoryerror'
    diagnosis: 'memory exhaustion visible in app logs — raise the service limit or reduce concurrency'
"""

_FALLBACK_PROVIDER_RE = re.compile(
    r"fmp|financial.?modeling|alpha.?vantage|massive|polygon|tiingo|"
    r"finnhub|fred\b|yahoo", re.I)

_rules_cache: dict = {"text": None, "rules": [], "provider": None}


def _rules_yaml(conn) -> str:
    row = conn.execute(
        "SELECT value FROM config WHERE key='log_rules'").fetchone()
    if row:
        return row["value"]
    conn.execute("INSERT INTO config VALUES ('log_rules', ?)",
                 (_DEFAULT_RULES_YAML,))
    conn.commit()
    return _DEFAULT_RULES_YAML


def _compile_rules(txt: str) -> tuple[list[dict], Any]:
    """YAML → compiled rules. Raises on any invalid rule — callers
    decide whether to keep last-good (scan) or reject the save (UI)."""
    import yaml
    doc = yaml.safe_load(txt) or {}
    prov = _FALLBACK_PROVIDER_RE
    if doc.get("provider_pattern"):
        prov = re.compile(str(doc["provider_pattern"]), re.I)
    rules = []
    for i, r in enumerate(doc.get("rules") or []):
        if not r.get("kind") or not r.get("pattern"):
            raise ValueError(f"rule {i}: needs kind + pattern")
        rules.append({
            "kind": str(r["kind"]),
            "pattern": re.compile(str(r["pattern"]), re.I),
            "severity": str(r.get("severity") or "medium"),
            "diagnosis": str(r.get("diagnosis") or "log error"),
            "needs_provider": bool(r.get("needs_provider", True)),
            "keep_firing_s": int(r.get("keep_firing_s") or 0),
        })
    return rules, prov


def _log_rules(conn) -> tuple[list[dict], Any]:
    """Compiled rules, re-parsed only when the stored YAML changes."""
    txt = _rules_yaml(conn)
    if txt == _rules_cache["text"]:
        return _rules_cache["rules"], _rules_cache["provider"]
    try:
        rules, prov = _compile_rules(txt)
    except Exception as exc:
        logger.warning("log_rules yaml invalid — keeping last-good: %s",
                       exc)
        if _rules_cache["rules"]:
            return _rules_cache["rules"], _rules_cache["provider"]
        rules, prov = _compile_rules(_DEFAULT_RULES_YAML)
    _rules_cache.update(text=txt, rules=rules, provider=prov)
    return rules, prov


def _scan_app_logs(conn, cid: str, name: str) -> list[dict]:
    """Scan a running container's log tail for rule-matched error
    signatures — the failures that leave docker 'healthy'."""
    try:
        tail = _logs(cid, tail=200)
    except Exception:
        return []
    rules, prov_re = _log_rules(conn)
    _LAST_PASS["rules"] = len(rules)   # expose the active rule count —
    # verifies stored sqlite rules actually refreshed after edits/reset
    hits: dict[str, list[str]] = {}
    for line in tail.splitlines():
        for r in rules:
            if not r["pattern"].search(line):
                continue
            if r["needs_provider"] and not prov_re.search(line):
                continue
            hits.setdefault(r["kind"], []).append(line.strip()[:160])
            break  # one signature per line is enough
    findings = []
    for kind, lines in hits.items():
        r = next(x for x in rules if x["kind"] == kind)
        prov = ""
        for line in lines:
            m = prov_re.search(line)
            if m:
                prov = m.group(0).lower().replace(" ", "")
                break
        det = {"diagnosis": (f"{prov}: " if prov else "")
               + r["diagnosis"],
               "log_tail": "\n".join(lines[-3:])}
        if r["keep_firing_s"]:
            det["keep_firing_s"] = r["keep_firing_s"]
        findings.append({
            "signature": f"app:{name}:{kind}",
            "source": "watch", "severity": r["severity"],
            "detail": det})
    return findings


def _sense(own_project: str) -> list[dict[str, Any]]:
    findings = []
    try:
        containers = _list_containers()
        _LAST_PASS["docker_ok"] = True
    except Exception as exc:
        # a blind watcher reporting 'all clear' is worse than no watcher
        _LAST_PASS["docker_ok"] = False
        logger.warning("docker socket unreachable: %s", exc)
        return [{
            "signature": "watch:docker-socket-unreachable",
            "source": "watch", "severity": "high",
            "detail": {"error": str(exc)[:300],
                       "diagnosis": "watcher cannot read the docker "
                       "socket — it sees nothing"},
        }] + _job_escalations()

    watched = _watched(containers, own_project)
    _LAST_PASS["watched"] = len(watched)
    _LAST_PASS["log_scanned"] = 0
    if not watched:
        findings.append({
            "signature": "stack:no-watched-containers",
            "source": "watch", "severity": "medium",
            "detail": {"diagnosis": "no compose-managed containers "
                       "outside the watcher — the app is absent "
                       "(deploy rolled back/removed) or filtered out"}})

    conn = _db()
    for c in watched:
        name = (c.get("Names") or ["?"])[0].lstrip("/")
        try:
            ins = _inspect(c["Id"])
        except Exception:
            continue
        st = ins.get("State", {})
        health = (st.get("Health") or {}).get("Status") or "none"
        status = st.get("Status", "")
        rc = st.get("RestartCount", 0)
        policy = (ins.get("HostConfig", {})
                  .get("RestartPolicy", {}).get("Name", ""))
        restarts_forever = policy in ("always", "unless-stopped")

        # restart-loop: restart count climbing while not healthy
        prev = conn.execute(
            "SELECT restart_count FROM container_state WHERE name=?",
            (name,)).fetchone()
        conn.execute(
            "INSERT INTO container_state (name,restart_count,status,"
            "health,updated) VALUES (?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET restart_count=?, "
            "status=?, health=?, updated=?",
            (name, rc, status, health, _now(),
             rc, status, health, _now()))
        grew = rc - (prev["restart_count"] if prev else rc)
        if grew >= RESTART_LOOP_DELTA and health != "healthy":
            findings.append({
                "signature": f"container:{name}:restart-loop",
                "source": "watch", "severity": "high",
                "detail": {"restarts": rc, "delta": grew,
                           "status": status, "health": health}})

        if health == "unhealthy":
            try:
                tail = _logs(c["Id"])[-3000:]
            except Exception:
                tail = ""
            diag, sev = _classify(tail, ins)
            findings.append({
                "signature": f"container:{name}:unhealthy",
                "source": "watch", "severity": sev,
                "detail": {"status": status, "restart_count": rc,
                           "log_tail": tail[-1500:], "diagnosis": diag}})

        elif (status in ("exited", "dead") and restarts_forever
              and st.get("ExitCode", 0) != 0):
            try:
                tail = _logs(c["Id"])[-3000:]
            except Exception:
                tail = ""
            diag, sev = _classify(tail, ins)
            findings.append({
                "signature": f"container:{name}:exited",
                "source": "watch", "severity": sev,
                "detail": {"exit_code": st.get("ExitCode"),
                           "oom": st.get("OOMKilled"),
                           "log_tail": tail[-1500:], "diagnosis": diag}})

        # created-wedge: compose/Coolify created the container but the
        # start failed — port bind conflict, missing mount, bad env.
        # No logs, no exit event, no healthcheck: invisible to every
        # sensor above. Docker leaves it in 'created' indefinitely.
        elif status == "created":
            try:
                # docker Created is RFC3339-nanos UTC — 19 chars gives
                # "YYYY-MM-DDTHH:MM:SS", tz attached explicitly
                created = datetime.fromisoformat(
                    (ins.get("Created") or "")[:19]
                ).replace(tzinfo=timezone.utc)
                age_s = (datetime.now(timezone.utc)
                         - created).total_seconds()
            except Exception:
                age_s = None
            if age_s is not None and age_s > CREATED_WEDGE_S:
                findings.append({
                    "signature": f"container:{name}:created-wedge",
                    "source": "watch", "severity": "high",
                    "detail": {
                        "status": "created",
                        "age_s": round(age_s),
                        "diagnosis": ("container created but never "
                                      "started — 'docker start' failed "
                                      "(port bind conflict, missing "
                                      "mount, or bad env). The error is "
                                      "in the deploy/Coolify log, not "
                                      "container logs: 'docker inspect "
                                      f"{name}' + 'docker ps --filter "
                                      "publish' to find the collision")}})

        # healthy-by-docker but config-dead — bad provider keys, plan
        # 401/403s, persistent 429s all leave the process running
        elif status == "running":
            _LAST_PASS["log_scanned"] += 1
            findings.extend(_scan_app_logs(conn, c["Id"], name))
    conn.commit()
    conn.close()
    findings.extend(_job_escalations())
    return findings


# ── notify ─────────────────────────────────────────────────────────────


def _email(subject: str, body: str) -> bool:
    user, pw = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    to = os.getenv("ALERT_EMAIL") or user
    if not (user and pw and to):
        logger.info("SMTP not configured — alert: %s", subject)
        return False
    try:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = user, to, subject
        msg.set_content(body)
        with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"),
                          int(os.getenv("SMTP_PORT", "587")),
                          timeout=20) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        return True
    except Exception as exc:
        logger.warning("email send failed: %s", exc)
        return False


def _pg_connect():
    if not DATABASE_URL:
        return None
    import psycopg2
    return psycopg2.connect(DATABASE_URL, connect_timeout=5)


def _job_escalations() -> list[dict]:
    """Worker-owned retry exhaustion → watch findings.

    The worker custodian writes `job:<name>:error` incidents after its
    bounded retries. The watcher surfaces only the terminal escalations;
    transient retry-in-progress rows stay in the job-repair table."""
    global _JOB_FEED_OK
    _JOB_FEED_OK = False
    _LAST_PASS["job_feed"] = "unavailable"
    conn = None
    try:
        conn = _pg_connect()
        if conn is None:
            return []
        cur = conn.cursor()
        cur.execute(
            """SELECT signature, severity, detail, attempts, last_seen
               FROM custodian_incidents
               WHERE signature LIKE 'job:%' AND status='escalated'
               ORDER BY last_seen DESC LIMIT 50""")
        findings = []
        for sig, sev, detail, attempts, last_seen in cur.fetchall():
            if isinstance(detail, str):
                try:
                    detail = json.loads(detail)
                except Exception:
                    detail = {"error": detail}
            det = dict(detail or {})
            det.setdefault(
                "diagnosis",
                "scheduled job exhausted auto-repair attempts — "
                "manual intervention required")
            det["attempts"] = attempts
            det["last_seen"] = str(last_seen)
            findings.append({
                "signature": sig, "source": "worker",
                "severity": "high" if sev != "high" else sev,
                "detail": det})
        _JOB_FEED_OK = True
        _LAST_PASS["job_feed"] = "ok"
        return findings
    except Exception as exc:
        logger.debug("job escalation read skipped: %s", exc)
        return []
    finally:
        if conn is not None:
            conn.close()


def _mirror_pg(sig: str, sev: str, detail: dict, status: str,
               diagnosis: str, steps: str) -> None:
    """Best-effort copy into postgres custodian_incidents so the board's
    Custodian view sees watch findings. Skipped silently when DB is down
    — sqlite is the record of truth."""
    conn = None
    try:
        from psycopg2.extras import Json
        conn = _pg_connect()
        if conn is None:
            return
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO custodian_incidents
                 (signature, source, severity, status, detail,
                  diagnosis, remediation, manual_steps)
               VALUES (%s,'watch',%s,%s,%s,%s,'escalate',%s)
               ON CONFLICT (signature) DO UPDATE SET
                 status=EXCLUDED.status, severity=EXCLUDED.severity,
                 detail=EXCLUDED.detail, last_seen=now(),
                 resolved_at=NULL""",
            (sig, sev, status, Json(detail), diagnosis, steps))
        conn.commit()
    except Exception as exc:
        logger.debug("pg mirror skipped (%s): %s", sig, exc)
    finally:
        if conn is not None:
            conn.close()


def _jsonable(v):
    """Postgres rows → JSON-safe values without changing timestamps."""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


def _job_repair_json(hours: int = JOB_REPAIR_HOURS) -> dict:
    """Read-only job health — durable job_runs + the in-worker
    custodian's remediation ledger. The watcher deliberately does not
    restart jobs itself: the worker owns _run_job and retry policy."""
    out = {"available": False, "hours": hours, "rows": []}
    conn = None
    try:
        from psycopg2.extras import RealDictCursor
        conn = _pg_connect()
        if conn is None:
            out["error"] = "DATABASE_URL not configured"
            return out
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """WITH latest AS (
                 SELECT DISTINCT ON (name) name, ran_at, duration_s,
                        error
                 FROM job_runs ORDER BY name, ran_at DESC
               ), latest_action AS (
                 SELECT DISTINCT ON (signature) signature, action,
                        result, created_at
                 FROM custodian_actions
                 WHERE signature LIKE 'job:%'
                 ORDER BY signature, id DESC
               )
               SELECT d.name, d.label, d.cron, d.enabled,
                      l.ran_at, l.duration_s, l.error,
                      i.status AS incident_status,
                      i.severity AS incident_severity,
                      i.attempts, i.last_seen AS incident_seen,
                      a.action AS repair_action,
                      a.result AS repair_result,
                      a.created_at AS repair_at
               FROM job_definitions d
               JOIN latest l ON l.name = d.name
               LEFT JOIN custodian_incidents i
                 ON i.signature = 'job:' || d.name || ':error'
               LEFT JOIN latest_action a
                 ON a.signature = 'job:' || d.name || ':error'
               WHERE l.error IS NOT NULL
                  OR (i.status IS NOT NULL AND i.status <> 'resolved')
                  OR a.created_at > now() - interval '1 hour' * %s
               ORDER BY (l.error IS NULL), COALESCE(a.created_at,
                         l.ran_at) DESC
               LIMIT 60""",
            (hours,))
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            if r.get("incident_status") == "escalated":
                r["state"] = "escalated"
            elif r.get("error"):
                if r.get("incident_status") == "mitigated":
                    r["state"] = "repairing"
                else:
                    r["state"] = "queued for retry"
            elif r.get("repair_at") or r.get("incident_status"):
                r["state"] = "repaired"
            else:
                r["state"] = "healthy"
            for k, v in list(r.items()):
                r[k] = _jsonable(v)
        out.update(available=True, rows=rows)
        return out
    except Exception as exc:
        out["error"] = str(exc)[:300]
        return out
    finally:
        if conn is not None:
            conn.close()


def _runbook_key(sig: str) -> tuple[str, str]:
    """Signature → (detector, kind). The runbook aggregates by the
    sensor+kind that caught it — a next-ssr-error on any frontend
    shares one entry, so a fix recorded once applies everywhere."""
    if sig.startswith("app:"):
        return ("log-scan", sig.rsplit(":", 1)[-1])
    if sig.startswith("container:"):
        return ("docker", sig.rsplit(":", 1)[-1])
    return (sig.split(":", 1)[0] or "watch", sig.rsplit(":", 1)[-1])


def _runbook_bump(conn, sig: str, severity: str, detail: dict) -> None:
    """Auto-fill the runbook entry for this finding kind — diagnosis
    and evidence land automatically; user-written steps are preserved."""
    detector, kind = _runbook_key(sig)
    rb_key = f"{detector}:{kind}"
    diag = (detail.get("diagnosis") or "watch finding")[:500]
    sample = (detail.get("log_tail") or detail.get("error")
              or "")[:1200]
    conn.execute(
        "INSERT INTO runbook (kind,detector,title,system_diagnosis,"
        "sample_log,times_seen,last_signature,last_seen,created_at) "
        "VALUES (?,?,?,?,?,1,?,?,?) "
        "ON CONFLICT(kind) DO UPDATE SET "
        "system_diagnosis=excluded.system_diagnosis, "
        "sample_log=excluded.sample_log, "
        "times_seen=times_seen+1, "
        "last_signature=excluded.last_signature, "
        "last_seen=excluded.last_seen",
        (rb_key, detector, f"{detector} — {kind}", diag, sample,
         sig, _now(), _now()))


def _record(conn, f: dict) -> tuple[bool, str]:
    """Upsert incident; returns (should_alert, status)."""
    sig, now = f["signature"], _now()
    steps = _steps(sig)
    diag = f["detail"].get("diagnosis") or "watch finding"
    row = conn.execute(
        "SELECT status, alerted_at FROM incidents WHERE signature=?",
        (sig,)).fetchone()
    if row:
        reopened = row["status"] == "resolved"
        conn.execute(
            "UPDATE incidents SET status='open', last_seen=?, detail=?, "
            "severity=?, occurrences=occurrences+?, resolved_at=NULL, "
            "alerted_at=CASE WHEN ? THEN NULL ELSE alerted_at END "
            "WHERE signature=?",
            (now, json.dumps(f["detail"]), f["severity"],
             1 if reopened else 0, reopened, sig))
        _runbook_bump(conn, sig, f["severity"], f["detail"])
        return row["alerted_at"] is None or reopened, "open"
    conn.execute(
        "INSERT INTO incidents (signature,source,severity,detail,"
        "diagnosis,manual_steps,first_seen,last_seen) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (sig, f["source"], f["severity"], json.dumps(f["detail"]),
         diag, steps, now, now))
    _runbook_bump(conn, sig, f["severity"], f["detail"])
    return True, "open"


def _resolve_absent(conn, seen: set[str]) -> None:
    """Resolve signatures absent this pass — except log-derived `app:`
    findings get keep_firing_for semantics (Prometheus): the evidence
    line can rotate out of the 80-line tail while the config fault
    persists, so they stay open until absent for keep_firing_s (rule
    override else KEEP_FIRING_S), clocked off last_seen."""
    now = _now()
    for r in conn.execute(
            "SELECT signature, source, detail, last_seen FROM incidents "
            "WHERE status != 'resolved'").fetchall():
        sig = r["signature"]
        if sig in seen:
            continue
        if r["source"] == "worker" and not _JOB_FEED_OK:
            continue                    # blind feed ≠ resolved failure
        if sig.startswith("app:"):
            try:
                grace = int(json.loads(r["detail"] or "{}")
                            .get("keep_firing_s") or KEEP_FIRING_S)
            except Exception:
                grace = KEEP_FIRING_S
            cutoff = (datetime.now(timezone.utc)
                      - timedelta(seconds=grace)).isoformat(
                          timespec="seconds")
            if (r["last_seen"] or "") > cutoff:
                continue                    # still inside keep-firing
        conn.execute(
            "UPDATE incidents SET status='resolved', resolved_at=?, "
            "resolved_by='auto' WHERE signature=?", (now, sig))


# ── status API ─────────────────────────────────────────────────────────
# Exporter-pattern read surface: /health is public (uptime checks),
# everything else needs Authorization: Bearer $WATCH_TOKEN. Stdlib
# http.server in a daemon thread — no framework, no deps.


def _incidents_json() -> dict:
    conn = _db()
    try:
        op = [dict(r) for r in conn.execute(
            "SELECT * FROM incidents WHERE status != 'resolved' "
            "ORDER BY last_seen DESC")]
        for r in op:
            try:
                r["detail"] = json.loads(r.get("detail") or "{}")
            except Exception:
                pass
            rb = conn.execute(
                "SELECT kind, resolution_steps, times_seen "
                "FROM runbook WHERE kind=?",
                (f"{_runbook_key(r['signature'])[0]}:"
                 f"{_runbook_key(r['signature'])[1]}",)).fetchone()
            if rb:
                r["runbook"] = dict(rb)
        res = [dict(r) for r in conn.execute(
            "SELECT signature,severity,status,occurrences,resolved_at,"
            "resolved_by,resolution_note,last_seen FROM incidents "
            "WHERE status='resolved' ORDER BY resolved_at DESC "
            "LIMIT 10")]
        acts = [dict(r) for r in conn.execute(
            "SELECT * FROM actions ORDER BY id DESC LIMIT 30")]
        return {"generated_at": _now(), "uptime_s": int(time.time() - _STARTED),
                "last_pass": _LAST_PASS, "open": op,
                "job_repair": _job_repair_json(),
                "resolved": res, "actions": acts}
    finally:
        conn.close()


_PAGE = """<!doctype html><meta charset=utf-8><title>custodian-watch</title>
<style>body{{font:13px/1.4 ui-monospace,monospace;max-width:1100px;margin:24px auto;padding:0 12px}}
table{{border-collapse:collapse;width:100%;margin:8px 0 24px}}td,th{{border:1px solid #444;padding:4px 8px;text-align:left;vertical-align:top}}
th{{background:#222;color:#eee}}.hi{{color:#c0392b;font-weight:700}}.med{{color:#e67e22}}.ok{{color:#27ae60}}
pre{{white-space:pre-wrap;font-size:11px;color:#888;max-height:120px;overflow:auto}}</style>
<h2>custodian-watch <span class=ok>&#9679;</span></h2>
<p>up {uptime}s &middot; last pass {last} &middot; {nfind} finding(s) &middot; {proj}</p>
<h3>scheduled jobs — failures & auto-repair</h3>{jobs_t}
<h3>open incidents</h3>{open_t}<h3>recently resolved</h3>{res_t}
<h3>actions</h3>{act_t}<p style=color:#888>JSON: /incidents &middot; /job-failures &middot; liveness: /health &middot; <a href="/rules{tok}">edit log rules</a> &middot; <a href="/runbook{tok}">runbook</a></p>"""


def _row_html(r, cols):
    sev = r.get("severity", "")
    cls = ' class="hi"' if sev == "high" else ' class="med"' if sev in ("medium",) else ""
    cells = "".join(
        f"<td{cls if c == 'severity' else ''}>"
        + (f"<pre>{r[c]}</pre>" if c == "log" else str(r.get(c, "") or ""))
        + "</td>" for c in cols)
    return f"<tr>{cells}</tr>"


def _incidents_html(token: str = "") -> str:
    d = _incidents_json()
    def tbl(rows, cols):
        head = "".join(f"<th>{c}" for c in cols)
        body = "".join(_row_html(r, cols) for r in rows) or \
            f"<tr><td colspan={len(cols)} class=ok>none</td></tr>"
        return f"<table><tr>{head}</tr>{body}</table>"
    import html as _h
    tok_q = (f"?token={token}" if token else "")
    for r in d["open"]:
        det = r.get("detail") or {}
        r["log"] = (det.get("log_tail") or det.get("error")
                    or json.dumps(det)[:400]) if isinstance(det, dict) \
            else str(det)[:400]
        m = re.match(r"^(?:container|app):([^:]+):",
                     r.get("signature") or "")
        r["live"] = (f'<a href="/logs/{m.group(1)}?tail=200'
                     + (f"&token={token}" if token else "")
                     + '">live&nbsp;tail</a>') if m else ""
        # recorded fix from the runbook — the detector+kind learning
        rb = r.get("runbook") or {}
        if rb.get("resolution_steps"):
            r["fix"] = (f'<pre>{_h.escape(str(rb["resolution_steps"]))}'
                        f'</pre><div style="color:#27ae60">recorded fix'
                        f' — seen {rb.get("times_seen", 1)}&times;</div>')
        else:
            rbk = str(rb.get("kind") or f"{_runbook_key(r.get('signature') or '')[0]}:{_runbook_key(r.get('signature') or '')[1]}")
            r["fix"] = (f'<a href="/runbook{tok_q}'
                        f'#{_h.escape(rbk)}">'
                        f'write fix &rarr;</a>')
        sig_esc = _h.escape(str(r.get("signature") or ""), quote=True)
        r["manage"] = (
            f'<form method=post action="/incidents/close{tok_q}" '
            f'style="margin:0">'
            f'<input type=hidden name=sig value="{sig_esc}">'
            f'<input name=note size=14 placeholder="note (optional)">'
            f'<button type=submit>close</button></form>')
    jobs = d.get("job_repair") or {}
    job_rows = []
    for r in jobs.get("rows") or []:
        r = dict(r)
        r["log"] = r.get("error") or r.get("repair_result") or ""
        r["repair"] = " ".join(x for x in
                               (r.get("repair_action"),
                                r.get("repair_result")) if x)
        job_rows.append(r)
    if not jobs.get("available"):
        job_rows = [{"name": "job repair feed", "state": "unavailable",
                     "log": jobs.get("error") or "DATABASE_URL not configured"}]
    return _PAGE.format(
        uptime=d["uptime_s"], last=d["last_pass"]["at"],
        nfind=d["last_pass"]["findings"], proj=os.uname().nodename,
        tok=(f"?token={token}" if token else ""),
        jobs_t=tbl(job_rows, ["name", "state", "incident_status",
                              "attempts", "log", "repair", "ran_at",
                              "repair_at"]),
        open_t=tbl(d["open"], ["signature", "severity", "diagnosis",
                              "log", "live", "fix", "manual_steps",
                              "last_seen", "manage"]),
        res_t=tbl(d["resolved"], ["signature", "severity", "occurrences",
                                  "resolved_at", "resolved_by",
                                  "resolution_note"]),
        act_t=tbl(d["actions"], ["created_at", "signature", "action",
                                 "result"]))


_RULES_PAGE = """<!doctype html><meta charset=utf-8><title>watch rules</title>
<style>body{{font:13px/1.4 ui-monospace,monospace;max-width:900px;margin:24px auto;padding:0 12px}}
textarea{{width:100%;height:60vh;font:12px ui-monospace,monospace;background:#111;color:#ddd;border:1px solid #444}}
button{{padding:6px 18px;margin:8px 0}}.err{{color:#c0392b}}.ok{{color:#27ae60}}</style>
<h2>log-scan rules</h2>
<p>YAML matched per-line against every running container's log tail.
Fields: <b>kind</b> (signature suffix) &middot; <b>pattern</b> (regex)
&middot; <b>severity</b> &middot; <b>diagnosis</b> &middot;
<b>needs_provider</b> (require provider name in the line)
&middot; <b>keep_firing_s</b>. Saved rules apply on the next pass.</p>
{msg}
<form method=post action="/rules{tok}">
<textarea name=rules>{rules}</textarea><br>
<button type=submit>save</button>
<button type=submit name=reset value=1
  formnovalidate
  onclick="return confirm('reset rules to built-in defaults?')">
  reset to defaults</button></form>
<p><a href="/{tok}">&larr; board</a></p>"""


def _rules_html(token: str, msg: str = "") -> str:
    import html as _h
    conn = _db()
    try:
        txt = _rules_yaml(conn)
    finally:
        conn.close()
    tok = f"?token={token}" if token else ""
    return _RULES_PAGE.format(rules=_h.escape(txt), tok=tok, msg=msg)


_RUNBOOK_PAGE = """<!doctype html><meta charset=utf-8><title>watch runbook</title>
<style>body{{font:13px/1.4 ui-monospace,monospace;max-width:1000px;margin:24px auto;padding:0 12px}}
.entry{{border:1px solid #444;margin:14px 0;padding:10px 14px}}
textarea{{width:100%;height:90px;font:12px ui-monospace,monospace;background:#111;color:#ddd;border:1px solid #444}}
pre{{white-space:pre-wrap;font-size:11px;color:#888;max-height:100px;overflow:auto;background:#161616;padding:6px}}
button{{padding:4px 14px}}.ok{{color:#27ae60}}.hi{{color:#c0392b}}
.k{{color:#e67e22}}</style>
<h2>runbook — what we learned</h2>
<p>Entries auto-fill when an incident fires (detector, diagnosis,
evidence). Add your fix steps once — they surface on every future
incident of the same kind, whichever container hit it.{msg}</p>
{entries}
<p><a href="/{tok}">&larr; board</a></p>"""


def _runbook_html(token: str, msg: str = "") -> str:
    import html as _h
    conn = _db()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM runbook ORDER BY times_seen DESC")]
    finally:
        conn.close()
    tok = f"?token={token}" if token else ""
    if not rows:
        entries = ('<p style="color:#888">empty — entries appear the '
                   'first time each finding kind fires.</p>')
    else:
        parts = []
        for r in rows:
            parts.append(
                f'<div class=entry id="{_h.escape(str(r["kind"]))}">'
                f'<b class=k>{_h.escape(str(r["kind"]))}</b>'
                f' &middot; seen {r["times_seen"]}&times;'
                f' &middot; last <code>{_h.escape(str(r["last_signature"] or ""))}</code>'
                f' &middot; {_h.escape(str(r["last_seen"] or ""))}'
                f'<div style="padding:6px 0;color:#bbb">'
                f'{_h.escape(str(r["system_diagnosis"] or ""))}</div>'
                + (f'<pre>{_h.escape(str(r["sample_log"]))}</pre>'
                   if r.get("sample_log") else "")
                + f'<form method=post action="/runbook{tok}">'
                f'<input type=hidden name=kind '
                f'value="{_h.escape(str(r["kind"]), quote=True)}">'
                f'<textarea name=steps placeholder="fix steps — what '
                f'worked, in order">'
                f'{_h.escape(str(r["resolution_steps"] or ""))}</textarea>'
                f'<button type=submit>save steps</button></form></div>')
        entries = "".join(parts)
    return _RUNBOOK_PAGE.format(entries=entries, tok=tok, msg=msg)


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str, ctype: str = "application/json") -> None:
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _auth(self) -> bool:
        if not WATCH_TOKEN:
            return True   # no token configured → open (dev), logged at boot
        if self.headers.get("Authorization") == f"Bearer {WATCH_TOKEN}":
            return True
        # browsers can't send Bearer headers — ?token= lets the HTML
        # board be bookmarked (trade-off: token lands in proxy logs)
        from urllib.parse import parse_qs, urlparse
        return (parse_qs(urlparse(self.path).query)
                .get("token", [""])[0] == WATCH_TOKEN)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/health":
            self._send(200, json.dumps({"ok": True,
                                        "uptime_s": int(time.time() - _STARTED),
                                        "last_pass": _LAST_PASS}))
            return
        if not self._auth():
            self._send(401, json.dumps({"error": "unauthorized"}))
            return
        try:
            if path == "/incidents":
                self._send(200, json.dumps(_incidents_json()))
            elif path == "/job-failures":
                self._send(200, json.dumps(_job_repair_json()))
            elif path == "/containers":
                out = []
                for c in _watched(_list_containers(), _project_name()):
                    try:
                        ins = _inspect(c["Id"])
                        st = ins.get("State", {})
                        out.append({
                            "name": (c.get("Names") or ["?"])[0].lstrip("/"),
                            "status": st.get("Status"),
                            "health": (st.get("Health") or {}).get(
                                "Status") or "none",
                            "restarts": st.get("RestartCount", 0),
                            "exit_code": st.get("ExitCode")})
                    except Exception:
                        pass
                self._send(200, json.dumps({"containers": out}))
            elif path.startswith("/logs/"):
                # /logs/<name-substring>?tail=N — live log pull for any
                # watched container; substring match since names carry
                # deploy timestamps (go-api-<project>-<ts>)
                m = re.match(r"^/logs/([a-zA-Z0-9_.-]+)$", path)
                frag = m.group(1) if m else ""
                tail = 200
                qs = self.path.split("?", 1)
                if len(qs) == 2:
                    try:
                        tail = min(500, int(qs[1].split("tail=")[-1]
                                            .split("&")[0]))
                    except ValueError:
                        pass
                hit = next(
                    (c for c in _watched(_list_containers(),
                                         _project_name())
                     if frag and frag in
                     (c.get("Names") or [""])[0].lstrip("/")), None)
                if not hit:
                    self._send(404, json.dumps(
                        {"error": f"no watched container matching "
                                  f"'{frag}'"}))
                else:
                    body = _logs(hit["Id"], tail=tail)
                    self._send(200, body, "text/plain; charset=utf-8")
            elif path == "/rules":
                from urllib.parse import parse_qs, urlparse
                tok = parse_qs(urlparse(self.path).query).get(
                    "token", [""])[0]
                self._send(200, _rules_html(tok), "text/html")
            elif path == "/runbook":
                from urllib.parse import parse_qs, urlparse
                tok = parse_qs(urlparse(self.path).query).get(
                    "token", [""])[0]
                self._send(200, _runbook_html(tok), "text/html")
            elif path == "/":
                from urllib.parse import parse_qs, urlparse
                tok = parse_qs(urlparse(self.path).query).get(
                    "token", [""])[0]
                self._send(200, _incidents_html(tok), "text/html")
            else:
                self._send(404, json.dumps({"error": "not found"}))
        except Exception as exc:
            self._send(500, json.dumps({"error": str(exc)[:300]}))

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if not self._auth():
            self._send(401, json.dumps({"error": "unauthorized"}))
            return
        from urllib.parse import parse_qs, urlparse
        tok = parse_qs(urlparse(self.path).query).get("token", [""])[0]

        if path == "/incidents/close":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(min(length, 1 << 16)).decode()
            form = parse_qs(body)
            sig = (form.get("sig") or [""])[0]
            note = (form.get("note") or [""])[0].strip()
            if sig:
                conn = _db()
                try:
                    conn.execute(
                        "UPDATE incidents SET status='resolved', "
                        "resolved_at=?, resolution_note=?, "
                        "resolved_by='manual' WHERE signature=?",
                        (_now(), note or None, sig))
                    conn.execute(
                        "INSERT INTO actions (signature,action,result,"
                        "created_at) VALUES (?,?,?,?)",
                        (sig, "close:manual", note or "closed", _now()))
                    conn.commit()
                finally:
                    conn.close()
            self.send_response(303)
            self.send_header("Location", f"/{tok}")
            self.end_headers()
            return

        if path == "/runbook":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(min(length, 1 << 16)).decode()
            form = parse_qs(body)
            kind = (form.get("kind") or [""])[0]
            steps = (form.get("steps") or [""])[0]
            if kind:
                conn = _db()
                try:
                    conn.execute(
                        "UPDATE runbook SET resolution_steps=?, "
                        "last_seen=? WHERE kind=?",
                        (steps.strip() or None, _now(), kind))
                    conn.commit()
                finally:
                    conn.close()
            self.send_response(303)
            self.send_header("Location",
                             f"/runbook{tok}#{kind}")
            self.end_headers()
            return

        if path != "/rules":
            self._send(404, json.dumps({"error": "not found"}))
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(min(length, 1 << 16)).decode()
            form = parse_qs(body)
            if form.get("reset"):
                txt, rules = _DEFAULT_RULES_YAML, None
            else:
                txt = form.get("rules", [""])[0]
                rules, _ = _compile_rules(txt)  # raises → not saved
                if not rules:
                    raise ValueError("no valid rules — refusing to save")
        except Exception as exc:
            self._send(200, _rules_html(
                tok, f'<p class=err>invalid: {exc} — not saved</p>'),
                "text/html")
            return
        conn = _db()
        try:
            conn.execute(
                "INSERT INTO config VALUES ('log_rules', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=?", (txt, txt))
            conn.commit()
        finally:
            conn.close()
        _rules_cache["text"] = None            # recompile on next pass
        n = len(rules) if rules is not None \
            else len(_compile_rules(_DEFAULT_RULES_YAML)[0])
        logger.info("log_rules updated via web (%d rules)", n)
        self._send(200, _rules_html(
            tok, f'<p class=ok>saved — {n} rules active on '
                 f'next pass</p>'), "text/html")

    def log_message(self, *a) -> None:   # quiet — access logs add noise
        pass


def _serve() -> None:
    srv = ThreadingHTTPServer(("0.0.0.0", WATCH_PORT), _Handler)
    logger.info("status API on :%d%s", WATCH_PORT,
                "" if WATCH_TOKEN else " (NO WATCH_TOKEN — open)")
    srv.serve_forever()


# ── supervisor loop ────────────────────────────────────────────────────


def main() -> None:
    logger.info("custodian-watch up — poll %ss, db %s", POLL_SECONDS, DB_PATH)
    project = _project_name()
    logger.info("compose project: %s", project or "(unfiltered)")
    threading.Thread(target=_serve, daemon=True).start()
    while True:
        try:
            open(HEARTBEAT, "w").write(_now())
            findings = _sense(project)
            _LAST_PASS.update({"at": _now(), "findings": len(findings),
                               "error": None})
            conn = _db()
            seen = set()
            for f in findings:
                seen.add(f["signature"])
                alert, status = _record(conn, f)
                if f.get("source") != "worker":
                    _mirror_pg(f["signature"], f["severity"],
                               f["detail"], status,
                               f["detail"].get("diagnosis",
                                               "watch finding"),
                               _steps(f["signature"]))
                if alert:
                    ok = _email(
                        f"[custodian] {f['signature']} — "
                        f"{f['severity'].upper()}",
                        f"Signature: {f['signature']}\n"
                        f"Severity: {f['severity']}\n\n"
                        f"{f['detail'].get('diagnosis','')}\n\n"
                        f"Manual steps:\n{_steps(f['signature'])}\n\n"
                        f"Log tail:\n{f['detail'].get('log_tail','')[:1200]}")
                    conn.execute(
                        "INSERT INTO actions (signature,action,result,"
                        "created_at) VALUES (?,?,?,?)",
                        (f["signature"], "notify:email",
                         "sent" if ok else "failed/unconfigured", _now()))
                    conn.execute(
                        "UPDATE incidents SET alerted_at=? "
                        "WHERE signature=?", (_now(), f["signature"]))
                    logger.warning("ALERT %s (email %s)",
                                   f["signature"], "sent" if ok else "failed")
            _resolve_absent(conn, seen)
            conn.commit()
            conn.close()
            if HEALTHCHECKS_URL:
                try:
                    import urllib.request
                    urllib.request.urlopen(HEALTHCHECKS_URL, timeout=10)
                except Exception as exc:
                    logger.debug("healthchecks ping failed: %s", exc)
            if findings:
                logger.info("pass: %d finding(s)", len(findings))
        except Exception as exc:
            # the watcher must never die — log and keep watching
            _LAST_PASS.update({"at": _now(), "error": str(exc)[:200]})
            logger.exception("pass failed: %s", exc)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
