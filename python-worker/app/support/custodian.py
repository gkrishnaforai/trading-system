"""Custodian — the support-agent supervisor.

Runs the incident loop every pass (and on a 10-min background loop):
    sensors → dedupe/upsert incident → diagnoser → tier gate →
    remediator (bounded actions only) → verifier next pass → escalate

Design follows the production SRE-agent standard (Stratus/AURA):
the diagnoser PROPOSES, a deterministic tier gate DISPOSES. Nothing
here restarts containers or touches data — the riskiest action is
re-kicking a refresh job, with a cooldown and an attempt cap before
it escalates to the human on the Daily Board.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

COOLDOWN_MIN = 15           # min between remediation attempts/incident
MAX_ATTEMPTS = 3            # per incident before escalate
STALE_H = {"momentum": 30,  # flag freshness SLA (h) — weekend-safe is
           "fundamental": 36,   # handled by occurrence counting
           "flywheel": 36}

# signature prefix → concrete human steps when auto-remediation is out
_MANUAL_STEPS = [
    ("db:unreachable",
     "1. docker ps — postgres/pgbouncer up?  2. Check DATABASE_URL env "
     "on worker.  3. pgbouncer pool saturated → restart pgbouncer.  "
     "4. Postgres down → check volume/logs, restart, verify SELECT 1."),
    ("stale:momentum",
     "1. job_runs → momentum last error.  2. Verify intraday_prices_only "
     "schedule is landing fresh bars (daily_bars recent dates).  "
     "3. Kick momentum from Job Scheduler.  4. If provider throttled, "
     "check FMP/Yahoo keys."),
    ("stale:fundamental",
     "1. job_runs → fund-flags last error.  2. FMP key valid? (401s in "
     "worker log = bad key).  3. Kick fund-flags manually.  "
     "4. Check flywheel feed isn't stuck upstream."),
    ("stale:flywheel",
     "1. job_runs → flywheel/refresh errors.  2. FMP fundamentals "
     "endpoint health.  3. Kick the refresh job; watch job_runs for "
     "a clean completion."),
    ("scan:alerts",
     "1. Worker log → alert scan traceback.  2. Provider connectivity "
     "from inside the worker container.  3. Re-run the scan; if it "
     "fails same way, the bug is in the scan path not the data."),
    ("job:",
     "1. Job Scheduler page → run the job manually, read its "
     "job_runs.error.  2. Check the job handler + provider keys "
     "(FMP/FINNHUB/FRED/ALPHAVANTAGE).  3. Fix, re-run, resolve here."),
]


def _manual_steps(sig: str) -> str:
    for pre, steps in _MANUAL_STEPS:
        if sig.startswith(pre):
            return steps
    return ("Unknown signature — inspect custodian_actions and the "
            "worker logs for the failing component, fix the root "
            "cause, then mark resolved.")


def _raise_technical_alert(sig: str, diagnosis: str, severity: str,
                           attempts: int, detail: dict) -> None:
    """Escalation = a technical alert into universal_events — the alert
    engine can notify on 'custodian_escalation' events; the Custodian
    page surfaces it regardless."""
    from app.database import db
    steps = _manual_steps(sig)
    try:
        db.execute_update(
            """INSERT INTO universal_events
                   (event_id, event_type, entity_type, entity_id,
                    event_data, event_timestamp, data_source,
                    processing_status)
               VALUES (gen_random_uuid(), 'custodian_escalation',
                       'system', :sig, CAST(:d AS jsonb), now(),
                       'custodian', 'pending')""",
            {"sig": sig,
             "d": _j({"signature": sig, "diagnosis": diagnosis,
                      "severity": severity, "attempts": attempts,
                      "detail": detail, "manual_steps": steps,
                      "requires_manual_intervention": True})})
    except Exception as exc:
        logger.warning("custodian alert emit failed for %s: %s", sig, exc)
    logger.warning("CUSTODIAN ESCALATION %s — %s | manual: %s",
                   sig, diagnosis, steps)

# ── sensors ────────────────────────────────────────────────────────────


def _sense() -> list[dict[str, Any]]:
    """Worker 1 — deterministic detectors. Each finding is a signature
    + detail; no judgment here."""
    from app.database import db
    findings = []

    # job errors — the refresh panel's own ledger
    try:
        from app.api.board_api import _jobs
        for name, st in (_jobs or {}).items():
            if st.get("error") and name != "all":
                findings.append({
                    "signature": f"job:{name}:error", "source": "jobs",
                    "severity": "medium",
                    "detail": {"error": str(st["error"])[:400],
                               "at": st.get("at")}})
    except Exception:
        pass

    # alert-scan errors
    try:
        from app.alerts.service import scan_status
        s = scan_status()
        if s.get("last_error"):
            findings.append({
                "signature": "scan:alerts:error", "source": "scan",
                "severity": "medium",
                "detail": {"error": str(s["last_error"])[:400]}})
    except Exception:
        pass

    # data staleness — flags older than their SLA mean the board is
    # scoring on yesterday's tape
    for label, sql in (
        ("momentum", "SELECT max(momentum_updated_at) m FROM stocks"),
        ("fundamental", "SELECT max(fundamental_updated_at) m "
                        "FROM stocks WHERE fundamental_state IS NOT NULL"),
        ("flywheel", "SELECT max(updated_at) m FROM symbol_flywheel"),
    ):
        try:
            m = db.execute_query(sql)[0].get("m")
            if not m:
                continue
            age_h = (datetime.now(timezone.utc)
                     - m.replace(tzinfo=timezone.utc)
                     ).total_seconds() / 3600
            if age_h > STALE_H[label]:
                findings.append({
                    "signature": f"stale:{label}", "source": "freshness",
                    "severity": "high" if age_h > 2 * STALE_H[label]
                                else "medium",
                    "detail": {"age_hours": round(age_h, 1),
                               "sla_h": STALE_H[label]}})
        except Exception:
            pass

    # DB reachability — if this fails, everything above is unknowable
    try:
        db.execute_query("SELECT 1")
    except Exception as exc:
        findings.append({"signature": "db:unreachable",
                         "source": "db", "severity": "high",
                         "detail": {"error": str(exc)[:300]}})
    return findings


# ── diagnoser ──────────────────────────────────────────────────────────

_RULES = [
    ("job:", "retry job", "retry", 1),
    ("scan:alerts", "retry alert scan", "retry:alerts", 1),
    ("stale:momentum", "kick momentum refresh", "kick:momentum", 2),
    ("stale:fundamental", "kick fund-flags refresh",
     "kick:fund-flags", 2),
    ("stale:flywheel", "kick flywheel refresh", "kick:flywheel", 2),
    ("db:unreachable", "DB unreachable — human check required",
     "escalate", 3),
]


def _diagnose(f: dict) -> tuple[str, str, int]:
    """Worker 2 — signature → (diagnosis, remediation, tier)."""
    sig = f["signature"]
    for pre, diag, rem, tier in _RULES:
        if sig.startswith(pre):
            return diag, rem, tier
    return "unknown signature — needs eyes", "escalate", 3


# ── remediator ─────────────────────────────────────────────────────────


async def _remediate(sig: str, action: str, tier: int) -> str:
    """Worker 3 — bounded executor. T1/T2 only touch refresh jobs,
    each with its own already_running guard; T3 does nothing but mark
    the incident for the human."""
    from app.database import db
    if tier >= 3 or action == "escalate":
        result = "escalated — human check needed"
    else:
        try:
            if action == "retry:alerts":
                from app.alerts import service as alert_service
                await alert_service.run_scan_job()
                result = "alert scan re-kicked"
            else:
                job = (sig.split(":")[1] if action == "retry"
                       else action.split(":", 1)[-1])
                from app.api.board_api import JOBS, _jobs, _run_job
                if job not in JOBS:
                    result = f"unknown job '{job}' — escalate"
                elif _jobs.get(job, {}).get("running"):
                    result = f"{job} already running"
                else:
                    import asyncio
                    asyncio.create_task(_run_job(job))
                    result = f"kicked {job}"
        except Exception as exc:
            result = f"remediation failed: {exc}"
    db.execute_update(
        "INSERT INTO custodian_actions (signature, action, tier,"
        " result) VALUES (:s,:a,:t,:r)",
        {"s": sig, "a": action, "t": tier, "r": result[:400]})
    return result


# ── supervisor ─────────────────────────────────────────────────────────


async def run_pass() -> dict[str, Any]:
    """One supervisor cycle. Idempotent: incidents upsert on signature,
    remediations gated by cooldown + attempt cap, mitigations verified
    by the NEXT pass (signature gone = resolved)."""
    from app.database import db
    findings = _sense()
    seen = {f["signature"] for f in findings}
    acts = []

    # verify: incidents whose signature no longer fires → resolved
    db.execute_update(
        "UPDATE custodian_incidents SET status='resolved',"
        " resolved_at=now() WHERE status IN ('open','mitigated')"
        " AND signature != ALL(:s) AND signature NOT LIKE 'db:%'",
        {"s": list(seen) or [""]})

    def _escalate(sig: str, diag: str, f: dict, attempts: int) -> None:
        """Terminal state — mark escalated, stamp manual steps, raise
        the technical alert exactly once per incident."""
        row = db.execute_query(
            "SELECT status, alerted_at FROM custodian_incidents"
            " WHERE signature=:s", {"s": sig})
        was_esc = row and row[0]["status"] == "escalated"
        db.execute_update(
            "UPDATE custodian_incidents SET status='escalated',"
            " manual_steps=:ms WHERE signature=:s",
            {"s": sig, "ms": _manual_steps(sig)})
        if not was_esc and not (row and row[0]["alerted_at"]):
            _raise_technical_alert(sig, diag, f["severity"],
                                   attempts, f["detail"])
            db.execute_update(
                "UPDATE custodian_incidents SET alerted_at=now()"
                " WHERE signature=:s", {"s": sig})
            acts.append(f"{sig} → ESCALATED (technical alert raised)")

    for f in findings:
        sig = f["signature"]
        diag, rem, tier = _diagnose(f)
        existing = db.execute_query(
            "SELECT status, attempts, last_seen FROM"
            " custodian_incidents WHERE signature=:s", {"s": sig})
        if existing:
            row = existing[0]
            # recurring after a 'resolved' → reopen + count occurrence
            occ_bump = ", occurrences = occurrences + 1," \
                " alerted_at = NULL" if row["status"] == "resolved" \
                else ""
            db.execute_update(
                "UPDATE custodian_incidents SET status='open',"
                " last_seen=now(), detail=CAST(:d AS jsonb),"
                " severity=:sv, diagnosis=:dg, remediation=:rm"
                f"{occ_bump} WHERE signature=:s",
                {"s": sig, "d": _j(f["detail"]), "sv": f["severity"],
                 "dg": diag, "rm": rem})
            attempts, last = row["attempts"], row["last_seen"]
        else:
            db.execute_update(
                "INSERT INTO custodian_incidents"
                " (signature, source, severity, detail, diagnosis,"
                "  remediation, manual_steps) VALUES (:s,:src,:sv,"
                " CAST(:d AS jsonb),:dg,:rm,:ms)",
                {"s": sig, "src": f["source"], "sv": f["severity"],
                 "d": _j(f["detail"]), "dg": diag, "rm": rem,
                 "ms": _manual_steps(sig)})
            attempts, last = 0, None

        # tier gate + cooldown + attempt cap — the disposal layer.
        # cooldown measured against the LAST REMEDIATION (last_seen is
        # refreshed every pass, so it can't carry the cooldown)
        la = db.execute_query(
            "SELECT max(created_at) m FROM custodian_actions"
            " WHERE signature=:s", {"s": sig})
        la_t = la[0]["m"] if la else None
        mins = ((datetime.now(timezone.utc)
                 - la_t.replace(tzinfo=timezone.utc)).total_seconds() / 60
                if la_t else 9999)
        if tier >= 3:
            _escalate(sig, diag, f, attempts)
        elif attempts < MAX_ATTEMPTS \
                and mins >= COOLDOWN_MIN * (attempts > 0):
            res = await _remediate(sig, rem, tier)
            hit_cap = attempts + 1 >= MAX_ATTEMPTS
            db.execute_update(
                "UPDATE custodian_incidents SET attempts=attempts+1,"
                " status=CASE WHEN attempts+1>=:cap THEN 'escalated'"
                " ELSE 'mitigated' END WHERE signature=:s",
                {"s": sig, "cap": MAX_ATTEMPTS})
            acts.append(f"{sig} → {rem} ({res})")
            if hit_cap:
                _escalate(sig, diag, f, attempts + 1)
        elif attempts >= MAX_ATTEMPTS:
            _escalate(sig, diag, f, attempts)
    return {"findings": len(findings), "actions": acts,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _j(d) -> str:
    import json
    return json.dumps(d or {})


def incidents() -> dict[str, Any]:
    from app.database import db
    open_i = db.execute_query(
        "SELECT * FROM custodian_incidents WHERE status != 'resolved'"
        " ORDER BY last_seen DESC")
    actions = db.execute_query(
        "SELECT * FROM custodian_actions ORDER BY id DESC LIMIT 40")
    resolved = db.execute_query(
        "SELECT signature, severity, attempts, occurrences,"
        " resolved_at, last_seen FROM custodian_incidents"
        " WHERE status = 'resolved' ORDER BY resolved_at DESC"
        " LIMIT 10")
    return {"open": open_i, "actions": actions,
            "resolved": resolved,
            "config": {"cooldown_min": COOLDOWN_MIN,
                       "max_attempts": MAX_ATTEMPTS}}
