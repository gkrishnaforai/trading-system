"""Job scheduler — the dispatcher half of the registry.

Reads `job_definitions` (the catalog — name, purpose, cron, deps,
enabled), fires due jobs through the same _run_job path the buttons
use, and records everything into job_runs.

AutoSys semantics, deliberately minimal:
  - 5-field cron, UTC  (min hour dom month dow; dow 0/7 = Sunday)
  - depends_on        predecessors must have an ERROR-FREE job_runs
                      row within dep_max_age_h, else the job waits
  - box 'all'         fires _run_all (dependency order lives in code)
  - dedup             a job can't fire twice inside the same minute
  - enabled=false     manual-only — scheduling is opt-in per job
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _field_match(field: str, val: int, lo: int, hi: int) -> bool:
    for part in field.split(","):
        if part == "*":
            return True
        if "/" in part:
            rng, step = part.split("/", 1)
            step = int(step)
            a, b = (lo, hi) if rng == "*" else map(int, rng.split("-", 1))
            if a <= val <= b and (val - a) % step == 0:
                return True
        elif "-" in part:
            a, b = map(int, part.split("-", 1))
            if a <= val <= b:
                return True
        else:
            try:
                if int(part) == val:
                    return True
            except ValueError:
                pass
    return False


def cron_match(expr: str, dt: datetime) -> bool:
    """Minimal 5-field cron matcher — enough for the registry's
    schedules without taking a dependency on croniter."""
    try:
        f = expr.split()
        if len(f) != 5:
            return False
        dow = (dt.weekday() + 1) % 7          # cron: 0/7 = Sunday
        vals = [(f[0], dt.minute, 0, 59), (f[1], dt.hour, 0, 23),
                (f[2], dt.day, 1, 31), (f[3], dt.month, 1, 12),
                (f[4], dow, 0, 7)]
        return all(_field_match(*v) for v in vals)
    except Exception:
        return False


def _missed_slot(expr: str, last_run, now: datetime,
                 max_days: int = 8) -> bool:
    """Catch-up — was the job due at ANY minute between its last run
    and now? Scans backward minute-by-minute; a missed slot fires on
    the next live tick (anacron semantics). Never-run jobs don't
    catch up — they'd fire on the next scheduled slot."""
    from datetime import timedelta
    if last_run is None:
        return False
    t = now.replace(second=0, microsecond=0)
    floor = max(last_run.replace(tzinfo=timezone.utc),
                t - timedelta(days=max_days))
    while t > floor:
        t -= timedelta(minutes=1)
        if cron_match(expr, t):
            return True
    return False


async def tick(now: datetime | None = None) -> dict[str, Any]:
    """One dispatcher cycle (~1/min): fire enabled+due jobs whose
    dependencies have clean recent runs. 'Due' = scheduled now OR a
    slot was missed since the last run (catch-up — the system being
    off at 22:00 doesn't lose the night's work)."""
    import asyncio
    from app.database import db
    from app.api.board_api import JOBS, _jobs, _run_job, _run_all

    now = now or datetime.now(timezone.utc)
    rows = db.execute_query(
        "SELECT * FROM job_definitions WHERE enabled AND cron IS NOT NULL"
        " ORDER BY priority")          # lower fires first when due
    fired, skipped = [], []
    for r in rows:
        name = r["name"]
        # same-minute dedup + last run — pulled up front because the
        # catch-up check needs it too
        last = db.execute_query(
            "SELECT max(ran_at) m FROM job_runs WHERE name=:n",
            {"n": name})[0]["m"]
        due_now = cron_match(r["cron"], now)
        due_catchup = (not due_now and r["kind"] != "box"
                       and _missed_slot(r["cron"], last, now))
        if not (due_now or due_catchup):
            continue
        if last and last.replace(tzinfo=timezone.utc) >= \
                now.replace(second=0, microsecond=0):
            skipped.append(f"{name} already fired")
            continue
        state = _jobs.get(name) or {}
        if state.get("running"):
            skipped.append(f"{name} running")
            continue
        # cooldown
        if last and (now - last.replace(tzinfo=timezone.utc)
                     ).total_seconds() < (r["cooldown_min"] or 15) * 60:
            skipped.append(f"{name} cooldown")
            continue
        # dependency gate — every predecessor needs a clean recent run
        deps = r.get("depends_on") or []
        unmet = []
        for d in deps:
            dr = db.execute_query(
                "SELECT ran_at, error FROM job_runs WHERE name=:n"
                " ORDER BY ran_at DESC LIMIT 1", {"n": d})
            if not dr or dr[0].get("error") or \
                    (now - dr[0]["ran_at"].replace(tzinfo=timezone.utc)
                     ).total_seconds() > (r["dep_max_age_h"] or 24) * 3600:
                unmet.append(d)
        if unmet:
            skipped.append(f"{name} waiting on {unmet}")
            continue
        asyncio.create_task(
            _run_all() if r["kind"] == "box" else _run_job(name))
        fired.append(f"{name}(catchup)" if due_catchup else name)
    return {"fired": fired, "skipped": skipped,
            "at": now.isoformat(timespec="seconds")}


def sync_registry() -> int:
    """Keep the catalog in sync with the code — every JOBS entry gets
    a row (label/purpose preserved on conflict)."""
    from app.database import db
    from app.api.board_api import JOBS
    n = 0
    for name, (label, _fn) in JOBS.items():
        db.execute_update(
            "INSERT INTO job_definitions (name, label) VALUES (:n,:l)"
            " ON CONFLICT (name) DO UPDATE SET label=:l",
            {"n": name, "l": label})
        n += 1
    db.execute_update(
        "INSERT INTO job_definitions (name, label, kind)"
        " VALUES ('all','REFRESH EVERYTHING','box')"
        " ON CONFLICT (name) DO UPDATE SET label='REFRESH EVERYTHING',"
        " kind='box'")
    return n


def set_schedule(name: str, cron: str | None, enabled: bool) -> dict:
    """UI/ops write path — the only mutation the dispatcher honors."""
    from app.database import db
    if cron is not None and cron.strip():
        # validate the expression before trusting it
        probe = cron_match(cron.strip(), datetime(2026, 1, 1, 0, 0))
        fields = cron.strip().split()
        if len(fields) != 5:
            return {"ok": False, "error": "need 5 cron fields"}
    db.execute_update(
        "UPDATE job_definitions SET cron=:c, enabled=:e,"
        " updated_at=now() WHERE name=:n",
        {"c": (cron or "").strip() or None, "e": enabled, "n": name})
    return {"ok": True, "name": name, "cron": cron, "enabled": enabled}


def next_fire(expr: str, now: datetime,
              max_days: int = 8) -> Optional[datetime]:
    """First minute after `now` matching `expr` (UTC). None if the
    cron is unparseable or nothing fires within max_days."""
    from datetime import timedelta
    if not expr or not str(expr).strip():
        return None
    t = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = t + timedelta(days=max_days)
    while t < end:
        if cron_match(expr, t):
            return t
        t += timedelta(minutes=1)
    return None


def catalog() -> list[dict[str, Any]]:
    """Registry view for the page — definition + last run + next
    scheduled fire, one row."""
    from app.database import db
    rows = db.execute_query(
        "SELECT d.name, d.label, d.purpose, d.kind, d.cron, d.enabled,"
        " d.depends_on, d.priority, r.ran_at AS last_run,"
        " r.error AS last_error, r.duration_s"
        " FROM job_definitions d"
        " LEFT JOIN LATERAL (SELECT ran_at, error, duration_s"
        "   FROM job_runs j WHERE j.name=d.name"
        "   ORDER BY ran_at DESC LIMIT 1) r ON true"
        " ORDER BY d.name")
    now = datetime.now(timezone.utc)
    for r in rows:
        nxt = next_fire(r.get("cron"), now) \
            if r.get("enabled") and r.get("cron") else None
        r["next_run"] = nxt.isoformat() if nxt else None
    return rows
