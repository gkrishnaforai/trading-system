"""earnings_watch — the earnings-day after-hours watcher.

The gap it closes: a tracked name reports at 16:05, the print lands
on the wire, but nobody re-evaluates it until the nightly chain —
or ever, if it's not in a job's universe. This polls every ~30 min
(scheduled externally, 16:00-20:00 ET) for active-tier names whose
`next_earnings_date` is today, and when the actuals land it:

  1. captures the print (eps est/actual, surprise %, rev est)
  2. runs earnings_release → the 8-K goes through doc_extract —
     verbatim claims, guidance → thesis_watches
  3. re-evaluates the thesis → status before vs after = the
     improving/deteriorating verdict
  4. journals earnings_watch + an alert_items alert carrying the
     analysis — one row per (symbol, print) so the poll is idempotent

Deterministic capture; the 8-K extraction layer is verbatim-grounded.
Advisory only.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _q(sql: str, p: Optional[dict] = None) -> list[dict]:
    from app.database import db
    return db.execute_query(sql, p or {})


def _u(sql: str, p: Optional[dict] = None) -> Any:
    from app.database import db
    return db.execute_update(sql, p or {})


def _et_today() -> date:
    """Earnings dates are US-market dates — after 20:00 ET the UTC
    date has already rolled to tomorrow, which is precisely when
    post-close prints matter. Always compare in ET."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York")).date()


# the book — names we hold or explicitly watch. Screener/theme
# memberships (rule_breaker, smallcap) are deliberately out: the
# watcher exists to review *our* prints, not the universe.
_TIER = ("(EXISTS (SELECT 1 FROM portfolio_positions pp"
         " WHERE pp.stock_id=s.id AND pp.quantity>0)"
         " OR EXISTS (SELECT 1 FROM watchlist_stocks ws"
         "            WHERE ws.stock_id=s.id))")


def todays_reporters() -> list[str]:
    """Book names (portfolio or watchlist) printing today, ET."""
    return [r["symbol"] for r in _q(
        "SELECT s.symbol FROM stocks s"
        " WHERE s.next_earnings_date ="
        " (now() AT TIME ZONE 'America/New_York')::date AND " + _TIER +
        " ORDER BY s.symbol")]


def due_reporters() -> list[tuple[str, date]]:
    """(symbol, print_day) pairs still owed a review: today's reporters
    plus any active-tier print from the last 2 days (ET) that was never
    captured. Actuals can land after the watch window — yfinance
    'Reported EPS' often arrives next morning — and by then
    next_earnings_date has rolled to the following quarter, so a
    today-only sweep would orphan the print permanently."""
    today = _et_today()
    pairs = {(s, today) for s in todays_reporters()}
    for r in _q(
            "SELECT ed.stock_symbol AS symbol, ed.earnings_date AS day"
            " FROM earnings_data ed JOIN stocks s"
            "   ON s.symbol = ed.stock_symbol"
            " WHERE ed.earnings_date BETWEEN :d2 AND :d0"
            "   AND NOT EXISTS (SELECT 1 FROM earnings_watch ew"
            "                   WHERE ew.symbol = ed.stock_symbol"
            "                   AND ew.earnings_date = ed.earnings_date)"
            "   AND " + _TIER,
            {"d0": today, "d2": today - timedelta(days=2)}):
        pairs.add((r["symbol"], r["day"]))
    return sorted(pairs, key=lambda p: (p[1], p[0]), reverse=True)


def _print(sym: str, day: date) -> Optional[dict]:
    """The day's earnings_data row once actuals (or estimates) exist."""
    rows = _q("SELECT stock_symbol, earnings_date, eps_estimate,"
              " eps_actual, revenue_estimate, surprise_percentage"
              " FROM earnings_data WHERE stock_symbol=:s"
              " AND earnings_date = :d",
              {"s": sym, "d": day})
    return dict(rows[0]) if rows else None


def _thesis_status(sym: str) -> Optional[str]:
    r = _q("SELECT status FROM symbol_thesis WHERE symbol=:s",
           {"s": sym})
    return r[0]["status"] if r else None


def _driver_deltas(sym: str) -> list[dict]:
    """Named-driver commitments captured from today's release — the
    'is the growth engine delivering' compare. A CUT on a named
    driver (NFLX ad revenue $3B→$2.7B) is a red flag the headline
    surprise can't see."""
    try:
        return [dict(r) for r in _q(
            "SELECT metric, period, value, prior_value, delta_dir,"
            " delta_pct, consensus_value, consensus_pct, value_text"
            " FROM driver_commitments"
            " WHERE symbol=:s AND (created_at AT TIME ZONE"
            " 'America/New_York')::date ="
            " (now() AT TIME ZONE 'America/New_York')::date"
            " AND status='open' ORDER BY ABS(delta_pct) DESC"
            " NULLS LAST LIMIT 8", {"s": sym})]
    except Exception:
        return []


def _verdict(before: Optional[str], after: Optional[str],
             surprise: Optional[float],
             drivers: Optional[list] = None,
             adj_surprise: Optional[float] = None) -> str:
    """improving/deteriorating from the thesis transition; surprise
    breaks ties. A named-driver guide CUT overrides the headline —
    the market repriced NFLX -6% on the ad-rev cut despite an EPS
    beat. A one-time-adjusted surprise can only upgrade the tie-break
    (a legal charge isn't business deterioration); the raw miss is
    still journaled. 'pending' when there's no basis yet."""
    rank = {"broken": 0, "deteriorating": 1, "unknown": 2,
            "improving": 3, "on_track": 4}
    cuts = [d for d in (drivers or []) if d.get("delta_dir") == "cut"]
    raises = [d for d in (drivers or []) if d.get("delta_dir") == "raised"]
    # a NEW commitment ≥5% below street behaves like a cut — guide
    # below consensus is the -6%-AH class of red flag (NFLX Q4 EPS)
    below = [d for d in (drivers or [])
             if d.get("delta_dir") not in ("cut", "raised")
             and d.get("consensus_pct") is not None
             and d["consensus_pct"] <= -0.05]
    above = [d for d in (drivers or [])
             if d.get("delta_dir") not in ("cut", "raised")
             and d.get("consensus_pct") is not None
             and d["consensus_pct"] >= 0.05]
    if before and after and before != after:
        v = ("improving" if rank.get(after, 2) > rank.get(before, 2)
             else "deteriorating")
    elif surprise is not None:
        eff = (max(surprise, adj_surprise)
               if adj_surprise is not None else surprise)
        v = ("improving" if eff >= 5 else
             "deteriorating" if eff <= -5 else "mixed")
    else:
        v = "pending"
    if cuts + below and not (raises or above):
        return "deteriorating"
    if cuts + below:
        return {"improving": "mixed", "on_track": "mixed"}.get(v, v)
    if (raises or above) and v in ("mixed", "pending"):
        return "improving"
    return v


def check_symbol(sym: str, day: Optional[date] = None) -> dict:
    """One symbol's earnings-day check for `day` (defaults to ET today).
    Idempotent — a journaled row for that print means the work already
    happened. `day` lets the sweep revisit prints whose actuals landed
    after the watch window closed."""
    from app.signals import earnings_calendar, earnings_release
    sym = sym.upper()
    today = day or _et_today()
    if _q("SELECT 1 FROM earnings_watch WHERE symbol=:s"
          " AND earnings_date=:d", {"s": sym, "d": today}):
        return {"symbol": sym, "status": "already_journaled"}

    before = _thesis_status(sym)
    # refetch the calendar — actuals land in earnings_data when the
    # print is out
    try:
        earnings_calendar.refresh_earnings_calendar(sym)
    except Exception as exc:
        logger.debug("earnings_watch refresh %s: %s", sym, exc)
    pr = _print(sym, today)
    if not pr or pr.get("eps_actual") is None:
        # print not out yet (or no actuals feed) — leave for next poll
        return {"symbol": sym, "status": "awaiting_print",
                "est": pr.get("eps_estimate") if pr else None}

    # the print landed — pull the 8-K through doc_extract (claims,
    # guidance → thesis_watches) then re-score the thesis
    ext = {}
    try:
        ext = earnings_release.run([sym], days=7)
    except Exception as exc:
        logger.debug("earnings_watch release %s: %s", sym, exc)
    after = before
    try:
        from app.signals import thesis_health
        after = thesis_health.evaluate(sym).get("status") or before
    except Exception as exc:
        logger.debug("earnings_watch thesis %s: %s", sym, exc)

    surp = pr.get("surprise_percentage")
    # one-time charge pass — legal/severance/impairment items buried
    # in the release can turn an adjusted beat into a reported miss;
    # annotate the row so the verdict isn't fooled (META Q2-26)
    adj = {}
    try:
        from app.signals import one_time
        adj = one_time.apply(sym, today)
    except Exception as exc:
        logger.debug("earnings_watch one_time %s: %s", sym, exc)
    adj_surp = adj.get("adjusted_surprise")
    drivers = _driver_deltas(sym)
    verdict = _verdict(before, after, surp, drivers, adj_surp)
    direction = ("UP" if verdict == "improving" else
                 "DOWN" if verdict == "deteriorating" else "NEUTRAL")
    detail = {
        "eps": {"est": _f(pr["eps_estimate"]),
                "act": _f(pr["eps_actual"])},
        "surprise_pct": _f(surp),
        "rev_est": _f(pr["revenue_estimate"]),
        "thesis": {"before": before, "after": after},
        "one_time": ({k: v for k, v in adj.items()
                      if k in ("items", "charges", "adjusted_eps",
                               "adjusted_surprise")} or None),
        "drivers": drivers,
        "release": {"analyzed": ext.get("analyzed"),
                    "claims": ext.get("claims")},
        "verdict": verdict}
    _u("INSERT INTO earnings_watch (symbol, earnings_date, session,"
       " eps_est, eps_actual, surprise_pct, rev_est, thesis_before,"
       " thesis_after, verdict, detail, alerted)"
       " VALUES (:s,:d,:se,:ee,:ea,:sp,:re,:tb,:ta,:v,"
       " CAST(:de AS jsonb),true)"
       " ON CONFLICT (symbol, earnings_date) DO UPDATE SET"
       " eps_actual=EXCLUDED.eps_actual,"
       " surprise_pct=EXCLUDED.surprise_pct,"
       " thesis_after=EXCLUDED.thesis_after,"
       " verdict=EXCLUDED.verdict, detail=EXCLUDED.detail,"
       " updated_at=now()",
       {"s": sym, "d": today, "se": "post",
        "ee": _f(pr["eps_estimate"]), "ea": _f(pr["eps_actual"]),
        "sp": _f(surp), "re": _f(pr["revenue_estimate"]),
        "tb": before, "ta": after, "v": verdict,
        "de": json.dumps(detail, default=str)})

    # the alert — carries the fundamentals verdict, not just the print
    in_book = bool(_q(
        "SELECT 1 FROM portfolio_positions pp JOIN stocks s"
        " ON s.id=pp.stock_id WHERE s.symbol=:s AND pp.quantity>0",
        {"s": sym}))
    in_wl = bool(_q(
        "SELECT 1 FROM watchlist_stocks ws JOIN stocks s"
        " ON s.id=ws.stock_id WHERE s.symbol=:s", {"s": sym}))
    beat = ("beat" if (surp or 0) > 0 else
            "miss" if (surp or 0) < 0 else "in-line")
    _u("INSERT INTO alert_items (symbol, event_type, direction,"
       " materiality, title, detail, fingerprint, source,"
       " source_timestamp, in_portfolio, in_watchlist, status,"
       " priority_score)"
       " VALUES (:s,'earnings',:di,:mat,:t,CAST(:de AS jsonb),:fp,"
       " 'earnings_watch',"
       " now(),:ib,:iw,'new',:pr)",
       {"s": sym, "di": direction,
        "mat": "HIGH" if abs(surp or 0) >= 5 else "MEDIUM",
        "t": (f"{sym} earnings: EPS {beat} "
              f"{surp:+.1f}%"
              + (f" (adj {adj_surp:+.1f}% ex-one-time)"
                 if adj_surp is not None
                 and abs((adj_surp or 0) - (surp or 0)) >= 2
                 else "")
              + f" — fundamentals {verdict}"
              + (f" (thesis {before or 'new'}→{after})"
                 if before != after else "")
              + "".join(
                  f" — {d['metric']} {d['period']} guide "
                  f"{d['delta_dir']}"
                  for d in drivers
                  if d.get("delta_dir") in ("cut", "raised"))[:120]),
        "de": json.dumps(detail, default=str),
        "fp": f"earnings_watch:{sym}:{today}",
        "ib": in_book, "iw": in_wl,
        "pr": 150 if in_book else 120})

    # post-print input refresh — the print just landed, so the stored
    # fundamentals snapshot is now pre-print. Refetch it (fresh
    # eps_forward + estimates + TTM actuals) and re-resolve FV.
    fv = {}
    try:
        from app.signals import fv_sweep
        fv = fv_sweep.refresh_after_print(sym)
    except Exception as exc:
        logger.debug("earnings_watch fv refresh %s: %s", sym, exc)

    # post-print review — journal a fresh 5-question review so the
    # stock-page watch section reflects the print (new thesis status,
    # refreshed FV), not the last weekly/alert row. Calls review()
    # directly: maybe_review's 20h dedupe would drop it whenever a
    # same-day review already ran, but the quarterly print is always
    # new material evidence worth journaling.
    rev = {}
    try:
        from app.signals import event_review
        rev = event_review.review(sym, trigger="earnings") or {}
    except Exception as exc:
        logger.debug("earnings_watch review %s: %s", sym, exc)
    return {"symbol": sym, "status": "journaled",
            "verdict": verdict, "surprise_pct": _f(surp),
            "thesis": {"before": before, "after": after},
            "review_verdict": rev.get("verdict"),
            "fv": {k: v for k, v in fv.items() if k != "symbol"}}


def _f(x) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except Exception:
        return None


def poll() -> dict:
    """The 30-min sweep — every active-tier name printing today that
    isn't journaled yet. Safe to run any time; symbols whose print
    hasn't landed return 'awaiting_print' and get retried next poll."""
    reporters = due_reporters()
    out, errs = [], []
    for sym, day in reporters:
        try:
            res = check_symbol(sym, day)
            if res["status"] == "journaled":
                out.append(res)
        except Exception as exc:
            errs.append(f"{sym}: {exc}")
            if len(errs) >= 10:
                break
    return {"reporters": len(reporters), "captured": out,
            "errors": errs}


def latest(days: int = 7) -> list[dict]:
    """Recent earnings-watch captures — the alert surface."""
    rows = _q("SELECT symbol, earnings_date, session, eps_est,"
              " eps_actual, surprise_pct, rev_est, thesis_before,"
              " thesis_after, verdict, detail, created_at"
              " FROM earnings_watch"
              " WHERE earnings_date >= CURRENT_DATE - :d"
              " ORDER BY earnings_date DESC, symbol", {"d": days})
    out = []
    for r in rows:
        row = dict(r)
        row["earnings_date"] = str(row["earnings_date"])
        row["created_at"] = str(row["created_at"])[:19]
        d = row.get("detail")
        row["detail"] = json.loads(d) if isinstance(d, str) else d
        out.append(row)
    return out
