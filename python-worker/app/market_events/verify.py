"""Provider-verified macro release schedule.

The baseline calendar (calendar.py) is hardcoded: BLS/Fed publish dates a
year ahead, but they move — shutdowns (Sept-2025 CPI slid 10/15→10/24),
holidays, bureau reschedules. This module reconciles our baseline against
Finnhub's economic calendar once a day and persists the authoritative
dates so downstream consumers (regime, event judge, boards) see the real
schedule — deterministic, no LLM.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.database import db
from app.observability.logging import get_logger

logger = get_logger("macro_event_verify")

# Finnhub event-name substring → (our kind, display name, severity, time_et)
_KIND_RULES = [
    (r"consumer price|cpi",        ("cpi",  "CPI inflation",        "high",    "08:30")),
    (r"producer price|ppi",        ("ppi",  "PPI producer prices",  "high",    "08:30")),
    (r"nonfarm|non-farm|employment situation|nfp",
                                   ("nfp",  "Jobs report (NFP)",    "high",    "08:30")),
    (r"fomc|interest rate decision|fed.*rate",
                                   ("fomc", "FOMC rate decision",   "extreme", "14:00")),
    (r"personal consumption|core pce|pce price|pce",
                                   ("pce",  "PCE inflation",        "high",    "08:30")),
]

_US_ONLY = {"US", "USA", "United States"}


def _num(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def reading_for(kind: str, actual, estimate) -> Optional[str]:
    """Deterministic read of a print vs consensus — no LLM."""
    a, e = _num(actual), _num(estimate)
    if a is None:
        return None
    if e is None:
        return f"printed {a:g}"
    diff = a - e
    if kind in ("cpi", "ppi", "pce"):
        if diff > 0.04:
            return "hotter than est — hawkish, equity headwind"
        if diff < -0.04:
            return "cooler than est — dovish tailwind"
        return "in line with estimates"
    if kind == "nfp":
        if diff > 30:
            return "strong payrolls — hawkish tilt"
        if diff < -30:
            return "soft payrolls — dovish tilt"
        return "near expectations"
    if kind == "fomc":
        if diff > 0:
            return "hawkish surprise"
        if diff < 0:
            return "dovish surprise"
        return "as expected"
    return None


def _classify(event_name: str, country: str) -> Optional[tuple]:
    if country and country.upper() not in _US_ONLY:
        return None
    name = (event_name or "").lower()
    for pattern, spec in _KIND_RULES:
        if re.search(pattern, name):
            return spec
    return None


def _provider_rows(today: date, days: int) -> Optional[List[Dict[str, Any]]]:
    """Economic-calendar rows, normalized to the Finnhub shape
    ({event, date, country, actual, estimate, prev}). Finnhub first;
    FMP's economic calendar is the fallback so verification still runs
    when only the FMP key is provisioned."""
    from app.config import settings

    if getattr(settings, "finnhub_api_key", None):
        from app.providers.finnhub.client import FinnhubClient
        client = FinnhubClient.from_settings()
        return client.fetch_economic_calendar(
            today.isoformat(),
            (today + timedelta(days=days)).isoformat())

    if not getattr(settings, "fmp_api_key", None):
        return None
    try:
        import requests
        r = requests.get(
            f"{settings.fmp_base_url}/economic-calendar",
            params={"from": today.isoformat(),
                    "to": (today + timedelta(days=days)).isoformat(),
                    "apikey": settings.fmp_api_key},
            timeout=20)
        items = r.json()
        if not isinstance(items, list):
            return []
        return [{"event": e.get("event") or "",
                 "date": str(e.get("date") or "")[:10],
                 "country": e.get("country") or "",
                 "actual": e.get("actual"),
                 "estimate": e.get("estimate"),
                 "prev": e.get("previous"),
                 "source": "fmp"}
                for e in items if str(e.get("date") or "")[:10]]
    except Exception as e:
        logger.warning("FMP economic calendar failed: %s", e)
        return []


def verify_and_store(days: int = 45) -> Dict[str, Any]:
    """Fetch provider calendar, reconcile vs baseline, persist overrides."""
    from .calendar import upcoming_macro_events

    today = datetime.now(timezone.utc).date()
    provider_rows = _provider_rows(today, days)
    if provider_rows is None:
        return {"skipped": "no econ-calendar provider key "
                           "(FINNHUB_API_KEY or FMP_API_KEY)",
                "stored": 0}

    mapped: List[Dict[str, Any]] = []
    for r in provider_rows:
        spec = _classify(r["event"], r.get("country") or "")
        if not spec:
            continue
        kind, name, sev, t = spec
        try:
            d = date.fromisoformat(r["date"])
        except ValueError:
            continue
        mapped.append({"kind": kind, "name": name, "date": d,
                       "severity": sev, "time_et": t,
                       "actual": r.get("actual"),
                       "estimate": r.get("estimate"),
                       "prev": r.get("prev")})

    baseline: Dict[str, List[str]] = {}
    for e in upcoming_macro_events(days):
        baseline.setdefault(e["kind"], []).append(e["date"])
    stored = rescheduled = 0
    for m in mapped:
        bases = baseline.get(m["kind"], [])
        moved = bool(bases) and m["date"].isoformat() not in bases
        # original_date = nearest baseline date this release replaced
        base = (min(bases, key=lambda b: abs(
                    (date.fromisoformat(b) - m["date"]).days))
                if moved else None)
        status = "rescheduled" if moved else "confirmed"
        db.execute_update(
            """INSERT INTO macro_event_overrides
                   (kind, name, event_date, original_date, status, source,
                    time_et, severity, actual, estimate, prev,
                    verified_at)
               VALUES (:kind, :name, :d, :orig, :status, :src,
                       :t, :sev, :act, :est, :prev, now())
               ON CONFLICT (kind, event_date) DO UPDATE SET
                   name=excluded.name, original_date=excluded.original_date,
                   status=excluded.status, time_et=excluded.time_et,
                   severity=excluded.severity,
                   actual=COALESCE(excluded.actual,
                                   macro_event_overrides.actual),
                   estimate=COALESCE(excluded.estimate,
                                     macro_event_overrides.estimate),
                   prev=COALESCE(excluded.prev,
                                 macro_event_overrides.prev),
                   verified_at=now()""",
            {"kind": m["kind"], "name": m["name"], "d": m["date"].isoformat(),
             "orig": base if moved else None, "status": status,
             "src": m.get("source") or "finnhub",
             "t": m["time_et"], "sev": m["severity"],
             "act": _num(m["actual"]), "est": _num(m["estimate"]),
             "prev": _num(m["prev"])})
        stored += 1
        rescheduled += int(moved)
    logger.info("macro calendar verified: %d events, %d rescheduled",
                stored, rescheduled)
    return {"stored": stored, "rescheduled": rescheduled}


def pending_due(now: Optional[datetime] = None,
                lookback_days: int = 5) -> List[Dict[str, Any]]:
    """Scheduled prints that are due or past but still missing their
    actual — baseline dates AND provider-rescheduled dates both count.
    This is the poller's trigger: any pending item means the release
    either hasn't printed yet or our provider hasn't reported it."""
    from .calendar import (_CPI_DATES, _PPI_DATES, _FOMC_DECISION_DATES,
                           _nth_weekday, _last_weekday, _ET)

    today = (now or datetime.now(timezone.utc)).astimezone(_ET).date()
    lo = today - timedelta(days=lookback_days)

    dues: List[tuple] = ([("cpi", d) for d in _CPI_DATES] +
                         [("ppi", d) for d in _PPI_DATES] +
                         [("fomc", d) for d in _FOMC_DECISION_DATES])
    # rule-derived dates (NFP first Friday, PCE last Friday) for the
    # lookback window — check last and current month
    for off in (-1, 0):
        m0 = today.month + off - 1
        mm = date(today.year + m0 // 12, m0 % 12 + 1, 1)
        dues.append(("nfp", _nth_weekday(mm, 4, 1)))
        dues.append(("pce", _last_weekday(mm, 4)))
    dues = [(k, d) for k, d in dues if lo <= d <= today]
    if not dues:
        return []

    try:
        rows = db.execute_query(
            """SELECT kind, event_date, original_date, actual
               FROM macro_event_overrides
               WHERE (event_date >= :lo AND event_date <= :hi)
                  OR (original_date >= :lo AND original_date <= :hi)""",
            {"lo": lo.isoformat(), "hi": today.isoformat()})
    except Exception:
        # table missing/unreadable — everything due is pending
        rows = []

    covered: set = set()
    pending: List[Dict[str, Any]] = []
    for r in rows:
        d_ev = str(r["event_date"])[:10]
        d_or = (str(r["original_date"])[:10]
                if r["original_date"] else None)
        if r["actual"] is not None:
            covered.add((r["kind"], d_ev))
            if d_or:
                covered.add((r["kind"], d_or))
        else:
            if date.fromisoformat(d_ev) <= today:
                pending.append({"kind": r["kind"], "date": d_ev,
                                "via": "override_no_actual"})
            if d_or:
                # the move itself resolves the baseline entry — its
                # pending state lives on the provider date instead
                covered.add((r["kind"], d_or))
    for k, d in dues:
        if (k, d.isoformat()) not in covered:
            pending.append({"kind": k, "date": d.isoformat(),
                            "via": "baseline_no_actual"})
    return pending


def poll_due(days: int = 45) -> Dict[str, Any]:
    """Hourly guard — re-verify only while a due print is still
    missing its actual. No pending items → no provider call."""
    pending = pending_due()
    if not pending:
        return {"skipped": "no_due_items", "stored": 0}
    out = verify_and_store(days)
    if "skipped" not in out:
        out["pending_before"] = pending
        out["pending_after"] = pending_due()
    return out


def load_overrides(days: int = 45) -> Dict[str, Dict[str, Any]]:
    """kind → {event_date: row} for recently-verified provider dates."""
    try:
        rows = db.execute_query(
            """SELECT kind, name, event_date, original_date, status,
                      time_et, severity, actual, estimate, prev, source
               FROM macro_event_overrides
               WHERE event_date >= CURRENT_DATE - 3
                 AND event_date <= CURRENT_DATE + CAST(:days AS int)
                 AND verified_at >= now() - interval '36 hours'""")
    except Exception as e:
        logger.warning(f"macro overrides unavailable: {e}")
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        out.setdefault(r["kind"], {})[str(r["event_date"])[:10]] = r
    return out
