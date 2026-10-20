"""Correction-alarm engine — is this a dip or a regime break?

Four independent legs, each scoring 0-100 alarm intensity. A normal
correction and the start of a recession look identical on day one of
the tape; these four are the classic discriminators:

  revision_breadth    Are analysts cutting estimates ACROSS sectors?
                      Per-symbol est_revision_pct exists in flywheel
                      and feeds stock decisions — this aggregates it
                      into the market-level signal the stock layer
                      can't see. Broad cuts = earnings recession.
  labor_credit        Correction or recession? HY spreads widening +
                      claims rising = credit event brewing; tight
                      spreads + calm claims = tape panic only.
                      Keyless FRED CSV (no API key needed).
  real_yields         DFII10 (10y TIPS). Rising real yields compress
                      growth multiples — a dip driven by this is a
                      de-rating, not an earnings problem.
  valuation_decomp    Is P/E falling because prices fell (de-rating —
                      selloff-engine territory) or because the E fell
                      (earnings cut — repricing, dips keep dipping)?
                      Needs journaled history; reports partial until
                      enough eval rows exist.

Verdict — correction_character:
  earnings_recession   broad cuts + credit stress + falling E —
                       the dangerous one; dips keep dipping
  credit_stress        HY widening fast / claims inflecting
  growth_scare         real yields rising, E intact, credit calm —
                       multiple compression; selloff-engine territory
  liquidity_stress     vol/positioning event, fundamentals + credit
                       untouched — the recoverable one
  none_yet             no leg elevated — a dip, not a regime break

Journals daily to correction_evals. Until the journal is long, this
is a READ layer — it never overrides posture; it informs it.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import urllib.request
from datetime import date, timedelta
from statistics import median
from typing import Any, Optional

logger = logging.getLogger(__name__)

_FRED_CSV = ("https://fred.stlouisfed.org/graph/fredgraph.csv"
             "?id={sid}&cosd={start}")


def _f(v) -> Optional[float]:
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


# ------------------------------ FRED (keyless) --------------------------

def _fred_series(sid: str, days: int = 120) -> list[tuple[date, float]]:
    """fredgraph.csv — public, no API key. (date, value) ascending."""
    start = (date.today() - timedelta(days=days)).isoformat()
    try:
        req = urllib.request.Request(
            _FRED_CSV.format(sid=sid, start=start),
            headers={"User-Agent": "trading-system/alarms"})
        txt = urllib.request.urlopen(req, timeout=20).read().decode()
        out = []
        for row in csv.DictReader(io.StringIO(txt)):
            v = _f(row.get(sid))
            if v is not None:
                out.append((date.fromisoformat(row["observation_date"]), v))
        return out
    except Exception as e:                                  # noqa: BLE001
        logger.debug("fred csv %s: %s", sid, e)
        return []


def _delta(series: list[tuple[date, float]], lookback: int = 20
           ) -> Optional[float]:
    if len(series) <= lookback:
        return None
    return series[-1][1] - series[-1 - lookback][1]


# ------------------------------ legs ------------------------------------

def _revision_breadth() -> dict[str, Any]:
    """Analyst cuts across sectors — flywheel est_revision_pct."""
    from app.database import db
    rows = db.execute_query(
        "SELECT s.sector, f.est_revision_pct FROM symbol_flywheel f"
        " JOIN stocks s ON s.symbol=f.symbol"
        " WHERE f.est_revision_pct IS NOT NULL AND s.sector IS NOT NULL")
    n = len(rows)
    if n < 30:
        return {"score": None, "note": "insufficient revision coverage",
                "n": n}
    cutting = sum(1 for r in rows if (r["est_revision_pct"] or 0) < -5)
    raising = sum(1 for r in rows if (r["est_revision_pct"] or 0) > 5)
    med = median(r["est_revision_pct"] for r in rows)
    by_sec: dict[str, list] = {}
    for r in rows:
        by_sec.setdefault(r["sector"], []).append(r["est_revision_pct"])
    sec_neg = {s: median(v) for s, v in by_sec.items()
               if len(v) >= 5 and median(v) < 0}
    pct_cut = cutting / n * 100
    score = min(100, pct_cut * 2 + len(sec_neg) * 8)
    return {
        "score": round(score, 1),
        "pct_cutting_5": round(pct_cut, 1),
        "pct_raising_5": round(raising / n * 100, 1),
        "median_revision": round(med, 2),
        "sectors_negative": sorted(sec_neg),
        "note": (f"{pct_cut:.0f}% of {n} names seeing >5% estimate "
                 f"cuts · median revision {med:+.1f}% · "
                 f"{len(sec_neg)} sectors net-negative")}


def _labor_credit() -> dict[str, Any]:
    """Correction vs recession — HY spreads + jobless claims."""
    hy = _fred_series("BAMLH0A0HYM2", days=120)
    icsa = _fred_series("ICSA", days=120)
    out: dict[str, Any] = {}
    score = 0.0
    if hy:
        lvl = hy[-1][1]
        d20 = _delta(hy, 20)
        out["hy_oas"] = round(lvl, 2)
        out["hy_oas_d20"] = round(d20, 2) if d20 is not None else None
        # level: <3.5 calm · 3.5-4.5 watch · 4.5-6 stress · >6 crisis
        score += (0 if lvl < 3.5 else 20 if lvl < 4.5 else
                  45 if lvl < 6 else 70)
        # widening velocity matters more than level for early warning
        if d20 is not None:
            score += (0 if d20 < 0.25 else 15 if d20 < 0.5
                      else 30 if d20 < 0.75 else 45)
    else:
        out["hy_oas"] = None
    if icsa:
        cur = icsa[-1][1] / 1000                      # raw → thousands
        prior4 = icsa[-5][1] / 1000 if len(icsa) >= 5 else None
        out["icsa_k"] = round(cur, 0)
        if prior4:
            out["icsa_d4w"] = round(cur - prior4, 0)
            score += (0 if cur - prior4 < 0 else 10 if cur - prior4 < 30
                      else 20)
    else:
        out["icsa_k"] = None
    out["score"] = round(min(100, score), 1)
    if hy:
        calm = (hy[-1][1] < 3.5 and (out.get("hy_oas_d20") or 0) < 0.25)
        out["note"] = (f"HY OAS {hy[-1][1]:.2f}% "
                       f"{out.get('hy_oas_d20'):+.2f}/20d · "
                       f"claims {out.get('icsa_k', '?')}k — "
                       + ("credit calm: correction, not recession"
                          if calm else "credit under stress"))
    return out


def _real_yields() -> dict[str, Any]:
    """DFII10 — 10y TIPS. Rising real yields compress growth multiples."""
    tips = _fred_series("DFII10", days=120)
    if not tips:
        return {"score": None, "note": "no TIPS series"}
    lvl, d20 = tips[-1][1], _delta(tips, 20)
    score = 0.0
    if lvl is not None:
        score += 0 if lvl < 1.5 else 15 if lvl < 2.0 else 30
    if d20 is not None:
        score += (0 if d20 < 0 else 20 if d20 < 0.15 else 40
                  if d20 < 0.3 else 55)
    return {"score": round(min(100, score), 1),
            "dfii10": round(lvl, 2),
            "dfii10_d20": round(d20, 2) if d20 is not None else None,
            "note": (f"real 10y {lvl:.2f}% {d20:+.2f}/20d — "
                     + ("real yields FALLING — easing pressure on "
                        "growth multiples" if (d20 or 0) < 0 else
                        "real yields RISING — multiple compression"))}


def _valuation_decomp() -> dict[str, Any]:
    """P/E down: de-rating vs earnings-cut. Needs journaled history —
    the eval row itself is the time series; partial until ~5 rows."""
    from app.database import db
    cur = db.execute_query(
        "SELECT percentile_cont(0.5) WITHIN GROUP"
        "  (ORDER BY f.fwd_pe) AS pe,"
        " percentile_cont(0.5) WITHIN GROUP"
        "  (ORDER BY f.fwd_eps_avg) AS eps,"
        " count(*) FILTER (WHERE f.fwd_eps_avg IS NOT NULL) AS n"
        " FROM symbol_flywheel f"
        " JOIN stocks s ON s.symbol=f.symbol"
        " WHERE s.is_active")
    row = cur[0] if cur else {}
    med_pe, med_eps = _f(row.get("pe")), _f(row.get("eps"))
    hist = db.execute_query(
        "SELECT readings->'valuation_decomp'->>'med_pe' AS pe,"
        " readings->'valuation_decomp'->>'med_eps' AS eps"
        " FROM correction_evals"
        " WHERE readings->'valuation_decomp'->>'med_pe' IS NOT NULL"
        " ORDER BY as_of DESC LIMIT 30")
    out: dict[str, Any] = {"med_pe": med_pe, "med_eps": med_eps}
    if len(hist) >= 5 and med_pe and med_eps:
        pe0, eps0 = _f(hist[-1]["pe"]), _f(hist[-1]["eps"])
        if pe0 and eps0:
            pe_d = med_pe / pe0 - 1
            eps_d = med_eps / eps0 - 1
            out["pe_chg"] = round(pe_d, 4)
            out["eps_chg"] = round(eps_d, 4)
            if eps_d < -0.02:
                kind = "earnings_cut"
                score = 70                  # the E is falling — repricing
            elif pe_d < -0.05 and eps_d >= -0.02:
                kind = "derating"
                score = 35                  # price fell, E intact — dip
            elif pe_d > 0.03:
                kind = "re-rating"
                score = 10
            else:
                kind = "flat"
                score = 15
            out["kind"] = kind
            out["score"] = score
            out["note"] = (f"universe median: P/E {pe_d * 100:+.1f}% vs "
                           f"fwd-EPS {eps_d * 100:+.1f}% over "
                           f"{len(hist)} evals — {kind.replace('_', ' ')}")
            return out
    out["score"] = None
    out["note"] = (f"median fwd P/E {med_pe:.1f} — decomposition arms "
                   f"after ~5 journaled evals (have {len(hist)})"
                   if med_pe else "no fwd P/E coverage")
    return out


# ------------------------------ verdict ---------------------------------

_CHAR_TONE = {
    "earnings_recession": "the dangerous one — dips keep dipping",
    "credit_stress": "credit conditions deteriorating — spreads "
                     "widening early; level may still look benign",
    "growth_scare": "multiple compression — selloff-engine "
                    "territory; sound dips are buyable",
    "liquidity_stress": "positioning unwind — recoverable once "
                        "the flush finishes",
    "none_yet": "no structural alarm — a dip, not a regime break",
}


def evaluate(persist: bool = True) -> dict[str, Any]:
    rb = _revision_breadth()
    lc = _labor_credit()
    ry = _real_yields()
    vd = _valuation_decomp()

    rb_s = rb.get("score") or 0
    lc_s = lc.get("score") or 0
    ry_s = ry.get("score") or 0
    vd_s = vd.get("score") or 0

    if rb_s >= 55 and lc_s >= 40:
        char = "earnings_recession"
    elif lc_s >= 45:
        # HY level can still look benign while the WIDENING is the
        # early warning — a fast +50bp/20d move during an equity
        # wobble is exactly what this alarm exists for
        char = "credit_stress"
    elif ry_s >= 45 and rb_s < 40 and lc_s < 45:
        char = "growth_scare"
    elif rb_s < 30 and lc_s < 30 and (vd.get("kind") in
                                    ("derating", None)):
        # fundamentals intact — whatever's happening is tape, not E
        char = ("liquidity_stress" if lc_s < 30 and rb_s < 30
                and vd.get("kind") == "derating" else "none_yet")
    else:
        char = "none_yet"

    severity = ("alarm" if max(rb_s, lc_s) >= 70 else
                "warning" if max(rb_s, lc_s, ry_s) >= 45 else
                "watch" if max(rb_s, lc_s, ry_s, vd_s) >= 25
                else "quiet")

    out = {"as_of": str(date.today()),
           "correction_character": char,
           "severity": severity,
           "meaning": _CHAR_TONE[char],
           "legs": {"revision_breadth": rb, "labor_credit": lc,
                    "real_yields": ry, "valuation_decomp": vd}}
    if persist:
        _persist(out)
    return out


def _persist(o: dict[str, Any]) -> None:
    from app.database import db
    db.execute_update(
        "INSERT INTO correction_evals (as_of, correction_character,"
        " severity, readings)"
        " VALUES (:d, :c, :s, CAST(:r AS jsonb))"
        " ON CONFLICT (as_of) DO UPDATE SET"
        " correction_character=EXCLUDED.correction_character,"
        " severity=EXCLUDED.severity,"
        " readings=EXCLUDED.readings",
        {"d": date.today(), "c": o["correction_character"],
         "s": o["severity"], "r": json.dumps(o, default=str)})


def latest() -> dict[str, Any]:
    from app.database import db
    r = db.execute_query(
        "SELECT as_of, correction_character, severity, readings"
        " FROM correction_evals ORDER BY as_of DESC LIMIT 1")
    if not r:
        return {}
    row = r[0]
    return {**(row["readings"] or {}), "as_of": str(row["as_of"])}


if __name__ == "__main__":
    print(json.dumps(evaluate(persist="--persist" in __import__("sys").argv),
                    indent=1, default=str))
