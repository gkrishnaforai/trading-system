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

_STARTED = time.time()
_LAST_PASS: dict[str, Any] = {"at": None, "findings": 0, "error": None,
                              "docker_ok": None, "watched": None}

# restart-count growth per poll that counts as a crash loop
RESTART_LOOP_DELTA = 2

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
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT);""")
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
  - kind: api-key
    severity: high
    needs_provider: false
    pattern: 'invalid api ?key|api ?key.*invalid|not.*valid.*api.?key'
    diagnosis: 'provider rejected its API key — fix the key in .env and recreate the service (env changes need up -d --force-recreate, not restart)'
  - kind: http-auth
    severity: high
    needs_provider: true
    pattern: 'status=(401|403)\\b|http.{0,10}(401|403)|unauthorized|forbidden'
    diagnosis: 'provider auth errors (401/403) — verify API key / entitlements in .env; some FMP endpoints are plan-gated'
  - kind: rate-limit
    severity: medium
    needs_provider: true
    keep_firing_s: 3600
    pattern: 'rate.?limit|status=429|too many requests'
    diagnosis: 'provider rate-limiting — check plan tier / call volume; persistent 429s need budget rework, not retries'
  - kind: db-conn
    severity: high
    needs_provider: false
    pattern: 'could not connect to (server|database)|connection refused.*(5432|6432|db)|psycopg.*operationalerror'
    diagnosis: 'app cannot reach postgres — check pgbouncer/postgres health and DATABASE_URL'
  - kind: disk-full
    severity: high
    needs_provider: false
    pattern: 'no space left on device|disk quota exceeded'
    diagnosis: 'host disk full — docker system df; prune images/logs or expand volume'
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
        tail = _logs(cid, tail=80)
    except Exception:
        return []
    rules, prov_re = _log_rules(conn)
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
        return [{"signature": "watch:docker-socket-unreachable",
                 "source": "watch", "severity": "high",
                 "detail": {"error": str(exc)[:300],
                            "diagnosis": "watcher cannot read the docker "
                            "socket — it sees nothing"}}]

    watched = _watched(containers, own_project)
    _LAST_PASS["watched"] = len(watched)
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

        # healthy-by-docker but config-dead — bad provider keys, plan
        # 401/403s, persistent 429s all leave the process running
        elif status == "running":
            findings.extend(_scan_app_logs(conn, c["Id"], name))
    conn.commit()
    conn.close()
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


def _mirror_pg(sig: str, sev: str, detail: dict, status: str,
               diagnosis: str, steps: str) -> None:
    """Best-effort copy into postgres custodian_incidents so the board's
    Custodian view sees watch findings. Skipped silently when DB is down
    — sqlite is the record of truth."""
    if not DATABASE_URL:
        return
    try:
        import psycopg2
        from psycopg2.extras import Json
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
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
        conn.close()
    except Exception as exc:
        logger.debug("pg mirror skipped (%s): %s", sig, exc)


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
        return row["alerted_at"] is None or reopened, "open"
    conn.execute(
        "INSERT INTO incidents (signature,source,severity,detail,"
        "diagnosis,manual_steps,first_seen,last_seen) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (sig, f["source"], f["severity"], json.dumps(f["detail"]),
         diag, steps, now, now))
    return True, "open"


def _resolve_absent(conn, seen: set[str]) -> None:
    """Resolve signatures absent this pass — except log-derived `app:`
    findings get keep_firing_for semantics (Prometheus): the evidence
    line can rotate out of the 80-line tail while the config fault
    persists, so they stay open until absent for keep_firing_s (rule
    override else KEEP_FIRING_S), clocked off last_seen."""
    now = _now()
    for r in conn.execute(
            "SELECT signature, detail, last_seen FROM incidents "
            "WHERE status != 'resolved'").fetchall():
        sig = r["signature"]
        if sig in seen:
            continue
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
            "UPDATE incidents SET status='resolved', resolved_at=? "
            "WHERE signature=?", (now, sig))


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
        res = [dict(r) for r in conn.execute(
            "SELECT signature,severity,status,occurrences,resolved_at,"
            "last_seen FROM incidents WHERE status='resolved' "
            "ORDER BY resolved_at DESC LIMIT 10")]
        acts = [dict(r) for r in conn.execute(
            "SELECT * FROM actions ORDER BY id DESC LIMIT 30")]
        return {"generated_at": _now(), "uptime_s": int(time.time() - _STARTED),
                "last_pass": _LAST_PASS, "open": op,
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
<h3>open incidents</h3>{open_t}<h3>recently resolved</h3>{res_t}
<h3>actions</h3>{act_t}<p style=color:#888>JSON: /incidents &middot; liveness: /health &middot; <a href="/rules{tok}">edit log rules</a></p>"""


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
    return _PAGE.format(
        uptime=d["uptime_s"], last=d["last_pass"]["at"],
        nfind=d["last_pass"]["findings"], proj=os.uname().nodename,
        tok=(f"?token={token}" if token else ""),
        open_t=tbl(d["open"], ["signature", "severity", "diagnosis",
                              "log", "live", "manual_steps",
                              "last_seen"]),
        res_t=tbl(d["resolved"], ["signature", "severity", "occurrences",
                                  "resolved_at"]),
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
<button type=submit>save</button></form>
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
        if path != "/rules":
            self._send(404, json.dumps({"error": "not found"}))
            return
        from urllib.parse import parse_qs, urlparse
        tok = parse_qs(urlparse(self.path).query).get("token", [""])[0]
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(min(length, 1 << 16)).decode()
            txt = parse_qs(body).get("rules", [""])[0]
            rules, _ = _compile_rules(txt)      # raises → not saved
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
        logger.info("log_rules updated via web (%d rules)", len(rules))
        self._send(200, _rules_html(
            tok, f'<p class=ok>saved — {len(rules)} rules active on '
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
                _mirror_pg(f["signature"], f["severity"], f["detail"],
                           status,
                           f["detail"].get("diagnosis", "watch finding"),
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
