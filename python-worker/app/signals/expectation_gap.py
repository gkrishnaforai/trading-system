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
    # R&D intensity — for software names R&D IS the buildout; EPS/FCF
    # compression from a rising R&D ratio is investment, not demand
    # decay. rd_slope = latest ratio minus the year-ago quarter.
    rd = [(_div(q.get("researchAndDevelopmentExpenses"),
                q.get("revenue"))) for q in inc]
    # operating margin — GM-vs-OM split is the discriminator between
    # product economics (GM falls) and opex/acquisition burden
    # (GM flat, OM falls). Deal amortization + integration land in OM.
    om = [(_div(q.get("operatingIncome"), q.get("revenue")))
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
    capex_ttm = fcf_now = fcf_prev = acq_ttm = sbc_ttm = None
    try:
        # the -ttm endpoint is empty on this plan — sum quarters instead
        cf = fmp.get_cash_flow_statement(sym, "quarter") or []
        cx = [abs(float(q["capitalExpenditure"])) for q in cf[:4]
              if q.get("capitalExpenditure") is not None]
        capex_ttm = sum(cx) if len(cx) >= 3 else None

        # SBC load — acquisition retention grants + comp inflation land
        # in GAAP EPS but not the adjusted headline. High sbc/rev is the
        # mechanical part of the GAAP-vs-adjusted gap.
        sx = [abs(float(q["stockBasedCompensation"])) for q in cf[:4]
              if q.get("stockBasedCompensation") is not None]
        sbc_ttm = sum(sx) if len(sx) >= 3 else None

        fcf = [q.get("freeCashFlow") for q in cf[:8]]
        # freeCashFlow absent on some plan tiers → ocf − capex
        if not any(v is not None for v in fcf):
            fcf = [(q.get("operatingCashFlow") or 0)
                   - abs(q.get("capitalExpenditure") or 0)
                   if q.get("operatingCashFlow") is not None else None
                   for q in cf[:8]]
        _cur = [v for v in fcf[:4] if v is not None]
        _prv = [v for v in fcf[4:8] if v is not None]
        fcf_now = sum(_cur) if len(_cur) >= 3 else None
        fcf_prev = sum(_prv) if len(_prv) >= 3 else None

        # acquisitionsNet is the M&A cash line — TTM spend vs revenue
        # is the organic-growth sanity check. Absent = no acq spend.
        ax = [abs(float(q["acquisitionsNet"])) for q in cf[:4]
              if q.get("acquisitionsNet") is not None]
        acq_ttm = sum(ax) if ax else 0.0
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
        "rd_rev": rd[0],
        "rd_slope": (rd[0] - rd[4] if rd[0] is not None
                     and rd[4] is not None else None),
        "om_now": om[0],
        "om_qoq": (om[0] - om[1] if om[0] is not None
                   and om[1] is not None else None),
        "om_slope": (om[0] - om[4] if om[0] is not None
                     and om[4] is not None else None),
        "sbc_rev": (_div(sbc_ttm, rev_ttm)
                    if sbc_ttm and rev_ttm else None),
        "capex_eff": (_div(gp_delta, capex_ttm)
                      if gp_delta is not None else None),
        "capex_rev": (_div(capex_ttm, rev_ttm)
                      if capex_ttm and rev_ttm else None),
        "fcf_ttm": fcf_now,
        "fcf_margin": (_div(fcf_now, rev_ttm)
                       if fcf_now is not None and rev_ttm else None),
        "fcf_growth": (fcf_now / fcf_prev - 1
                       if fcf_now is not None and fcf_prev
                       and abs(fcf_prev) > 1e6
                       and (fcf_prev > 0) == (fcf_now > 0) else None),
        "acq_spend_ttm": acq_ttm,
        "acq_rev_pct": (_div(acq_ttm, rev_ttm)
                        if acq_ttm and rev_ttm else 0.0),
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
    """yfinance earnings_dates ∪ our own earnings_data journal →
    beat streak, avg/last surprise, last report date. The journal leg
    is the self-heal: verified prints the earnings pipeline already
    journaled can't freeze behind a provider outage (yf rate-limits
    datacenter IPs) the way the bare yf read could — its failure used
    to leave last_report_date COALESCE-frozen at last-known-good while
    the rest of the row kept refreshing."""
    import yfinance as yf
    from app.database import db
    try:
        ed = yf.Ticker(sym).earnings_dates
    except Exception:
        ed = None
    past = (ed[ed["Reported EPS"].notna()].copy()
            if ed is not None and not ed.empty else pd.DataFrame())
    # union by report date — the journal wins a same-date disagreement
    # (it's what the earnings engine actually graded)
    merged: dict = {}
    if not past.empty:
        past = past.sort_index(ascending=False)
        for ts, r in past.iterrows():
            merged[ts.date()] = (
                float(r["Reported EPS"]) if pd.notna(r["Reported EPS"])
                else None,
                float(r["Surprise(%)"]) if pd.notna(r["Surprise(%)"])
                else None)
    try:
        for r in db.execute_query(
                "SELECT earnings_date, eps_actual, surprise_percentage"
                " FROM earnings_data WHERE stock_symbol=:s"
                " AND eps_actual IS NOT NULL"
                " ORDER BY earnings_date DESC LIMIT 8", {"s": sym}) or []:
            merged[date.fromisoformat(str(r["earnings_date"])[:10])] = (
                float(r["eps_actual"])
                if r.get("eps_actual") is not None else None,
                float(r["surprise_percentage"])
                if r.get("surprise_percentage") is not None else None)
    except Exception:
        pass
    if not merged:
        return {}
    days = sorted(merged, reverse=True)
    surprises = [s for d in days
                 if (s := merged[d][1]) is not None][:4]
    streak = 0
    for v in surprises:
        if v > 0:
            streak += 1
        else:
            break
    last_date = days[0]
    trend = (surprises[0] - surprises[-1]
             if len(surprises) >= 3 else None)   # newest - oldest
    # reported (headline) EPS — non-GAAP for most issuers. YoY on the
    # reported series vs GAAP eps growth is the accounting-effect gap:
    # both falling = real decay; reported up / GAAP down = deal
    # amortization + SBC noise, not demand deterioration.
    rep = [v for d in days if (v := merged[d][0]) is not None][:5]
    rep_growth = (rep[0] / rep[4] - 1
                  if len(rep) >= 5 and rep[4] and rep[4] > 0.05
                  else None)
    return {"eps_rep": rep[0] if rep else None,
            "eps_rep_growth": rep_growth,
            "beat_streak": streak,
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
    # nearest forward fiscal year — the response order is not
    # guaranteed, and taking the first row past the horizon silently
    # grabbed FY+4 estimates (PLTR 'fwd EPS $14.38' was the FY2030
    # row, printing a fake-cheap 12.4× forward P/E)
    fwd_rows = [e for e in est
                if e.get("date") and str(e["date"])[:10] >
                str(today + timedelta(days=60))]
    if not fwd_rows:
        return {}
    fwd = min(fwd_rows, key=lambda e: str(e["date"])[:10])
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
    yf_eps = None
    try:
        import yfinance as yf
        tk = yf.Ticker(sym)
        trend = tk.eps_trend
        if trend is not None and not trend.empty \
                and "+1y" in trend.index:
            cur = trend.loc["+1y", "current"]
            ago = trend.loc["+1y", "90daysAgo"]
            if pd.notna(cur):
                yf_eps = float(cur)
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

    # write-time sanity vs the reported basis — a forward-FY consensus
    # orders of magnitude from reported TTM EPS is a provider row on
    # the wrong basis (far-year row, wrong field, unit mismatch), not
    # analyst opinion. PLTR's 'forward EPS' journaled $14.38 — the
    # FY2030 row — against $1.43 TTM and a ~$2.35 real FY27 print,
    # printing a fake-cheap 12.4x forward P/E. Ratio check needs a
    # sane base (>=$0.25 TTM); below that the denominator is near-zero
    # and the ratio can't distinguish junk from a real inflection.
    eps_suspect = None
    if eps_avg is not None:
        try:
            er = db.execute_query(
                "SELECT eps_actual FROM earnings_data"
                " WHERE stock_symbol=:s AND eps_actual IS NOT NULL"
                " ORDER BY earnings_date DESC LIMIT 4", {"s": sym})
            eps_ttm = (sum(float(r["eps_actual"]) for r in er)
                       if len(er) == 4 else None)
            yf_sane = (yf_eps is not None and
                       (eps_ttm is None or eps_ttm < 0.25 or
                        0.05 <= yf_eps / eps_ttm <= 6.0))
            out_of_band = (eps_ttm is not None and eps_ttm >= 0.25
                           and not (0.05 <= eps_avg / eps_ttm <= 6.0))
            # cross-source divergence — FMP's fiscal-year basis and
            # yfinance's +1y should agree closely; >25% apart means the
            # provider row is a different fiscal year (the AMZN/FN/
            # ALGM/PWR far-year rows all sit inside the TTM band and
            # only this check separates them from real fast growers)
            diverged = (eps_suspect is None and yf_eps is not None
                        and yf_eps > 0
                        and abs(eps_avg / yf_eps - 1) > 0.25)
            if out_of_band or diverged:
                if yf_sane:
                    eps_suspect = {
                        "provider_eps": eps_avg,
                        "eps_ttm": (round(eps_ttm, 2)
                                    if eps_ttm is not None else None),
                        "yf_eps": yf_eps,
                        "fixed_by": ("yfinance" if out_of_band
                                     else "cross_source")}
                    eps_avg = yf_eps
                elif out_of_band:
                    eps_suspect = {"provider_eps": eps_avg,
                                   "eps_ttm": round(eps_ttm, 2),
                                   "action": "cleared"}
                    eps_avg = None
                else:
                    # diverged but yf isn't a sane substitute either —
                    # keep the provider value, flag it unresolved
                    eps_suspect = {"provider_eps": eps_avg,
                                   "yf_eps": yf_eps,
                                   "action": "unresolved"}
                logger.warning("fwd_eps %s suspect: %s", sym,
                               eps_suspect)
        except Exception as exc:
            logger.debug("eps sanity %s: %s", sym, exc)

    return {"fwd_eps_avg": eps_avg, "fwd_rev_avg": rev_avg,
            "num_analysts": analysts, "est_revision_pct": revision_pct,
            "rev_breadth_30d": breadth, "eps_suspect": eps_suspect}


def _h2_load(fmp, sym: str) -> Optional[dict]:
    """How much of the current fiscal year's expected EPS growth is
    still unreported — the 'back-half-loaded' check.

    Provider reality: FMP's quarterly analyst-estimates are not on
    this plan, so the quarterly-curve version isn't computable. What
    IS available, on an estimate-consistent basis:

      0y avg / yearAgoEps     yfinance earnings_estimate — the in-
                              progress FY consensus + prior FY, both
                              on the adjusted basis analysts model
      Reported EPS            yfinance earnings_dates — headline
                              (adjusted) actuals per print
      period/fiscalYear       FMP income-statement — which quarters
                              belong to the current FY (for counting
                              how many prints have landed)

    load = (fy_est − reported_this_fy) / (fy_est − prior_fy)
         = share of the year's expected EPS growth still ahead.
    >1.0 means the street's growth target exceeds what's printed so
    far entirely. Only meaningful mid-year — early in the FY it's
    mechanically ~all-of-it — so the caller reads n_reported too.
    None = fail closed."""
    import yfinance as yf
    tk = yf.Ticker(sym)
    ee = tk.earnings_estimate
    if ee is None or ee.empty or "0y" not in ee.index:
        return None
    est_fy, prior_fy = (ee.loc["0y", "avg"], ee.loc["0y", "yearAgoEps"])
    if not (pd.notna(est_fy) and pd.notna(prior_fy)) \
            or prior_fy <= 0 or est_fy <= 0:
        return None
    fy_growth = float(est_fy) - float(prior_fy)
    if fy_growth <= 0:
        return None                     # not a growth year — moot

    # quarters reported so far in the fiscal year the '0y' row covers:
    # the count of income-statement rows in the latest fiscalYear
    inc = fmp._make_request(
        "/income-statement",
        {"symbol": sym, "period": "quarter", "limit": 8}) or []
    # staleness guard — if the latest reported quarter is >110d old,
    # the income feed's fiscalYear counter is a year behind the '0y'
    # row's fiscal year and the count maps to the wrong year
    try:
        if date.today() - date.fromisoformat(str(inc[0]["date"])[:10]) \
                > timedelta(days=110):
            return None
    except (KeyError, IndexError, ValueError):
        return None
    fys = [q.get("fiscalYear") for q in inc if q.get("fiscalYear")]
    n_reported = len([q for q in inc if q.get("fiscalYear")
                      == (fys[0] if fys else None)]) if fys else 0
    if n_reported == 0 or n_reported >= 4:
        return None                     # year not started / finished —
                                        # the load question is moot

    ed = tk.earnings_dates
    if ed is None or ed.empty or "Reported EPS" not in ed.columns:
        return None
    rep = [float(v) for v in
           ed.sort_index(ascending=False)["Reported EPS"].tolist()
           if pd.notna(v)]
    if len(rep) < n_reported:
        return None
    ytd = sum(rep[:n_reported])         # adjusted basis — matches est
    if ytd >= est_fy:
        return 0.0                      # year already delivered
    return {"load": (float(est_fy) - ytd) / fy_growth,
            "n_reported": n_reported,
            "unearned_share": (float(est_fy) - ytd) / float(est_fy)}


def _exp_risk(fmp, sym: str, m: dict) -> dict:
    """Growth-expectations risk — is the price outrunning the estimate?

    The named warning: price rising while forward estimates stop
    improving means returns are coming from multiple expansion —
    fragile to the first estimate cut. mult_expansion_pct decomposes
    the ~90d move: (1+dP)/(1+dE)-1 on the same clock as
    est_revision_pct. None = unknown; px_rev_divergence clears to
    NULL when uncomputable rather than persisting a stale flag.
    """
    from app.database import db
    out = {"mult_expansion_pct": None, "fwd_pe_pctile": None,
           "h2_growth_load": None, "px_rev_divergence": None,
           "cust_top1_pct": None, "cust_note": None}

    try:
        row = db.execute_query(
            "SELECT top1_pct, top5_note FROM symbol_customer_conc "
            "WHERE symbol=:s", {"s": sym})
        if row:
            out["cust_top1_pct"] = row[0]["top1_pct"]
            out["cust_note"] = row[0]["top5_note"]
    except Exception as exc:
        logger.debug("cust conc %s: %s", sym, exc)

    d_e = m.get("est_revision_pct")
    if d_e is not None and abs(d_e) > 5:
        d_e = None                       # sign-flip arithmetic junk
    d_p = None
    try:
        # canonical daily_bars — a READ, not bars.load(): this runs
        # per-symbol inside the flywheel job loop, and load()'s
        # thin-tape top-up would hide a provider fetch in a DB loop.
        # Thin tape just yields d_p=None — fail closed.
        closes = [float(r["close"]) for r in db.execute_query(
            "SELECT close FROM (SELECT date, close FROM daily_bars "
            "WHERE symbol=:s ORDER BY date DESC LIMIT 66) t "
            "ORDER BY date", {"s": sym})]
        if len(closes) >= 45:
            back = closes[-64] if len(closes) >= 64 else closes[0]
            if back and closes[-1]:
                d_p = closes[-1] / back - 1
    except Exception as exc:
        logger.debug("exp risk tape %s: %s", sym, exc)

    me = None
    if d_p is not None and d_e is not None and d_e > -0.95:
        me = (1 + d_p) / (1 + d_e) - 1
    else:
        # fallback: direct fwd-P/E change from journaled snapshots —
        # same decomposition without needing estimate history
        try:
            hist = db.execute_query(
                "SELECT (metrics->>'fwd_pe')::float AS pe "
                "FROM fundamental_snapshots WHERE symbol=:s "
                "AND metrics->>'fwd_pe' IS NOT NULL "
                "AND as_of <= :cut ORDER BY as_of DESC LIMIT 1",
                {"s": sym, "cut": date.today()
                  - timedelta(days=REVISION_LOOKBACK_DAYS)})
            if hist and hist[0]["pe"] and m.get("fwd_pe"):
                me = m["fwd_pe"] / hist[0]["pe"] - 1
        except Exception as exc:
            logger.debug("exp risk pe-hist %s: %s", sym, exc)
    if me is not None and abs(me) <= 3:
        out["mult_expansion_pct"] = round(me, 3)
    out["px_rev_divergence"] = (
        None if me is None else
        bool(me >= 0.15
             and d_p is not None and d_p >= 0.10
             and (d_e is None or d_e <= 0.03)))

    try:
        pes = [r["pe"] for r in db.execute_query(
            "SELECT (metrics->>'fwd_pe')::float AS pe "
            "FROM fundamental_snapshots WHERE symbol=:s "
            "AND metrics->>'fwd_pe' IS NOT NULL "
            "AND as_of > :cut",
            {"s": sym, "cut": date.today() - timedelta(days=365)})
            if r["pe"]]
        if m.get("fwd_pe") and len(pes) >= 20:
            out["fwd_pe_pctile"] = round(
                sum(1 for p in pes if p <= m["fwd_pe"]) / len(pes), 2)
    except Exception as exc:
        logger.debug("exp risk pctile %s: %s", sym, exc)

    try:
        h2 = _h2_load(fmp, sym)
        # only persist once the year is underway — with <2 quarters
        # reported the load is mechanically ~all-of-it and the caveat
        # can't distinguish 'back-half-loaded' from 'year just started'
        if h2 is not None and h2["n_reported"] >= 2:
            out["h2_growth_load"] = round(h2["load"], 3)
    except Exception as exc:
        logger.debug("exp risk h2 %s: %s", sym, exc)
    return out


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
    try:
        m.update(_exp_risk(fmp, sym, m))
    except Exception as exc:
        logger.debug("flywheel exp-risk %s: %s", sym, exc)

    score, det = _score(m)
    if m.get("eps_suspect"):
        det["eps_suspect"] = m["eps_suspect"]
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
            " eps_growth_ttm, fcf_ttm, fcf_margin, fcf_growth,"
            " acq_spend_ttm, acq_rev_pct, rd_rev, rd_slope,"
            " om_now, om_qoq, om_slope, sbc_rev, eps_rep,"
            " eps_rep_growth, mult_expansion_pct, fwd_pe_pctile,"
            " h2_growth_load, px_rev_divergence, cust_top1_pct,"
            " cust_note) "
            "VALUES (:s,:rg,:ra,:gm,:gms,:gmq,:eg,:ea,:bs,:asp,:lsp,:lrd,"
            ":fe,:fr,:na,:er,:fpe,:mr,:gs,CAST(:gd AS jsonb),"
            ":nde,:dte,:rb,:str,:roic,:roe,:ceff,:crev,:egt,"
            ":ft,:fm,:fg,:aspd,:arp,:rdr,:rds,"
            ":omn,:omq,:oms,:sbcr,:erp,:erpg,"
            ":mexp,:ppe,:h2l,:prd,:ct1,:cn) "
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
            # cleared-by-sanity must override COALESCE — otherwise the
            # corrupt stored value (PLTR's $14.38 FY2030 row) survives
            " fwd_eps_avg=CASE WHEN :feb THEN NULL"
            " ELSE COALESCE(EXCLUDED.fwd_eps_avg,"
            "      symbol_flywheel.fwd_eps_avg) END,"
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
            " fcf_ttm=COALESCE(EXCLUDED.fcf_ttm,"
            " symbol_flywheel.fcf_ttm),"
            " fcf_margin=COALESCE(EXCLUDED.fcf_margin,"
            " symbol_flywheel.fcf_margin),"
            " fcf_growth=COALESCE(EXCLUDED.fcf_growth,"
            " symbol_flywheel.fcf_growth),"
            " acq_spend_ttm=COALESCE(EXCLUDED.acq_spend_ttm,"
            " symbol_flywheel.acq_spend_ttm),"
            " acq_rev_pct=COALESCE(EXCLUDED.acq_rev_pct,"
            " symbol_flywheel.acq_rev_pct),"
            " rd_rev=COALESCE(EXCLUDED.rd_rev, symbol_flywheel.rd_rev),"
            " rd_slope=COALESCE(EXCLUDED.rd_slope,"
            " symbol_flywheel.rd_slope),"
            " om_now=COALESCE(EXCLUDED.om_now, symbol_flywheel.om_now),"
            " om_qoq=COALESCE(EXCLUDED.om_qoq, symbol_flywheel.om_qoq),"
            " om_slope=COALESCE(EXCLUDED.om_slope,"
            " symbol_flywheel.om_slope),"
            " sbc_rev=COALESCE(EXCLUDED.sbc_rev,"
            " symbol_flywheel.sbc_rev),"
            " eps_rep=COALESCE(EXCLUDED.eps_rep,"
            " symbol_flywheel.eps_rep),"
            " eps_rep_growth=COALESCE(EXCLUDED.eps_rep_growth,"
            " symbol_flywheel.eps_rep_growth),"
            " mult_expansion_pct=COALESCE(EXCLUDED.mult_expansion_pct,"
            " symbol_flywheel.mult_expansion_pct),"
            " fwd_pe_pctile=COALESCE(EXCLUDED.fwd_pe_pctile,"
            " symbol_flywheel.fwd_pe_pctile),"
            " h2_growth_load=COALESCE(EXCLUDED.h2_growth_load,"
            " symbol_flywheel.h2_growth_load),"
            # divergence is a CURRENT-state flag, not a metric: when
            # the inputs can't compute this run, NULL it — a stale
            # 'diverging' persisted under COALESCE would keep warning
            # after the tape healed
            " px_rev_divergence=EXCLUDED.px_rev_divergence,"
            " cust_top1_pct=COALESCE(EXCLUDED.cust_top1_pct,"
            " symbol_flywheel.cust_top1_pct),"
            " cust_note=COALESCE(EXCLUDED.cust_note,"
            " symbol_flywheel.cust_note),"
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
             "feb": bool((m.get("eps_suspect") or {})
                        .get("action") == "cleared"),
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
             "ft": m.get("fcf_ttm"), "fm": m.get("fcf_margin"),
             "fg": m.get("fcf_growth"),
             "aspd": m.get("acq_spend_ttm"),
             "arp": m.get("acq_rev_pct"),
             "rdr": m.get("rd_rev"), "rds": m.get("rd_slope"),
             "omn": m.get("om_now"), "omq": m.get("om_qoq"),
             "oms": m.get("om_slope"), "sbcr": m.get("sbc_rev"),
             "erp": m.get("eps_rep"), "erpg": m.get("eps_rep_growth"),
             "mexp": m.get("mult_expansion_pct"),
             "ppe": m.get("fwd_pe_pctile"),
             "h2l": m.get("h2_growth_load"),
             "prd": m.get("px_rev_divergence"),
             "ct1": m.get("cust_top1_pct"),
             "cn": m.get("cust_note"),
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


def audit_fwd_eps(symbols: Optional[list[str]] = None) -> list[dict]:
    """Deterministic audit of every stored fwd_eps_avg — no provider
    calls. Two checks, same logic as the write-time guard:

      ratio     fwd_eps vs reported TTM EPS (0.05x-6.0x band)
      snapshot  fwd_eps vs the NEAREST-future period's eps_avg in
                symbol_estimate_snapshots — >25% divergence means the
                stored value came from a different fiscal year

    Returns the suspect rows; repair_fwd_eps() recomputes them."""
    from app.database import db
    p: dict = {}
    sql = ("SELECT f.symbol, f.fwd_eps_avg, f.fwd_pe, f.updated_at,"
           " (SELECT MIN(period_end) FROM symbol_estimate_snapshots ss"
           "  WHERE ss.symbol=f.symbol"
           "    AND ss.period_end > CURRENT_DATE + 60) AS fwd_period,"
           " (SELECT ss.eps_avg FROM symbol_estimate_snapshots ss"
           "  WHERE ss.symbol=f.symbol"
           "    AND ss.period_end > CURRENT_DATE + 60"
           "  ORDER BY ss.period_end, ss.as_of DESC LIMIT 1)"
           "   AS snap_eps"
           " FROM symbol_flywheel f WHERE f.fwd_eps_avg IS NOT NULL")
    if symbols:
        sql += " AND f.symbol = ANY(:s)"
        p["s"] = [s.upper() for s in symbols]
    rows = db.execute_query(sql, p)
    ttm = {r["symbol"]: r["t"] for r in db.execute_query(
        "SELECT symbol, SUM(eps_actual) AS t FROM ("
        "  SELECT stock_symbol AS symbol, eps_actual,"
        "   ROW_NUMBER() OVER (PARTITION BY stock_symbol"
        "    ORDER BY earnings_date DESC) AS rn"
        "  FROM earnings_data WHERE eps_actual IS NOT NULL) x"
        " WHERE rn <= 4 GROUP BY symbol HAVING COUNT(*) = 4")}
    out = []
    for r in rows:
        sym = r["symbol"]
        fwd = r.get("fwd_eps_avg")
        t = ttm.get(sym)
        ratio = (float(fwd) / float(t)
                 if fwd is not None and t and float(t) >= 0.25
                 else None)
        snap = r.get("snap_eps")
        snap_div = (abs(float(fwd) / float(snap) - 1)
                    if fwd is not None and snap and float(snap) > 0
                    else None)
        bad_ratio = ratio is not None and not (0.05 <= ratio <= 6.0)
        bad_snap = snap_div is not None and snap_div > 0.25
        if bad_ratio or bad_snap:
            out.append({
                "symbol": sym, "fwd_eps_avg": fwd,
                "eps_ttm": round(float(t), 2) if t else None,
                "ttm_ratio": round(ratio, 2) if ratio else None,
                "snap_eps": snap, "fwd_period": str(r.get("fwd_period")),
                "snap_divergence": round(snap_div, 2)
                                   if snap_div else None,
                "checks": [c for c, b in
                           (("ttm_ratio", bad_ratio),
                            ("snapshot_year", bad_snap)) if b],
                "updated_at": str(r.get("updated_at"))[:19]})
    return out


async def repair_fwd_eps(symbols: Optional[list[str]] = None,
                         batch: int = 40,
                         concurrency: int = 5) -> dict:
    """Audit → recompute suspects → re-resolve FV where the EPS moved.

    The flywheel recompute is the fix: _estimates now picks the
    nearest forward year and the sanity guard clears/corrects
    anything still out of band. Symbols whose forward EPS moved >10%
    get a fair-value re-resolve — the earnings-driven FV legs were
    priced on the same wrong estimate.

    Batched + concurrent: the first full-book pass found ~130
    suspects and a serial compute (~25-40s of provider calls per
    symbol) blew the 15m job timeout after only ~3 fixes. Each run
    re-audits, so fixed names drop out of the suspect list — the job
    converges over successive runs within its timeout."""
    suspects = audit_fwd_eps(symbols)
    todo = suspects[:batch]
    if not todo:
        return {"audited": len(suspects), "suspects": suspects,
                "fixed": [], "failed": [], "fv_recomputed": [],
                "remaining": 0}
    from app.providers.financial_modeling_prep.client import (
        EnhancedFMPClient)
    fmp = EnhancedFMPClient.from_settings()
    sem = asyncio.Semaphore(concurrency)
    fixed, failed, fv = [], [], []

    async def _one(row):
        sym = row["symbol"]
        async with sem:
            before = row["fwd_eps_avg"]
            m = await asyncio.to_thread(compute_flywheel, fmp, sym)
            after = m.get("fwd_eps_avg")
            moved = (before is None or after is None
                     or abs(after / before - 1) > 0.10)
            return {"symbol": sym, "before": before, "after": after,
                    "suspect": m.get("eps_suspect")}, moved

    results = await asyncio.gather(
        *(_one(r) for r in todo), return_exceptions=True)
    for res in results:
        if isinstance(res, Exception):
            failed.append({"error": str(res)[:120]})
            continue
        rec, moved = res
        fixed.append(rec)
        if moved:
            fv.append(rec["symbol"])

    fv_sem = asyncio.Semaphore(2)
    async def _fv(sym):
        async with fv_sem:
            try:
                from app.signals import fv_sweep
                return await asyncio.to_thread(
                    fv_sweep._resolve_fv, sym)
            except Exception as exc:
                return {"symbol": sym, "error": str(exc)[:120]}
    fv_results = await asyncio.gather(*(_fv(s) for s in fv))
    remaining = len(audit_fwd_eps(symbols))
    return {"audited": len(suspects), "batch": len(todo),
            "fixed": fixed, "failed": failed,
            "fv_recomputed": list(fv_results),
            "remaining": remaining}


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
