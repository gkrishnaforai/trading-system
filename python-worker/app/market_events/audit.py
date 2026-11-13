"""Weekly calendar audit — the change-report layer over the existing
refresh machinery.

The refresh jobs already run (econ-cal-verify 3x daily, flywheel
weeknights); nothing reports *what moved*. Once a week this job:

  macro     re-runs verify_and_store(45d), fingerprints the upcoming
            event list and diffs it against last week's snapshot —
            added / moved / removed scheduled events are journaled
  earnings  fingerprints stocks.next_earnings_date across the tracked
            universe (book ∪ scan members), diffs vs last week, then
            refreshes stale/blind symbols and cross-checks FMP's
            windowed calendar against our dates for the next 30d —
            disagreements are flagged, never silently written
  digest    a single alert_items row summarizing the week's moves

Every diff row lands in calendar_audit; snapshot rows (scope=...)
carry the full fingerprint so next week's diff is point-in-time.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_EARNINGS_XCHECK_DAYS = 30   # FMP cross-check window
_STALE_REFRESH_CAP = 80      # bound the per-symbol yfinance sweep


# ------------------------------------------------------------------
# pure diffs — testable, no DB
# ------------------------------------------------------------------

def _diff_macro(before: list[dict], after: list[dict]) -> list[dict]:
    """Event-level diff on [(kind,date,name)] fingerprints. A removed
    (kind,name) paired with an added (kind,name) is a move, not a
    delete+insert."""
    def key(e):
        return (e["kind"], e["date"])

    b_keys = {key(e): e for e in before}
    a_keys = {key(e): e for e in after}
    removed = [e for k, e in b_keys.items() if k not in a_keys]
    added = [e for k, e in a_keys.items() if k not in b_keys]

    changes: list[dict] = []
    consumed: set[int] = set()
    for r in removed:
        mate = next((i for i, a in enumerate(added)
                     if i not in consumed
                     and a["kind"] == r["kind"]
                     and a["name"] == r["name"]), None)
        if mate is not None:
            consumed.add(mate)
            changes.append({"event_kind": r["kind"], "name": r["name"],
                            "change_type": "moved",
                            "old_date": r["date"],
                            "new_date": added[mate]["date"]})
        else:
            changes.append({"event_kind": r["kind"], "name": r["name"],
                            "change_type": "removed",
                            "old_date": r["date"], "new_date": None})
    for i, a in enumerate(added):
        if i not in consumed:
            changes.append({"event_kind": a["kind"], "name": a["name"],
                            "change_type": "added",
                            "old_date": None, "new_date": a["date"]})
    return changes


def _diff_earnings(before: dict, after: dict) -> list[dict]:
    """symbol → next_earnings_date map diff. Dates compared as iso
    strings — snapshots round-trip through jsonb."""
    changes: list[dict] = []
    for sym, new in after.items():
        old = before.get(sym)
        if new and old and new != old:
            changes.append({"symbol": sym, "change_type": "moved",
                            "old_date": old, "new_date": new})
        elif new and not old:
            changes.append({"symbol": sym, "change_type": "added",
                            "old_date": None, "new_date": new})
        elif old and not new:
            changes.append({"symbol": sym, "change_type": "removed",
                            "old_date": old, "new_date": None})
    return changes


# ------------------------------------------------------------------
# journal helpers
# ------------------------------------------------------------------

def _last_snapshot(scope: str) -> Optional[Any]:
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT detail FROM calendar_audit WHERE scope=:s"
            " ORDER BY id DESC LIMIT 1", {"s": scope})
    except Exception:
        return None
    if not rows:
        return None
    d = rows[0].get("detail")
    if isinstance(d, str):
        d = json.loads(d)
    return (d or {}).get("fingerprint")


def _journal(run_id: str, scope: str, change_type: str,
             old_date=None, new_date=None, event_kind=None,
             symbol=None, detail=None) -> None:
    from app.database import db
    db.execute_update(
        "INSERT INTO calendar_audit (run_id, as_of, scope, event_kind,"
        " symbol, change_type, old_date, new_date, detail)"
        " VALUES (:r,:a,:s,:k,:y,:c,:o,:n,CAST(:d AS jsonb))",
        {"r": run_id, "a": date.today(), "s": scope, "k": event_kind,
         "y": symbol, "c": change_type,
         "o": str(old_date) if old_date else None,
         "n": str(new_date) if new_date else None,
         "d": json.dumps(detail or {}, default=str)})


def _snapshot(run_id: str, scope: str, fingerprint) -> None:
    _journal(run_id, scope, "snapshot", detail={
        "fingerprint": fingerprint, "captured": str(date.today())})


# ------------------------------------------------------------------
# earnings legs
# ------------------------------------------------------------------

def _tracked_symbols() -> list[str]:
    from app.database import db
    from app.signals import symbol_tiers
    rows = db.execute_query(symbol_tiers._active_sql())
    return [r["symbol"] for r in rows]


def _next_earnings_map(symbols: list[str]) -> dict:
    from app.database import db
    if not symbols:
        return {}
    rows = db.execute_query(
        "SELECT symbol, next_earnings_date FROM stocks"
        " WHERE symbol = ANY(:syms)", {"syms": symbols})
    return {r["symbol"]: (str(r["next_earnings_date"])[:10]
                          if r["next_earnings_date"] else None)
            for r in rows}


def _stale_candidates(symbols: list[str], cur: dict) -> list[str]:
    """Symbols whose stored date is suspect: past (should have rolled)
    or NULL despite a reported-print history (real reporters shouldn't
    be blind). NULL-with-no-history is legitimately uncovered — never
    refreshed into a fake date."""
    from app.database import db
    today = date.today()
    stale = [s for s in symbols
             if cur.get(s) and date.fromisoformat(cur[s]) < today]
    if not symbols:
        return stale
    blind = db.execute_query(
        "SELECT s.symbol FROM stocks s WHERE s.symbol = ANY(:syms)"
        " AND s.next_earnings_date IS NULL AND EXISTS ("
        "   SELECT 1 FROM earnings_data ed"
        "   WHERE ed.stock_symbol = s.symbol"
        "     AND ed.eps_actual IS NOT NULL)",
        {"syms": symbols})
    stale += [r["symbol"] for r in blind]
    return list(dict.fromkeys(stale))[:_STALE_REFRESH_CAP]


def _fmp_window_map(days: int) -> dict:
    """FMP's whole-market earnings calendar for the window — one call.
    {symbol: iso date}; a symbol may appear once (nearest print)."""
    try:
        from app.providers.financial_modeling_prep.client import (
            FinancialModelingPrepClient)
        rows = FinancialModelingPrepClient.from_settings() \
            .get_earnings_calendar(
                from_date=date.today().isoformat(),
                to_date=(date.today()
                         + timedelta(days=days)).isoformat())
    except Exception as exc:
        logger.debug("fmp earnings window failed: %s", exc)
        return {}
    out = {}
    for r in rows or []:
        s, d = r.get("symbol"), str(r.get("date") or "")[:10]
        if s and d and (s not in out or d < out[s]):
            out[s] = d
    return out


# ------------------------------------------------------------------
# run
# ------------------------------------------------------------------

def run(days: int = 45) -> dict:
    from app.database import db
    from .calendar import upcoming_macro_events
    from .verify import verify_and_store
    from app.signals.earnings_calendar import refresh_earnings_calendar

    run_id = str(uuid.uuid4())
    today = date.today()
    res: dict[str, Any] = {"run_id": run_id, "as_of": str(today)}

    # ---- macro: verify, fingerprint, diff vs last week -------------
    res["verify"] = verify_and_store(days)
    evts = upcoming_macro_events(days)
    macro_now = [{"kind": e["kind"], "date": e["date"],
                  "name": e["name"]}
                 for e in evts if e.get("days_away", 0) >= -3]
    macro_prev = _last_snapshot("macro_snapshot") or []
    macro_changes = _diff_macro(macro_prev, macro_now)
    for ch in macro_changes:
        _journal(run_id, "macro", ch["change_type"],
                 old_date=ch["old_date"], new_date=ch["new_date"],
                 event_kind=ch["event_kind"],
                 detail={"name": ch["name"]})
    _snapshot(run_id, "macro_snapshot", macro_now)
    res["macro_changes"] = macro_changes

    # ---- earnings: fingerprint, diff, refresh suspects, x-check ----
    symbols = _tracked_symbols()
    cur = _next_earnings_map(symbols)
    prev = _last_snapshot("earnings_snapshot") or {}
    earn_changes = _diff_earnings(prev, cur)

    stale = _stale_candidates(symbols, cur)
    res["stale_refreshed"] = 0
    for s in stale:
        try:
            out = refresh_earnings_calendar(s)
        except Exception as exc:
            logger.debug("audit refresh %s failed: %s", s, exc)
            continue
        res["stale_refreshed"] += 1
        new = out.get("next_earnings_date")
        new = str(new)[:10] if new else None
        if new and new != cur.get(s):
            earn_changes.append(
                {"symbol": s, "change_type": "stale_fixed",
                 "old_date": cur.get(s), "new_date": new})
            cur[s] = new

    # cross-provider read-only check — disagreement is flagged, the
    # stored yahoo date stays authoritative until its own refresh moves
    fmp = _fmp_window_map(_EARNINGS_XCHECK_DAYS)
    res["fmp_window_rows"] = len(fmp)
    horizon = (today + timedelta(days=_EARNINGS_XCHECK_DAYS)).isoformat()
    for s in symbols:
        ours, theirs = cur.get(s), fmp.get(s)
        if ours and theirs and ours <= horizon and ours != theirs:
            earn_changes.append(
                {"symbol": s, "change_type": "provider_disagreement",
                 "old_date": ours, "new_date": theirs})
    for ch in earn_changes:
        _journal(run_id, "earnings", ch["change_type"],
                 old_date=ch["old_date"], new_date=ch["new_date"],
                 symbol=ch["symbol"])
    _snapshot(run_id, "earnings_snapshot", cur)
    res["earnings_changes"] = earn_changes

    # ---- digest ----------------------------------------------------
    n = len(macro_changes) + len(earn_changes)
    if n:
        parts = [f"{c['event_kind']} {c['change_type']}"
                 f" {c['old_date'] or '—'}→{c['new_date'] or '—'}"
                 for c in macro_changes[:6]]
        parts += [f"{c['symbol']} {c['change_type']}"
                  f" {c['old_date'] or '—'}→{c['new_date'] or '—'}"
                  for c in earn_changes[:6]]
        try:
            db.execute_update(
                "INSERT INTO alert_items (symbol, event_type,"
                " direction, materiality, title, detail, fingerprint,"
                " source, source_timestamp, status)"
                " VALUES ('MKT','calendar_audit','neutral','MEDIUM',"
                " :t, CAST(:d AS jsonb), :f, 'calendar_audit', now(),"
                " 'new') ON CONFLICT (fingerprint) DO NOTHING",
                {"t": f"Weekly calendar audit: {n} change(s) — "
                      + "; ".join(parts[:8]),
                 "d": json.dumps({"macro": macro_changes,
                                  "earnings": earn_changes},
                                 default=str),
                 "f": f"calendar-audit-{today}"})
        except Exception as exc:
            logger.debug("audit digest alert failed: %s", exc)

    res["changes"] = n
    logger.info("calendar audit %s: %d macro, %d earnings changes, "
                "%d stale refreshed", run_id[:8], len(macro_changes),
                len(earn_changes), res["stale_refreshed"])
    return res


def latest(limit: int = 200) -> dict:
    """Last audit run's change rows — what moved in the calendar."""
    from app.database import db
    try:
        runs = db.execute_query(
            "SELECT run_id, as_of, MIN(created_at) AS ran_at"
            " FROM calendar_audit WHERE change_type <> 'snapshot'"
            " GROUP BY run_id, as_of ORDER BY ran_at DESC LIMIT 1")
    except Exception:
        return {"changes": []}
    if not runs:
        return {"changes": []}
    rows = db.execute_query(
        "SELECT scope, event_kind, symbol, change_type, old_date,"
        " new_date, detail, created_at FROM calendar_audit"
        " WHERE run_id=:r ORDER BY scope, id",
        {"r": runs[0]["run_id"]})
    return {"run_id": runs[0]["run_id"],
            "as_of": str(runs[0]["as_of"]), "changes": rows}
