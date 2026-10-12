"""Expectation-gap / earnings-flywheel layer — the canonical "is the
business outrunning Wall Street's model?" signal.

Every engine (rule breakers, 5x scout, LEAPS) joins symbol_flywheel
instead of re-deriving these metrics. The composite gap_score(0-100):

  acceleration  (35): rev_accel>0 +15 · eps_accel>0 +10 · gm_slope>0 +10
  beats         (20): streak≥3 +15 / ≥2 +10 · avg surprise >5% +5
  revisions     (15): fwd EPS estimate rising vs ~90d snapshot
  coverage      (10): <12 analysts +10 · <25 +5 — under-covered = room
  muted reaction(10): last print beat >5% and stock moved <3%
  valuation     (10): fwd P/E <40 partial, <25 full

The framework: business inflects → estimates catch up → valuation
catches up → rerating. We want to sit between steps one and two.

Sources: FMP income-statement (acceleration) + analyst-estimates
(forward EPS/rev, coverage) · yfinance earnings_dates (surprise
history) · OHLCV for the muted-reaction check.
"""
from __future__ import annotations

import asyncio
import logging
import math
import pandas as pd
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

REVISION_LOOKBACK_DAYS = 90      # compare estimates vs ~90d-ago snapshot
SNAPSHOT_MIN_GAP_DAYS = 14       # don't append near-duplicate snapshots


def _div(a, b):
    return a / b if a is not None and b else None


def _fundamental_accel(fmp, sym: str) -> dict:
    """8 quarters of income statements → rev/eps YoY acceleration and
    gross-margin slope."""
    inc = fmp._make_request(
        "/income-statement",
        {"symbol": sym, "period": "quarter", "limit": 8}) or []
    if len(inc) < 6:
        return {}
    rev = [q.get("revenue") for q in inc]
    eps = [q.get("eps") or q.get("epsDiluted") for q in inc]
    gm = [(_div(q.get("grossProfit"), q.get("revenue")))
          for q in inc]
    rev_yoy = [(_div(rev[i], rev[i + 4])) - 1 if rev[i] and rev[i + 4]
               else None for i in range(4)]
    # growth % only meaningful when both periods share a sign and the
    # base isn't dust — cur<0 on a tiny positive prior yields -387% of
    # nothing; a flip to losses is a regime flag, not a growth rate
    eps_yoy = [(_div(eps[i], eps[i + 4])) - 1
               if eps[i] is not None and eps[i + 4] is not None
               and eps[i + 4] >= 0.25 and eps[i] > -0.5
               else None for i in range(4)]
    # TTM EPS YoY — the smoothed level view. Single quarters are lumpy
    # (tax timing, SBC, acquisition amortization): NOW printed -22% on a
    # quarterly compare while TTM EPS was flat. Level-deterioration
    # judgments run on this; quarterly eps_yoy stays as momentum detail.
    eps_ttm_growth = None
    if len(eps) >= 8 and all(v is not None for v in eps[:8]):
        ttm_now, ttm_prev = sum(eps[:4]), sum(eps[4:8])
        if ttm_prev >= 0.10 and ttm_now > -0.5:
            eps_ttm_growth = (ttm_now / ttm_prev) - 1
    def _accel(cur, prev):
        # a diff off a ~zero-base YoY level is base-effect noise, not
        # trajectory — CIEN: EPS +437% YoY "decelerated" −1911pts
        # because the prior quarter was +2350% off ~zero EPS
        if cur is None or prev is None:
            return None
        # level-relative FIRST: triple-digit growth stepping down is
        # normalization, not deterioration — NBIS +621%→+454% isn't
        # "slowing". Return 0 (not None) so it overwrites stored junk.
        if cur > 1.0 and cur < prev:
            return 0.0
        # then the base-effect guard — a diff off a ~zero-base YoY
        # level is arithmetic noise (CIEN +437% vs prior +2350%).
        # Return 0 (not None): None survives via upsert COALESCE and
        # resurrects the stale stored diff — PLTR carried a -81pt eps
        # "decel" artifact into the classifier this way
        if abs(prev) > 2.0:
            return 0.0
        return cur - prev

    # capex efficiency — for buildout-phase AI names the question is
    # whether each $1 of capex produces new gross profit, not whether
    # FCF is positive yet (it won't be, by design)
    rev_ttm = sum(x for x in rev[:4] if x) or None
    gp_delta = (inc[0].get("grossProfit") - inc[4].get("grossProfit")
                ) * 4 if (inc[0].get("grossProfit") is not None
                          and inc[4].get("grossProfit") is not None) else None
    capex_ttm = None
    try:
        # the -ttm endpoint is empty on this plan — sum quarters instead
        cf = fmp.get_cash_flow_statement(sym, "quarter") or []
        cx = [abs(float(q["capitalExpenditure"])) for q in cf[:4]
              if q.get("capitalExpenditure") is not None]
        capex_ttm = sum(cx) if len(cx) >= 3 else None
    except Exception:
        pass

    return {
        "rev_growth": rev_yoy[0],
        "rev_accel": _accel(rev_yoy[0], rev_yoy[1]),
        "gm_now": gm[0],
        "gm_slope": (gm[0] - gm[4] if gm[0] is not None
                     and gm[4] is not None else None),
        # sequential delta — the "temporary compression vs structural
        # breakdown" discriminator (QoQ down / YoY up + capex-heavy =
        # capacity-cycle margin pressure, not demand loss)
        "gm_qoq": (gm[0] - gm[1] if gm[0] is not None
                   and gm[1] is not None else None),
        "eps_growth": eps_yoy[0],
        "eps_accel": _accel(eps_yoy[0], eps_yoy[1]),
        "eps_growth_ttm": eps_ttm_growth,
        "capex_eff": (_div(gp_delta, capex_ttm)
                      if gp_delta is not None else None),
        "capex_rev": (_div(capex_ttm, rev_ttm)
                      if capex_ttm and rev_ttm else None),
    }


def _balance_health(fmp, sym: str) -> dict:
    """Balance-sheet + business-quality legs. net_debt_ebitda catches
    'great business, dangerous capital structure' (TLN ~11.8x on
    restructuring-inflated denominators); ROIC/ROE live only on the
    ANNUAL key-metrics feed on this plan."""
    out: dict = {}
    km = fmp.get_key_metrics_ttm(sym) or []
    if km:
        out["net_debt_ebitda"] = km[0].get("netDebtToEBITDATTM")
        out["debt_to_equity"] = km[0].get("debtToEquityTTM")
    try:
        ka = fmp.get_key_metrics(sym) or []
    except Exception:
        ka = []
    if ka:
        out["roic"] = ka[0].get("returnOnInvestedCapital")
        out["roe"] = ka[0].get("returnOnEquity")
    return out


def _surprises(sym: str) -> dict:
    """yfinance earnings_dates → beat streak, avg/last surprise,
    last report date."""
    import yfinance as yf
    ed = yf.Ticker(sym).earnings_dates
    if ed is None or ed.empty:
        return {}
    past = ed[ed["Reported EPS"].notna()].copy()
    if past.empty:
        return {}
    past = past.sort_index(ascending=False)
    surprises = [float(v) for v in past["Surprise(%)"].tolist()
                 if pd.notna(v)][:4]
    streak = 0
    for v in surprises:
        if v > 0:
            streak += 1
        else:
            break
    last_date = past.index[0].date() if len(past.index) else None
    trend = (surprises[0] - surprises[-1]
             if len(surprises) >= 3 else None)   # newest - oldest
    return {"beat_streak": streak,
            "surprise_trend": trend,
            "avg_surprise_pct": (sum(surprises) / len(surprises)
                                 if surprises else None),
            "last_surprise_pct": surprises[0] if surprises else None,
            "last_report_date": str(last_date) if last_date else None}


def _estimates(fmp, sym: str) -> dict:
    """Forward estimates + analyst coverage from FMP, plus revision
    drift vs our own ~90d-ago snapshot (snapshots accumulate in
    symbol_estimate_snapshots — that's how the revision signal gets
    built over time)."""
    from app.database import db
    est = fmp._make_request(
        "/analyst-estimates",
        {"symbol": sym, "period": "annual", "limit": 6}) or []
    today = date.today()
    fwd = next((e for e in est
                if e.get("date") and str(e["date"])[:10] >
                str(today + timedelta(days=60))), None)
    if not fwd:
        return {}
    period_end = str(fwd["date"])[:10]
    eps_avg = fwd.get("epsAvg")
    rev_avg = fwd.get("revenueAvg")
    analysts = fwd.get("numAnalystsEps") or fwd.get("numAnalystsRevenue")

    # snapshot the FULL annual estimate curve (every forward period),
    # not just the nearest — the long-dated rows are what the
    # long-duration repricing lens (lt_power) reads. Each period_end
    # accumulates its own as_of time-series for revision deltas.
    revision_pct = None
    try:
        _ensure_stock(sym)
        for e in est:
            d = e.get("date")
            if not d or str(d)[:10] <= str(today + timedelta(days=60)):
                continue
            pe = str(d)[:10]
            recent = db.execute_query(
                "SELECT 1 FROM symbol_estimate_snapshots WHERE symbol=:s "
                "AND period_end=:p AND as_of > :cut LIMIT 1",
                {"s": sym, "p": pe,
                 "cut": today - timedelta(days=SNAPSHOT_MIN_GAP_DAYS)})
            if recent:
                continue
            db.execute_query(
                "INSERT INTO symbol_estimate_snapshots "
                "(symbol, period_end, eps_avg, eps_low, eps_high, "
                "rev_avg, num_analysts) "
                "VALUES (:s, :p, :e, :el, :eh, :r, :a) "
                "ON CONFLICT (symbol, period_end, as_of) DO NOTHING",
                {"s": sym, "p": pe, "e": e.get("epsAvg"),
                 "el": e.get("epsLow"), "eh": e.get("epsHigh"),
                 "r": e.get("revenueAvg"),
                 "a": e.get("numAnalystsEps") or e.get("numAnalystsRevenue")})
        prev = db.execute_query(
            "SELECT eps_avg, as_of FROM symbol_estimate_snapshots "
            "WHERE symbol=:s AND period_end=:p "
            "AND as_of <= :cut ORDER BY as_of DESC LIMIT 1",
            {"s": sym, "p": period_end,
             "cut": today - timedelta(days=REVISION_LOOKBACK_DAYS)})
        if prev and eps_avg is not None and prev[0].get("eps_avg"):
            p = prev[0]["eps_avg"]
            # % revision is only meaningful on a sane base — near-zero
            # or sign-flipping estimates (IREN 0.07→1.33 = +1891%)
            # produce noise, not signal
            if abs(p) >= 0.25 and (p > 0) == (eps_avg > 0):
                revision_pct = eps_avg / p - 1
    except Exception as exc:
        logger.debug("est snapshot %s failed: %s", sym, exc)

    # yfinance carries the actual revision history — eps_trend has the
    # +1y estimate as of 7/30/60/90 days ago, eps_revisions has the
    # up/down breadth. This fills the revision signal TODAY; our own
    # snapshots only become the source once they've aged past 90d.
    breadth = None
    try:
        import yfinance as yf
        tk = yf.Ticker(sym)
        trend = tk.eps_trend
        if trend is not None and not trend.empty \
                and "+1y" in trend.index:
            cur = trend.loc["+1y", "current"]
            ago = trend.loc["+1y", "90daysAgo"]
            # same base sanity as the snapshot path — near-zero or
            # sign-flipping priors make % revision pure noise
            if (pd.notna(cur) and pd.notna(ago)
                    and abs(float(ago)) >= 0.25
                    and (ago > 0) == (cur > 0)):
                revision_pct = float(cur / ago - 1)
            if not eps_avg and pd.notna(cur):
                eps_avg = float(cur)
        ee = tk.earnings_estimate
        if ee is not None and not ee.empty and "+1y" in ee.index:
            n = ee.loc["+1y", "numberOfAnalysts"]
            if pd.notna(n) and int(n) > (analysts or 0):
                analysts = int(n)
        rv = tk.eps_revisions
        if rv is not None and not rv.empty and "+1y" in rv.index:
            up = rv.loc["+1y", "upLast30days"]
            dn = rv.loc["+1y", "downLast30days"]
            if pd.notna(up) and pd.notna(dn):
                breadth = int(up) - int(dn)
    except Exception as exc:
        logger.debug("yf estimates %s failed: %s", sym, exc)

    return {"fwd_eps_avg": eps_avg, "fwd_rev_avg": rev_avg,
            "num_analysts": analysts, "est_revision_pct": revision_pct,
            "rev_breadth_30d": breadth}


def _muted_reaction(sym: str, last_report: Optional[str],
                    last_surprise: Optional[float],
                    bars=None) -> Optional[bool]:
    """Beat >5% but the stock moved <3% over the print window → the
    market hasn't repriced the new earnings power. Needs daily bars
    spanning the report date; returns None when unknown."""
    if last_surprise is None or not last_report:
        return None
    if last_surprise <= 5:
        return False            # wasn't a meaningful beat
    if not bars:
        return None             # can't measure the reaction
    rep = date.fromisoformat(str(last_report))
    window = [b for b in bars
              if rep - timedelta(days=1) <= b.date <= rep
              + timedelta(days=2)]
    if len(window) < 2:
        return None
    first, last = window[0], window[-1]
    move = (last.close / first.open - 1) * 100 if first.open else 0
    return move < 3.0


def _score(m: dict) -> tuple[float, dict]:
    det: dict[str, Any] = {}
    s = 0.0
    # acceleration (35)
    a = 0.0
    if (m.get("rev_accel") or 0) > 0:
        a += 15
    if (m.get("eps_accel") or 0) > 0:
        a += 10
    if (m.get("gm_slope") or 0) > 0:
        a += 10
    det["acceleration"] = a
    s += a
    # beats (20)
    streak = m.get("beat_streak") or 0
    b = (15 if streak >= 3 else 10 if streak >= 2 else
         5 if streak >= 1 else 0)
    if (m.get("avg_surprise_pct") or 0) > 5:
        b += 5
    det["beats"] = b
    s += b
    # revisions (15)
    rev_pct = m.get("est_revision_pct")
    r = (15 if rev_pct and rev_pct > 0.10 else
         10 if rev_pct and rev_pct > 0.03 else
         5 if rev_pct and rev_pct > 0 else 0)
    det["revisions"] = r
    det["rev_breadth_30d"] = m.get("rev_breadth_30d")
    s += r
    # coverage (10) — under-covered = estimates can still move a lot
    n = m.get("num_analysts")
    c = 10 if n is not None and n < 12 else (5 if n is not None
                                             and n < 25 else 0)
    det["coverage"] = c
    s += c
    # muted reaction (10)
    mu = 10 if m.get("muted_reaction") else 0
    det["muted_reaction"] = mu
    s += mu
    # valuation sanity (10)
    fpe = m.get("fwd_pe")
    v = (10 if fpe and fpe < 25 else 5 if fpe and fpe < 40 else 0)
    det["valuation"] = v
    s += v
    return round(s, 1), det


def _ensure_stock(sym: str) -> None:
    """FK target — vivify a minimal stocks row for symbols discovered
    by engines before the ingestion pipeline registers them."""
    from app.database import db
    db.execute_query(
        "INSERT INTO stocks (symbol) VALUES (:s) "
        "ON CONFLICT (symbol) DO NOTHING", {"s": sym})


def compute_flywheel(fmp, sym: str, price: Optional[float] = None,
                     bars=None) -> dict:
    """Compute + persist the flywheel row for one symbol."""
    from app.database import db
    sym = sym.upper().strip()
    try:
        _ensure_stock(sym)
    except Exception as exc:
        logger.debug("stock vivify %s: %s", sym, exc)
    m: dict[str, Any] = {"symbol": sym}
    try:
        m.update(_fundamental_accel(fmp, sym))
    except Exception as exc:
        logger.debug("flywheel accel %s: %s", sym, exc)
    try:
        m.update(_surprises(sym))
    except Exception as exc:
        logger.debug("flywheel surprises %s: %s", sym, exc)
    try:
        m.update(_estimates(fmp, sym))
    except Exception as exc:
        logger.debug("flywheel estimates %s: %s", sym, exc)
    try:
        m.update(_balance_health(fmp, sym))
    except Exception as exc:
        logger.debug("flywheel leverage %s: %s", sym, exc)
    if price is None:
        try:
            q = fmp._make_request("/quote", {"symbol": sym}) or []
            price = q[0].get("price") if q else None
        except Exception:
            price = None
    if price:
        m["fwd_pe"] = (_div(price, m["fwd_eps_avg"])
                       if m.get("fwd_eps_avg") else None)
    if bars is None and m.get("last_report_date"):
        try:
            import yfinance as yf
            rep = date.fromisoformat(str(m["last_report_date"]))
            hist = yf.Ticker(sym).history(
                start=rep - timedelta(days=5),
                end=rep + timedelta(days=4))
            bars = [
                type("B", (), {"date": i.date(), "open": float(r.Open),
                               "close": float(r.Close)})
                for i, r in hist.iterrows()] if not hist.empty else None
        except Exception:
            bars = None
    try:
        m["muted_reaction"] = _muted_reaction(
            sym, m.get("last_report_date"), m.get("last_surprise_pct"),
            bars)
    except Exception as exc:
        logger.debug("flywheel reaction %s: %s", sym, exc)

    score, det = _score(m)
    # provider outage guard — a total miss must not wipe last-known-good
    _CORE = ("rev_growth", "gm_now", "eps_growth", "beat_streak",
             "fwd_eps_avg", "num_analysts", "last_report_date")
    _fresh = any(m.get(k) is not None for k in _CORE)
    try:
        if not _fresh:
            raise RuntimeError("no flywheel fields computed — skip write")
        db.execute_query(
            "INSERT INTO symbol_flywheel "
            "(symbol, rev_growth, rev_accel, gm_now, gm_slope, gm_qoq, "
            " eps_growth, eps_accel, beat_streak, avg_surprise_pct, "
            " last_surprise_pct, last_report_date, fwd_eps_avg, "
            " fwd_rev_avg, num_analysts, est_revision_pct, fwd_pe, "
            " muted_reaction, gap_score, gap_detail, "
            " net_debt_ebitda, debt_to_equity, rev_breadth_30d,"
            " surprise_trend, roic, roe, capex_eff, capex_rev,"
            " eps_growth_ttm) "
            "VALUES (:s,:rg,:ra,:gm,:gms,:gmq,:eg,:ea,:bs,:asp,:lsp,:lrd,"
            ":fe,:fr,:na,:er,:fpe,:mr,:gs,CAST(:gd AS jsonb),"
            ":nde,:dte,:rb,:str,:roic,:roe,:ceff,:crev,:egt) "
            "ON CONFLICT (symbol) DO UPDATE SET "
            "rev_growth=COALESCE(EXCLUDED.rev_growth,"
            " symbol_flywheel.rev_growth),"
            # a stored accel diff is only trustworthy while the series
            # still computes — when fresh growth is uncomputable the
            # stored diff is a stale artifact, not data (PLTR carried
            # a -81pt phantom eps decel for exactly this reason)
            " rev_accel=CASE WHEN EXCLUDED.rev_accel IS NOT NULL"
            " THEN EXCLUDED.rev_accel"
            " WHEN EXCLUDED.rev_growth IS NULL THEN NULL"
            " WHEN ABS(symbol_flywheel.rev_accel) > 2 THEN NULL"
            " ELSE symbol_flywheel.rev_accel END,"
            " gm_now=COALESCE(EXCLUDED.gm_now, symbol_flywheel.gm_now),"
            " gm_slope=COALESCE(EXCLUDED.gm_slope,"
            " symbol_flywheel.gm_slope),"
            " gm_qoq=COALESCE(EXCLUDED.gm_qoq,"
            " symbol_flywheel.gm_qoq),"
            # eps YoY on a positive base can't fall below −1 (that's
            # zero EPS); stored values below are sign-flip junk
            " eps_growth=COALESCE(EXCLUDED.eps_growth,"
            " CASE WHEN symbol_flywheel.eps_growth < -1 THEN NULL "
            "      ELSE symbol_flywheel.eps_growth END),"
            " eps_accel=CASE WHEN EXCLUDED.eps_accel IS NOT NULL"
            " THEN EXCLUDED.eps_accel"
            " WHEN EXCLUDED.eps_growth IS NULL THEN NULL"
            " WHEN ABS(symbol_flywheel.eps_accel) > 2 THEN NULL"
            " ELSE symbol_flywheel.eps_accel END,"
            # same stale-artifact rule as the accel diffs: when the EPS
            # series refreshed but the TTM window couldn't compute
            # (negative/insufficient prior-year base), the stored TTM
            # is from an older window — stale, not last-good
            " eps_growth_ttm=CASE WHEN EXCLUDED.eps_growth_ttm"
            " IS NOT NULL THEN EXCLUDED.eps_growth_ttm"
            " WHEN EXCLUDED.eps_growth IS NOT NULL THEN NULL"
            " ELSE symbol_flywheel.eps_growth_ttm END,"
            " beat_streak=COALESCE(EXCLUDED.beat_streak,"
            " symbol_flywheel.beat_streak),"
            " avg_surprise_pct=COALESCE(EXCLUDED.avg_surprise_pct,"
            " symbol_flywheel.avg_surprise_pct),"
            " last_surprise_pct=COALESCE(EXCLUDED.last_surprise_pct,"
            " symbol_flywheel.last_surprise_pct),"
            " last_report_date=COALESCE(EXCLUDED.last_report_date,"
            " symbol_flywheel.last_report_date),"
            " fwd_eps_avg=COALESCE(EXCLUDED.fwd_eps_avg,"
            " symbol_flywheel.fwd_eps_avg),"
            " fwd_rev_avg=COALESCE(EXCLUDED.fwd_rev_avg,"
            " symbol_flywheel.fwd_rev_avg),"
            " num_analysts=COALESCE(EXCLUDED.num_analysts,"
            " symbol_flywheel.num_analysts),"
            # COALESCE keeps last-good on transient miss, but a stored
            # value outside the sanity band (±500%) is base-effect junk
            # — clear it even when the new compute is NULL
            " est_revision_pct=COALESCE(EXCLUDED.est_revision_pct,"
            " CASE WHEN ABS(symbol_flywheel.est_revision_pct) > 5 "
            "      THEN NULL ELSE symbol_flywheel.est_revision_pct "
            "END),"
            " fwd_pe=COALESCE(EXCLUDED.fwd_pe, symbol_flywheel.fwd_pe),"
            " muted_reaction=COALESCE(EXCLUDED.muted_reaction,"
            " symbol_flywheel.muted_reaction),"
            " gap_score=EXCLUDED.gap_score,"
            " gap_detail=EXCLUDED.gap_detail,"
            " net_debt_ebitda=COALESCE(EXCLUDED.net_debt_ebitda,"
            " symbol_flywheel.net_debt_ebitda),"
            " debt_to_equity=COALESCE(EXCLUDED.debt_to_equity,"
            " symbol_flywheel.debt_to_equity),"
            " rev_breadth_30d=COALESCE(EXCLUDED.rev_breadth_30d,"
            " symbol_flywheel.rev_breadth_30d),"
            " surprise_trend=COALESCE(EXCLUDED.surprise_trend,"
            " symbol_flywheel.surprise_trend),"
            " roic=COALESCE(EXCLUDED.roic, symbol_flywheel.roic),"
            " roe=COALESCE(EXCLUDED.roe, symbol_flywheel.roe),"
            " capex_eff=COALESCE(EXCLUDED.capex_eff,"
            " symbol_flywheel.capex_eff),"
            " capex_rev=COALESCE(EXCLUDED.capex_rev,"
            " symbol_flywheel.capex_rev),"
            " updated_at=now(), as_of=now()",
            {"s": sym, "rg": m.get("rev_growth"),
             "ra": m.get("rev_accel"), "gm": m.get("gm_now"),
             "gms": m.get("gm_slope"), "gmq": m.get("gm_qoq"),
             "eg": m.get("eps_growth"),
             "ea": m.get("eps_accel"), "bs": m.get("beat_streak"),
             "asp": m.get("avg_surprise_pct"),
             "lsp": m.get("last_surprise_pct"),
             "lrd": m.get("last_report_date"),
             "fe": m.get("fwd_eps_avg"), "fr": m.get("fwd_rev_avg"),
             "na": m.get("num_analysts"),
             "er": m.get("est_revision_pct"), "fpe": m.get("fwd_pe"),
             "mr": m.get("muted_reaction"), "gs": score,
             "nde": m.get("net_debt_ebitda"),
             "dte": m.get("debt_to_equity"),
             "rb": m.get("rev_breadth_30d"),
             "str": m.get("surprise_trend"),
             "roic": m.get("roic"), "roe": m.get("roe"),
             "ceff": m.get("capex_eff"), "crev": m.get("capex_rev"),
             "egt": m.get("eps_growth_ttm"),
             "gd": __import__("json").dumps(det)})
    except Exception as exc:
        logger.debug("flywheel persist %s: %s", sym, exc)
    try:
        from app.signals.earnings_calendar import (
            refresh_earnings_calendar)
        m["earnings"] = refresh_earnings_calendar(sym)
    except Exception as exc:
        logger.debug("earnings calendar %s: %s", sym, exc)
    m["gap_score"], m["gap_detail"] = score, det
    return m


async def refresh_flywheel(symbols: list[str],
                           concurrency: int = 4) -> dict:
    """Batch refresh — called at the tail of engine evals so boards
    carry fresh gap data."""
    from app.providers.financial_modeling_prep.client import (
        EnhancedFMPClient)
    fmp = EnhancedFMPClient.from_settings()
    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def _one(s):
        nonlocal done
        async with sem:
            try:
                await asyncio.to_thread(compute_flywheel, fmp, s)
                done += 1
            except Exception as exc:
                logger.debug("flywheel %s: %s", s, exc)

    await asyncio.gather(*(_one(s) for s in symbols))
    return {"refreshed": done, "total": len(symbols)}
