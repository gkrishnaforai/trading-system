"""Sector timing — bottom opportunity vs rebound confirmation as
SEPARATE scores over a 4-state machine. Generalizes theme_rotation
(the AI-basket legs) to any sector via its ETF + theme membership.

  opp   : is it cheap/exhausted?  (drawdown, oversold, capitulation)
  conf  : is it recovering?        (trend reclaim, breadth, RS, revisions)
  trap  : oversold AND deteriorating fundamentals (bull-trap risk)

States: none → selloff → capitulation → potential_bottom →
bottom_forming → rebound_confirmed; failed_rebound when a formed
bottom breaks its low again. Missing data lowers confidence —
never counts as neutral."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from app.database import db
from app.signals.theme_rotation import _closes, _ret

SECTORS = {
    "semiconductors": {"etf": "SMH",
                       "theme": ["NVDA", "AVGO", "AMD", "TSM", "MU",
                                 "AMAT", "LRCX", "KLAC", "INTC", "QCOM"]},
    "ai_infra": {"etf": "SMH",
                 "theme": ["NVDA", "VRT", "ALAB", "CRDO", "COHR", "FN",
                           "PWR", "ANET", "GEV", "ETN"]},
    "software": {"etf": "IGV",
                 "theme": ["MSFT", "PLTR", "CRM", "NOW", "ADBE", "ORCL",
                           "SNOW", "DDOG", "CRWD", "PANW"]},
    "energy": {"etf": "XLE",
               "theme": ["XOM", "CVX", "COP", "EOG", "SLB", "OXY", "MPC",
                         "VLO", "PSX", "DVN"]},
    "financials": {"etf": "XLF",
                   "theme": ["JPM", "BAC", "GS", "MS", "WFC", "C", "AXP",
                             "BLK", "SPGI", "PYPL"]},
    "consumer": {"etf": "XLY",
                 "theme": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX",
                           "LOW", "TJX", "BKNG", "CMG"]},
}


def _pct_below_sma20(syms: List[str], as_of: date) -> Optional[float]:
    hits, n = 0, 0
    for s in syms:
        c = _closes(s, 30, as_of)
        if len(c) < 20:
            continue
        n += 1
        if c[-1] < sum(c[-20:]) / 20:
            hits += 1
    return hits / n if n >= 4 else None


def _median_revision(syms: List[str]) -> Optional[float]:
    rows = db.execute_query(
        "SELECT est_revision_pct FROM symbol_flywheel"
        " WHERE symbol = ANY(:s) AND est_revision_pct IS NOT NULL",
        {"s": syms})
    vals = sorted(float(r["est_revision_pct"]) for r in rows)
    return vals[len(vals) // 2] if len(vals) >= 3 else None


def compute(as_of: Optional[date] = None) -> Dict[str, Any]:
    as_of = as_of or date.today()
    spy = _closes("SPY", 260, as_of)
    out = []
    for key, spec in SECTORS.items():
        etf = spec["etf"]
        c = _closes(etf, 260, as_of)
        missing = []
        if len(c) < 60 or len(spy) < 60:
            missing.append("etf_history")
        hi60 = max(c[-60:]) if len(c) >= 60 else (max(c) if c else None)
        last = c[-1] if c else None
        dd = (last / hi60 - 1) if (last and hi60) else None
        sma20 = sum(c[-20:]) / 20 if len(c) >= 20 else None
        sma50 = sum(c[-50:]) / 50 if len(c) >= 50 else None
        rs20 = (_ret(c, 20) - _ret(spy, 20)) if (
            c and spy and len(c) > 21 and len(spy) > 21
            and _ret(c, 20) is not None and _ret(spy, 20) is not None) \
            else None
        rs60 = (_ret(c, 60) - _ret(spy, 60)) if (
            c and spy and len(c) > 61 and len(spy) > 61
            and _ret(c, 60) is not None and _ret(spy, 60) is not None) \
            else None
        below20 = _pct_below_sma20(spec["theme"], as_of)
        if below20 is None:
            missing.append("breadth")
        rev = _median_revision(spec["theme"])
        if rev is None:
            missing.append("revisions")
        stretch = (last / sma20 - 1) if (last and sma20) else None

        # opportunity — cheap + exhausted
        opp = 0.0
        if dd is not None:
            opp += min(35, max(0, -dd * 140))          # -25% → 35
        if stretch is not None and stretch < 0:
            opp += min(20, -stretch * 100)              # -20% → 20
        if below20 is not None:
            opp += below20 * 25                          # exhaustion
        if rev is not None and rev <= 0:
            opp += 10 if -15 <= rev else 5               # trough-ish
        opp = round(min(100, opp), 1)

        # confirmation — is the turn real
        conf = 0.0
        if sma20 and last and last > sma20:
            conf += 25
        if sma50 and last and last > sma50:
            conf += 15
        if rs20 is not None and rs20 > 0:
            conf += 15 + min(15, rs20 * 150)
        if below20 is not None and below20 < 0.4:
            conf += 15
        if rev is not None and rev > 0:
            conf += 15 + min(10, rev / 5)
        conf = round(min(100, conf), 1)

        # trap — oversold while fundamentals deteriorate
        trap = 0.0
        if rev is not None and rev < -8:
            trap += 45
        elif rev is not None and rev < 0:
            trap += 25
        if rs60 is not None and rs60 < -0.08:
            trap += 30
        if dd is not None and dd < -0.20:
            trap += 25
        trap = round(min(100, trap), 1)

        # state machine — 'none' means quiet/healthy, not 'in a
        # selloff too shallow to matter'; a real drawdown reads
        # selloff even before it's an opportunity
        if opp < 40:
            state = "selloff" if (dd is not None and dd < -0.08
                                  or (rs20 is not None
                                      and rs20 < -0.08)) else "none"
        elif conf >= 65:
            state = "rebound_confirmed"
        elif conf >= 50:
            state = "bottom_forming"
        elif opp >= 60 and conf < 40:
            state = "capitulation" if (stretch or 0) < -0.06 \
                else "potential_bottom"
        elif opp >= 60:
            state = "potential_bottom"
        else:
            state = "selloff"
        out.append({"sector": key, "etf": etf, "as_of": str(as_of),
                    "opp_score": opp, "conf_score": conf,
                    "trap_score": trap, "state": state,
                    "signals": {"drawdown_pct": round(dd * 100, 1)
                                if dd is not None else None,
                                "vs_sma20_pct": round(stretch * 100, 1)
                                if stretch is not None else None,
                                "rs20_pct": round(rs20 * 100, 1)
                                if rs20 is not None else None,
                                "rs60_pct": round(rs60 * 100, 1)
                                if rs60 is not None else None,
                                "breadth_below_20": below20,
                                "median_revision": rev},
                    "missing": missing})
    return {"as_of": str(as_of), "sectors": out}


def _persist(row: Dict[str, Any]) -> None:
    for s in row["sectors"]:
        db.execute_update(
            "INSERT INTO sector_timing_daily"
            " (as_of, sector_key, etf, opp_score, conf_score,"
            "  trap_score, state, signals, missing)"
            " VALUES (:d, :k, :e, :o, :c, :t, :st, :si, :mi)"
            " ON CONFLICT (as_of, sector_key) DO UPDATE SET"
            " opp_score=EXCLUDED.opp_score,"
            " conf_score=EXCLUDED.conf_score,"
            " trap_score=EXCLUDED.trap_score,"
            " state=EXCLUDED.state, signals=EXCLUDED.signals,"
            " missing=EXCLUDED.missing",
            {"d": row["as_of"], "k": s["sector"], "e": s["etf"],
             "o": s["opp_score"], "c": s["conf_score"],
             "t": s["trap_score"], "st": s["state"],
             "si": __import__("json").dumps(s["signals"]),
             "mi": __import__("json").dumps(s["missing"])})


def run() -> Dict[str, Any]:
    row = compute()
    _persist(row)
    return row


def current() -> Dict[str, Any]:
    rows = db.execute_query(
        "SELECT DISTINCT ON (sector_key) sector_key, as_of, etf,"
        " opp_score, conf_score, trap_score, state, signals, missing"
        " FROM sector_timing_daily ORDER BY sector_key, as_of DESC")
    return {"sectors": rows,
            "history_days": db.execute_query(
                "SELECT count(DISTINCT as_of) n"
                " FROM sector_timing_daily")[0]["n"]}
