"""Earnings completion reconciler — nightly ~23:00 ET backstop.

earnings_watch captures the print fast (same evening); the SLOW
artifacts legitimately lag — the 10-Q carrying XBRL facts can land
days to ~45 days after the print. This job tracks, per
(symbol, earnings_date), what is journaled vs still owed:

  print      earnings_data has actuals
  verdict    earnings_watch verdict resolved (not pending)
  release8k  the 8-K press release was processed (sec_filings_processed)
  filing     a 10-Q/10-K covering the period exists on EDGAR
  xbrl       symbol_sec_facts refreshed to the reported period
  quarterly  fundamental_quarterly has the reported period row
  report     earnings_reports generated for the print
  drivers    driver commitments captured from the release

Each night it re-checks the trailing window, runs the owning fill
path for what's missing (same functions the primary jobs use —
nothing reimplemented), journals the checklist, and on ANY fill
re-runs the fundamentals chain so late data refreshes the evals that
consumed stale inputs. A 10-Q/10-K landing journals an alert. At
45d the row expires with `missing` journaled — owed artifacts stay
null, never fabricated.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_WINDOW = 45               # days after the print we keep reconciling
_PERIOD_LO = 90            # fiscal period_end ∈ [day−90, day−5]
_PERIOD_HI = 5


def _q(sql: str, p: Optional[dict] = None) -> list[dict]:
    from app.database import db
    return db.execute_query(sql, p or {})


def _u(sql: str, p: Optional[dict] = None) -> Any:
    from app.database import db
    return db.execute_update(sql, p or {})


def _et_today() -> date:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York")).date()


def _reporters(days: int = _WINDOW) -> list[dict]:
    """(symbol, earnings_date) pairs for book names inside the
    reconcile window — from earnings_watch ∪ earnings_data ∪
    stocks.next_earnings_date history."""
    today = _et_today()
    return _q(
        "SELECT DISTINCT symbol, earnings_date FROM ("
        " SELECT symbol, earnings_date FROM earnings_watch"
        "  WHERE earnings_date BETWEEN :d0 AND :d1"
        " UNION SELECT stock_symbol, earnings_date FROM earnings_data"
        "  WHERE earnings_date BETWEEN :d0 AND :d1"
        "   AND stock_symbol IN (SELECT symbol FROM book_symbols)"
        ") x ORDER BY earnings_date DESC, symbol",
        {"d0": today - timedelta(days=days), "d1": today})


def _checks(sym: str, day: date) -> dict[str, str]:
    """The completion checklist — each 'done' is a journaled fact the
    engine itself can see; 'pending' means still owed."""
    c: dict[str, str] = {}
    r = _q("SELECT eps_actual, surprise_percentage FROM earnings_data"
           " WHERE stock_symbol=:s AND earnings_date=:d",
           {"s": sym, "d": day})
    c["print"] = ("done" if r and (r[0].get("eps_actual") is not None
                                   or r[0].get("surprise_percentage")
                                   is not None) else "pending")
    r = _q("SELECT verdict FROM earnings_watch"
           " WHERE symbol=:s AND earnings_date=:d",
           {"s": sym, "d": day})
    c["verdict"] = ("done" if r and r[0].get("verdict")
                    not in (None, "pending") else "pending")
    c["release8k"] = ("done" if _q(
        "SELECT 1 FROM sec_filings_processed WHERE symbol=:s"
        " AND filed BETWEEN :d0 AND :d1 LIMIT 1",
        {"s": sym, "d0": day - timedelta(days=2),
         "d1": day + timedelta(days=6)}) else "pending")
    c["xbrl"] = ("done" if _q(
        "SELECT 1 FROM symbol_sec_facts WHERE symbol=:s"
        " AND as_of BETWEEN :d0 AND :d1 LIMIT 1",
        {"s": sym, "d0": day - timedelta(days=_PERIOD_LO),
         "d1": _et_today()}) else "pending")
    c["quarterly"] = ("done" if _q(
        "SELECT 1 FROM fundamental_quarterly WHERE symbol=:s"
        " AND period_end BETWEEN :d0 AND :d1 LIMIT 1",
        {"s": sym, "d0": day - timedelta(days=_PERIOD_LO),
         "d1": day - timedelta(days=_PERIOD_HI)}) else "pending")
    c["report"] = ("done" if _q(
        "SELECT 1 FROM earnings_reports WHERE symbol=:s"
        " AND earnings_date=:d LIMIT 1",
        {"s": sym, "d": day}) else "pending")
    c["drivers"] = ("done" if _q(
        "SELECT 1 FROM driver_commitments WHERE symbol=:s"
        " AND created_at::date BETWEEN :d0 AND :d1 LIMIT 1",
        {"s": sym, "d0": day - timedelta(days=1),
         "d1": day + timedelta(days=7)}) else "pending")
    return c


def _alert_filing(sym: str, form: str, accession: Optional[str],
                  period_end: Optional[str]) -> None:
    """10-Q/10-K landed → alert. Fingerprinted on accession so the
    same filing alerts once across nights."""
    flags = _q(
        "SELECT EXISTS(SELECT 1 FROM portfolio_positions pp"
        " JOIN stocks s ON s.id=pp.stock_id"
        " WHERE s.symbol=:s AND pp.quantity>0) AS ip,"
        " EXISTS(SELECT 1 FROM watchlist_stocks ws"
        " JOIN stocks s ON s.id=ws.stock_id"
        " WHERE s.symbol=:s) AS iw", {"s": sym})
    fp = f"sec_filing:{accession or form + ':' + sym}"
    if _q("SELECT 1 FROM alert_items WHERE fingerprint=:f", {"f": fp}):
        return
    _u("INSERT INTO alert_items (symbol, event_type, direction,"
       " materiality, title, detail, fingerprint, source,"
       " source_timestamp, in_portfolio, in_watchlist, status,"
       " priority_score)"
       " VALUES (:s,'sec_filing','neutral',:mat,:t,"
       " CAST(:de AS jsonb),:fp,'earnings_completion',now(),"
       " :ib,:iw,'new',40)",
       {"s": sym, "mat": "HIGH" if form == "10-K" else "MEDIUM",
        "t": f"{sym} {form} filed — XBRL facts available for refresh",
        "de": json.dumps({"form": form, "accession": accession,
                          "period_end": period_end}),
        "fp": fp,
        "ib": bool(flags and flags[0].get("ip")),
        "iw": bool(flags and flags[0].get("iw"))})


def _reanalyze(sym: str) -> list[str]:
    """New data landed → re-run the fundamentals chain for this one
    symbol so evals consume fresh inputs tonight, not stale ones."""
    done: list[str] = []
    for name, fn in (
        ("fundamental_health", lambda: _call(
            "app.signals.fundamental_health", "refresh_all", [sym])),
        ("earnings_quality", lambda: _call(
            "app.signals.earnings_quality", "run", [sym])),
        ("event_review", lambda: _call(
            "app.signals.event_review", "run_universe", [sym])),
    ):
        try:
            fn()
            done.append(name)
        except Exception as exc:                       # noqa: BLE001
            logger.info("completion reanalyze %s %s: %s",
                        name, sym, exc)
    return done


def _call(mod: str, fn: str, *a):
    m = __import__(mod, fromlist=[fn])
    return getattr(m, fn)(*a)


def _fill(sym: str, day: date, checks: dict,
          filings: list[dict], fmp) -> tuple[list, list, dict]:
    """Run the owning fill path per pending check. Returns
    (filled, reanalyzed, updated_checks)."""
    filled: list = []
    reanalyzed: list = []
    changed = False

    if checks["release8k"] == "pending":
        try:
            from app.signals import earnings_release
            earnings_release.run([sym], days=10)
            checks["release8k"] = "done"
            filled.append("release8k")
            changed = True
        except Exception as exc:                       # noqa: BLE001
            logger.info("completion 8k fill %s: %s", sym, exc)

    # filing detection — the caller passes only filings covering the
    # period; alert fires on every sighting (accession fingerprint
    # dedupes to once)
    new_filing = filings[0] if filings else None
    if new_filing:
        _alert_filing(sym, new_filing["form"],
                      new_filing.get("accession"), new_filing.get("period_end"))
        if checks.get("filing") == "pending":
            checks["filing"] = "done"
            filled.append("filing")

    if checks["xbrl"] == "pending" and checks["filing"] == "done":
        try:
            from app.signals import sec_fundamentals
            f = sec_fundamentals.extract(sym)
            if f:
                sec_fundamentals.persist(sym, f)
                checks["xbrl"] = "done"
                filled.append("xbrl")
                changed = True
        except Exception as exc:                       # noqa: BLE001
            logger.info("completion xbrl fill %s: %s", sym, exc)

    if checks["quarterly"] == "pending" and fmp is not None:
        try:
            from app.signals import fundamental_journal
            if fundamental_journal.journal_symbol(fmp, sym):
                checks["quarterly"] = "done"
                filled.append("quarterly")
                changed = True
        except Exception as exc:                       # noqa: BLE001
            logger.info("completion quarterly fill %s: %s", sym, exc)

    if checks["report"] == "pending":
        try:
            from app.signals import earnings_report
            if earnings_report.build(sym, day):
                checks["report"] = "done"
                filled.append("report")
        except Exception as exc:                       # noqa: BLE001
            logger.info("completion report fill %s: %s", sym, exc)

    if changed:
        reanalyzed = _reanalyze(sym)
    return filled, reanalyzed, checks


def run(symbols: Optional[list[str]] = None) -> dict[str, Any]:
    """Nightly reconcile — every tracked print in the window gets its
    checklist refreshed; pending artifacts get a fill attempt."""
    from app.providers import sec_edgar
    today = _et_today()
    reps = _reporters()
    if symbols:
        reps = [r for r in reps if r["symbol"] in set(symbols)]
    fmp = None
    try:
        from app.providers.financial_modeling_prep.client import \
            EnhancedFMPClient
        fmp = EnhancedFMPClient.from_settings()
    except Exception:
        logger.info("completion: no FMP client — quarterly fills off")

    stats = {"checked": 0, "complete": 0, "tracking": 0, "expired": 0,
             "filled": 0}
    filings_cache: dict[str, list[dict]] = {}
    for rep in reps:
        sym, day = rep["symbol"], rep["earnings_date"]
        try:
            checks = _checks(sym, day)
            if sym not in filings_cache:
                filings_cache[sym] = sec_edgar.recent_filings(
                    sym, ("10-Q", "10-K"), days=_WINDOW + 10)
            filings = filings_cache[sym]
            covering = [f for f in filings
                        if f.get("period_end")
                        and day - timedelta(days=_PERIOD_LO)
                        <= date.fromisoformat(f["period_end"]) <= day]
            checks.setdefault("filing", "pending")
            filled, reanalyzed, checks = _fill(
                sym, day, checks, covering, fmp)
            missing = [k for k, v in checks.items() if v == "pending"]
            age = (today - day).days
            status = ("complete" if not missing
                      else "expired" if age > _WINDOW else "tracking")
            prior = _q("SELECT filled, reanalyzed FROM"
                       " earnings_completion WHERE symbol=:s"
                       " AND earnings_date=:d", {"s": sym, "d": day})
            acc_filled = list(dict.fromkeys(
                ((prior[0].get("filled") or [])
                 if prior else []) + filled))
            acc_rean = list(dict.fromkeys(
                ((prior[0].get("reanalyzed") or [])
                 if prior else []) + reanalyzed))
            _u("INSERT INTO earnings_completion (symbol, earnings_date,"
               " checks, missing, filled, reanalyzed, status,"
               " last_checked, updated_at)"
               " VALUES (:s,:d,CAST(:c AS jsonb),CAST(:m AS jsonb),"
               " CAST(:f AS jsonb),CAST(:r AS jsonb),:st,now(),now())"
               " ON CONFLICT (symbol, earnings_date) DO UPDATE SET"
               " checks=EXCLUDED.checks, missing=EXCLUDED.missing,"
               " filled=EXCLUDED.filled,"
               " reanalyzed=EXCLUDED.reanalyzed,"
               " status=EXCLUDED.status, last_checked=now(),"
               " updated_at=now()",
               {"s": sym, "d": day, "c": json.dumps(checks),
                "m": json.dumps(missing), "f": json.dumps(acc_filled),
                "r": json.dumps(acc_rean), "st": status})
            stats["checked"] += 1
            stats[status] += 1
            stats["filled"] += len(filled)
        except Exception as exc:                       # noqa: BLE001
            logger.warning("completion %s %s failed: %s",
                           sym, day, exc)
    return stats


def for_symbol(sym: str, days: int = _WINDOW) -> dict[str, Any]:
    """The stock-page view — latest checklist rows for one symbol."""
    rows = _q(
        "SELECT symbol, earnings_date, checks, missing, filled,"
        " reanalyzed, status, last_checked FROM earnings_completion"
        " WHERE symbol=:s AND earnings_date >= :d0"
        " ORDER BY earnings_date DESC LIMIT 6",
        {"s": sym.upper(), "d0": _et_today() - timedelta(days=days)})
    return {"symbol": sym.upper(), "rows": rows}
