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
import smtplib
import socket
import sqlite3
import threading
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s custodian-watch %(message)s")
logger = logging.getLogger("custodian-watch")

DOCKER_SOCK = os.getenv("DOCKER_SOCK", "/var/run/docker.sock")
DB_PATH = os.getenv("WATCH_DB", "/data/custodian.db")
POLL_SECONDS = int(os.getenv("WATCH_POLL_SECONDS", "60"))
HEALTHCHECKS_URL = os.getenv("HEALTHCHECKS_URL", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
HEARTBEAT = "/data/heartbeat"
WATCH_PORT = int(os.getenv("WATCH_PORT", "8100"))
WATCH_TOKEN = os.getenv("WATCH_TOKEN", "")   # Bearer token for the API

_STARTED = time.time()
_LAST_PASS: dict[str, Any] = {"at": None, "findings": 0, "error": None}

# restart-count growth per poll that counts as a crash loop
RESTART_LOOP_DELTA = 2

_MANUAL_STEPS = [
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
    """This container's own compose project — filter siblings by it."""
    try:
        me = _inspect(socket.gethostname())
        return (me.get("Config", {}).get("Labels", {})
                .get("com.docker.compose.project", ""))
    except Exception:
        return ""


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
            updated TEXT);""")
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


def _sense(project: str) -> list[dict[str, Any]]:
    findings = []
    try:
        containers = _list_containers()
    except Exception as exc:
        logger.warning("docker socket unreachable: %s", exc)
        return findings

    conn = _db()
    for c in containers:
        labels = c.get("Labels") or {}
        if project and labels.get("com.docker.compose.project") != project:
            continue
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
    conn.execute(
        "UPDATE incidents SET status='resolved', resolved_at=? "
        "WHERE status != 'resolved'",
        (_now(),)) if not seen else conn.execute(
        f"UPDATE incidents SET status='resolved', resolved_at=? "
        f"WHERE status != 'resolved' AND signature NOT IN "
        f"({','.join('?' * len(seen))})",
        (_now(), *seen))


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
<h3>actions</h3>{act_t}<p style=color:#888>JSON: /incidents &middot; liveness: /health</p>"""


def _row_html(r, cols):
    sev = r.get("severity", "")
    cls = ' class="hi"' if sev == "high" else ' class="med"' if sev in ("medium",) else ""
    cells = "".join(
        f"<td{cls if c == 'severity' else ''}>"
        + (f"<pre>{r[c]}</pre>" if c == "log" else str(r.get(c, "") or ""))
        + "</td>" for c in cols)
    return f"<tr>{cells}</tr>"


def _incidents_html() -> str:
    d = _incidents_json()
    def tbl(rows, cols):
        head = "".join(f"<th>{c}" for c in cols)
        body = "".join(_row_html(r, cols) for r in rows) or \
            f"<tr><td colspan={len(cols)} class=ok>none</td></tr>"
        return f"<table><tr>{head}</tr>{body}</table>"
    for r in d["open"]:
        try:
            r["log"] = json.loads(r.get("detail") or "{}").get("log_tail", "")
        except Exception:
            r["log"] = ""
    return _PAGE.format(
        uptime=d["uptime_s"], last=d["last_pass"]["at"],
        nfind=d["last_pass"]["findings"], proj=os.uname().nodename,
        open_t=tbl(d["open"], ["signature", "severity", "status",
                              "occurrences", "last_seen", "log"]),
        res_t=tbl(d["resolved"], ["signature", "severity", "occurrences",
                                  "resolved_at"]),
        act_t=tbl(d["actions"], ["created_at", "signature", "action",
                                 "result"]))


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
        return self.headers.get("Authorization") == f"Bearer {WATCH_TOKEN}"

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
                project = _project_name()
                out = [{"name": (c.get("Names") or ["?"])[0].lstrip("/"),
                        "status": c.get("State"), "health": c.get("Status")}
                       for c in _list_containers()
                       if not project or (c.get("Labels") or {}).get(
                           "com.docker.compose.project") == project]
                self._send(200, json.dumps({"containers": out}))
            elif path == "/":
                self._send(200, _incidents_html(), "text/html")
            else:
                self._send(404, json.dumps({"error": "not found"}))
        except Exception as exc:
            self._send(500, json.dumps({"error": str(exc)[:300]}))

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
