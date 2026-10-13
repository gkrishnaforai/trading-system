"""Deterministic scheduled-event resolver.

This is deliberately separate from event interpretation: it knows when a
scheduled event exists, but never invents the released policy decision.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional

from .models import EventSeverity, EventStatus, MarketEvent, MarketEventType, PolicyBias

_ET = ZoneInfo("America/New_York")
_FOMC_DECISION_DATES = {
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29),
    date(2026, 6, 17), date(2026, 7, 29), date(2026, 9, 16),
    date(2026, 10, 28), date(2026, 12, 9),
}

# BLS CPI release schedule (published ~a year ahead) — 8:30 ET prints
_CPI_DATES = {
    date(2026, 1, 13), date(2026, 2, 11), date(2026, 3, 11),
    date(2026, 4, 10), date(2026, 5, 12), date(2026, 6, 10),
    date(2026, 7, 14), date(2026, 8, 12), date(2026, 9, 11),
    date(2026, 10, 13), date(2026, 11, 10), date(2026, 12, 10),
}
# Other scheduled market-moving dates — elections, known catalysts
_OTHER_DATES = {
    date(2026, 11, 3): ("US midterm elections", "election",
                        "high"),
}

# PPI typically prints the morning after CPI week releases
_PPI_DATES = {
    date(2026, 1, 14), date(2026, 2, 12), date(2026, 3, 12),
    date(2026, 4, 13), date(2026, 5, 13), date(2026, 6, 11),
    date(2026, 7, 15), date(2026, 8, 13), date(2026, 9, 14),
    date(2026, 10, 14), date(2026, 11, 12), date(2026, 12, 11),
}


def _nth_weekday(d: date, weekday: int, n: int) -> date:
    """nth `weekday` (0=Mon) of d's month — e.g. first Friday for NFP."""
    cur = d.replace(day=1)
    seen = 0
    while True:
        if cur.weekday() == weekday:
            seen += 1
            if seen == n:
                return cur
        cur += timedelta(days=1)


def _last_weekday(d: date, weekday: int) -> date:
    """Last `weekday` of d's month — e.g. last Friday for PCE."""
    cur = d.replace(day=28)
    while True:
        cur += timedelta(days=1)
        if cur.month != d.month:
            cur -= timedelta(days=1)
            break
    while cur.weekday() != weekday:
        cur -= timedelta(days=1)
    return cur


def upcoming_macro_events(days: int = 45,
                          now: Optional[datetime] = None
                          ) -> list[dict]:
    """Forward macro calendar — the dates that move regime: FOMC,
    jobs report, CPI, PPI, PCE. Rule-derived entries are flagged
    `est`; hardcoded ones carry the published schedule."""
    cur = (now or datetime.now(timezone.utc))
    today = cur.astimezone(_ET).date()
    evts: list[dict] = []

    def add(name: str, kind: str, d: date, time_et: str,
            severity: str, est: bool = False):
        gap = (d - today).days
        if gap < -1 or gap > days:
            return
        evts.append({"name": name, "kind": kind, "date": str(d),
                     "time_et": time_et, "severity": severity,
                     "days_away": max(0, gap), "est": est})

    for d, (name, kind, sev) in _OTHER_DATES.items():
        add(name, kind, d, "all-day", sev)
    for d in _FOMC_DECISION_DATES:
        add("FOMC rate decision", "fomc", d, "14:00", "extreme")
    for d in _CPI_DATES:
        add("CPI inflation", "cpi", d, "08:30", "high")
    for d in _PPI_DATES:
        add("PPI producer prices", "ppi", d, "08:30", "high", est=True)
    # NFP — first Friday of each month, 8:30 ET (structural rule)
    # PCE — last Friday of each month, 8:30 ET (structural rule)
    for off in range(0, 3):
        m0 = today.month - 1 + off
        mm = date(today.year + m0 // 12, m0 % 12 + 1, 1)
        add("Jobs report (NFP)", "nfp", _nth_weekday(mm, 4, 1),
            "08:30", "high", est=True)
        add("PCE inflation", "pce", _last_weekday(mm, 4),
            "08:30", "high", est=True)
    evts = _apply_verified_overrides(evts, today, days)
    evts.sort(key=lambda e: e["date"])
    return evts


def _apply_verified_overrides(evts: list, today: date, days: int) -> list:
    """Overlay provider-verified dates on the hardcoded baseline.

    When Finnhub's calendar disagrees with the baked-in date for a kind
    (bureau reschedule, shutdown delay, holiday shift) the verified date
    wins and the entry is flagged `rescheduled`/`rescheduled_from`.
    Verified dates with no baseline counterpart are appended outright."""
    try:
        from .verify import load_overrides
        overrides = load_overrides(days)
    except Exception:
        return evts
    if not overrides:
        return evts

    used: set = set()  # (kind, date) pairs already consumed
    out: list = []
    for e in evts:
        ver = overrides.get(e["kind"])
        if not ver:
            out.append(e)
            continue
        if e["date"] in ver:
            e = {**e, "verified": True}
            used.add((e["kind"], e["date"]))
            out.append(e)
            continue
        # baseline date absent from provider schedule — nearest verified
        # date within ±20d is a reschedule; anything else is unconfirmed
        base = date.fromisoformat(e["date"])
        cand = min(
            ((d, abs((date.fromisoformat(d) - base).days))
             for d in ver if (e["kind"], d) not in used),
            key=lambda p: p[1], default=None)
        if cand and cand[1] <= 20:
            row = ver[cand[0]]
            used.add((e["kind"], cand[0]))
            out.append({**e, "date": cand[0],
                        "time_et": row.get("time_et") or e["time_et"],
                        "days_away": max(0, (date.fromisoformat(cand[0])
                                             - today).days),
                        "rescheduled": True, "rescheduled_from": e["date"],
                        "verified": True})
        else:
            out.append({**e, "unconfirmed": True})
    # provider events with no baseline counterpart — new releases
    for kind, dates in overrides.items():
        for d, row in dates.items():
            if (kind, d) not in used:
                base = date.fromisoformat(d)
                gap = (base - today).days
                if -1 <= gap <= days:
                    out.append({"name": row["name"], "kind": kind,
                                "date": d,
                                "time_et": row.get("time_et") or "08:30",
                                "severity": row.get("severity") or "high",
                                "days_away": max(0, gap), "est": False,
                                "verified": True, "source": "finnhub"})
    return out


def resolve_current_market_event(
    now: Optional[datetime] = None,
) -> Optional[MarketEvent]:
    """Return the current FOMC event window, if one is active.

    The active window begins on the calendar day before the decision and ends
    at the end of the decision day. Release time is 14:00 America/New_York.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = current.astimezone(_ET)
    decision_date = next(
        (d for d in sorted(_FOMC_DECISION_DATES)
         if d - timedelta(days=1) <= local.date() <= d),
        None,
    )
    if decision_date is None:
        return None

    release_local = datetime.combine(decision_date, time(14, 0), tzinfo=_ET)
    status = EventStatus.RELEASED if local >= release_local else EventStatus.SCHEDULED
    scheduled = datetime.combine(decision_date, time(14, 0), tzinfo=_ET).astimezone(timezone.utc)
    return MarketEvent(
        event_id=f"fomc-{decision_date.isoformat()}",
        event_type=MarketEventType.FOMC,
        event_name="FOMC rate decision",
        severity=EventSeverity.EXTREME,
        status=status,
        scheduled_at=scheduled,
        timezone="America/New_York",
        policy_bias=PolicyBias.UNKNOWN,
        future_policy={},
        source="federal_reserve_schedule_2026",
        as_of=current,
    )
