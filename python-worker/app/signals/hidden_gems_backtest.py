"""Hidden Gems backtest + grading — answers "does the score actually
predict returns", and calibrates which score bands earn conviction.

Two honest modes, no look-ahead either way:

MODE A — shadow grading (the real backtest, fills over time):
    hidden_gem_snapshots are journaled daily with score; a grading
    pass joins forward returns at +20d/+60d vs SPY once the window
    matures. Cannot look ahead — the score was frozen at snapshot.

MODE B — partial-factor historical replay:
    earnings_data.actuals (usable when earnings_date <= as_of — the
    report date, never the period end) + daily_bars reconstruct the
    growth-trajectory + tape factors back to ~Oct 2025. Estimate-
    revision and FCF/quality factors have no point-in-time history —
    they score None and are EXCLUDED from the replay composite rather
    than faked. Replay answers "did the computable factors predict
    returns" — the composite's edge gets proven by Mode A.

Score buckets → hit rates tell you where conviction thresholds sit.
Survivorship caveat: universe = current flywheel coverage; delisted
names are absent — replay overestimates hit rate modestly.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from statistics import mean, median
from typing import Any, Optional

logger = logging.getLogger(__name__)

HORIZONS = (20, 60)                    # trading days
REPLAY_FACTOR_W = {                    # factors replayable as-of
    "eps_growth": .20, "rev_growth": .10, "eps_accel": .20,
    "rev_accel": .10, "quality": .15,
    "rel_strength": .15, "price_vol": .10}
# same veto semantics as the live scanner's hard filters
REPLAY_HARD = {"eps_growth_min": 0.20, "rev_growth_min": 0.15,
               "gm_min": 0.20, "dilution_max": 0.10,
               "debt_to_equity_max": 3.0}


def _bars(as_of: date, syms: list[str]) -> dict[str, list[dict]]:
    """Close series per symbol ending at as_of."""
    from app.database import db
    rows = db.execute_query(
        "SELECT symbol, date, close, volume FROM daily_bars "
        "WHERE symbol = ANY(:s) AND date <= :d ORDER BY symbol, date",
        {"s": list(syms), "d": as_of})
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["symbol"], []).append(
            {"d": r["date"], "c": float(r["close"]), "v": r["volume"]})
    return out


def _fwd_return(series: list[dict], as_of: date, days: int) -> Optional[float]:
    """Return from close on/before as_of to close ~days ahead."""
    idx = next((i for i, b in enumerate(series) if b["d"] > as_of), None)
    if idx is None or idx == 0 or idx + days - 1 >= len(series):
        return None
    return series[min(idx + days, len(series) - 1)]["c"] / \
        series[idx - 1]["c"] - 1


def _tape(series: list[dict], spy: list[dict], as_of: date) -> dict:
    """RS vs SPY (60d/120d), vs SMA50/200, 52wk distance, volume trend —
    all from bars on/before as_of."""
    seg = [b for b in series if b["d"] <= as_of]
    spy_seg = [b for b in spy if b["d"] <= as_of]
    if len(seg) < 30 or len(spy_seg) < 30:
        return {}
    px = seg[-1]["c"]

    def ret(s: list[dict], n: int) -> Optional[float]:
        return s[-1]["c"] / s[-1 - n]["c"] - 1 if len(s) > n else None

    r60, s60 = ret(seg, 60), ret(spy_seg, 60)
    r120, s120 = ret(seg, 120), ret(spy_seg, 120)
    sma50 = sum(b["c"] for b in seg[-50:]) / min(50, len(seg))
    sma200 = (sum(b["c"] for b in seg[-200:]) / 200
              if len(seg) >= 200 else None)
    hi52 = max(b["c"] for b in seg[-252:])
    vol = seg[-1]["v"]; vavg = sum(b["v"] for b in seg[-20:]) / 20
    return {"px": px,
            "rs60": (r60 - s60) if r60 is not None and s60 is not None
                    else None,
            "rs120": (r120 - s120) if r120 is not None
                    and s120 is not None else None,
            "vs_sma50": px / sma50 - 1, "vs_sma200": (
                px / sma200 - 1) if sma200 else None,
            "sma50_200": (sma50 / sma200 - 1) if sma200 else None,
            "dd52w": px / hi52 - 1,
            "vol_ratio": vol / vavg if vavg else None}


def _growth_asof(sym: str, as_of: date) -> dict:
    """YoY growth + accel point-in-time. Prefers fundamental_quarterly
    (real revenue/margins; availability = filing_date — the SEC key).
    Falls back to earnings_data EPS history where the journal is thin.
    Availability rule: only rows filed/dated <= as_of may be seen."""
    from app.database import db
    rows = db.execute_query(
        "SELECT period_end, filing_date, revenue, gross_profit, "
        "net_income, eps_diluted, equity, free_cf, shares_diluted, "
        "total_debt, cash FROM fundamental_quarterly "
        "WHERE symbol = :s AND filing_date <= :d "
        "ORDER BY period_end DESC LIMIT 12",
        {"s": sym, "d": as_of})
    if len(rows) >= 5:
        return _growth_from_journal(rows)
    return _growth_from_earnings(db, sym, as_of)


def _yoy(rows: list, key: str, n: int = 4) -> list:
    """YoY series for `key`: q[i] vs q[i+4], positive-base only."""
    out = []
    for i in range(min(n, len(rows) - 4)):
        cur, yr = rows[i].get(key), rows[i + 4].get(key)
        if cur is None or yr is None:
            out.append(None)
            continue
        base = abs(float(yr))
        out.append(float(cur) / base - 1 if base > 0.01 else None)
    return out


def _accel(yoy: list) -> Optional[float]:
    """latest − mean(prior 2) — the spec's acceleration formula."""
    g = [x for x in yoy if x is not None]
    return g[0] - mean(g[1:3]) if len(g) >= 3 else None


def _growth_from_journal(rows: list) -> dict:
    """Full factor set from fundamental_quarterly — includes the
    quality leg the scanner proxies today: real ROE, FCF growth and
    margin, gross-margin level + slope, dilution, leverage."""
    e, r = _yoy(rows, "eps_diluted"), _yoy(rows, "revenue")
    geps = [x for x in e if x is not None]
    grev = [x for x in r if x is not None]
    out: dict[str, Any] = {}
    if geps:
        out["eps_growth"] = geps[0]
        out["eps_accel"] = _accel(e)
    if grev:
        out["rev_growth"] = grev[0]
        out["rev_accel"] = _accel(r)

    cur = rows[0]
    rev = cur.get("revenue")
    if rev:
        out["gm_now"] = (cur["gross_profit"] / rev
                         if cur.get("gross_profit") is not None
                         else None)
        out["fcf_margin"] = (cur["free_cf"] / rev
                             if cur.get("free_cf") is not None
                             else None)
    gm = [q["gross_profit"] / q["revenue"] for q in rows[:4]
          if q.get("gross_profit") is not None and q.get("revenue")]
    if len(gm) >= 4:
        out["gm_slope"] = gm[0] - mean(gm[1:4])
    fcf_yoy = _yoy(rows, "free_cf")
    gfc = [x for x in fcf_yoy if x is not None]
    if gfc:
        out["fcf_growth"] = gfc[0]
    ni_yoy = [x for x in _yoy(rows, "net_income") if x is not None]
    eq = [q["equity"] for q in rows[:5] if q.get("equity")]
    if ni_yoy and eq:
        # ROE ≈ (ttm net income proxy) / equity — quarterly NI ×4
        ni_ttm = sum(float(q["net_income"]) for q in rows[:4]
                     if q.get("net_income") is not None)
        out["roe"] = ni_ttm / mean(eq) if eq else None
    # dilution + leverage — the spec's soft hard-filters
    sh = [float(q["shares_diluted"]) for q in rows[:5]
          if q.get("shares_diluted")]
    if len(sh) >= 5 and sh[4] > 0:
        out["dilution_yoy"] = sh[0] / sh[4] - 1
    cur_debt, cur_cash = cur.get("total_debt"), cur.get("cash")
    if cur_debt is not None and cur.get("equity"):
        out["debt_to_equity"] = float(cur_debt) / float(cur["equity"])
    return out


def _growth_from_earnings(db, sym: str, as_of: date) -> dict:
    """Legacy path — earnings_data EPS only (revenue_actual never
    lands in that table). Kept for symbols the journal doesn't cover
    yet."""
    rows = db.execute_query(
        "SELECT earnings_date, eps_actual FROM earnings_data "
        "WHERE stock_symbol = :s AND earnings_date <= :d "
        "AND eps_actual IS NOT NULL "
        "ORDER BY earnings_date DESC LIMIT 12",
        {"s": sym, "d": as_of})
    if len(rows) < 5:
        return {}
    e = _yoy([{"eps": r["eps_actual"]} for r in rows], "eps")
    geps = [x for x in e if x is not None]
    return {"eps_growth": geps[0], "eps_accel": _accel(e)} if geps \
        else {}


def _replay_score(f: dict, t: dict) -> Optional[float]:
    """Mode-B composite over the factors replayable point-in-time."""
    def s100(x, lo, hi):
        return max(0.0, min(100.0, (x - lo) / (hi - lo) * 100)) \
            if x is not None else None

    # quality leg — now real ROE/FCF/margin once the journal fills
    q = [s100(f.get("roe"), 0, 0.30), s100(f.get("fcf_margin"), 0, 0.25),
         s100(f.get("fcf_growth"), 0, 0.50),
         s100(f.get("gm_now"), 0.20, 0.75)]
    q = [x for x in q if x is not None]
    parts = {
        "eps_growth": s100(f.get("eps_growth"), 0, 1.0),
        "rev_growth": s100(f.get("rev_growth"), 0, 0.6),
        "eps_accel": s100(f.get("eps_accel"), -0.5, 0.5),
        "rev_accel": s100(f.get("rev_accel"), -0.5, 0.5),
        "quality": mean(q) if q else None,
        "rel_strength": s100(
            t.get("rs120") or t.get("rs60"), -0.3, 0.5),
        "price_vol": (None if t.get("vs_sma50") is None
                      else s100(t["vs_sma50"], -0.2, 0.3)),
    }
    w = sum(REPLAY_FACTOR_W[k] for k, v in parts.items()
            if v is not None)
    if w < 0.5:                       # too many missing → unscored
        return None
    return sum(parts[k] * REPLAY_FACTOR_W[k] for k in parts
               if parts[k] is not None) / w


def replay(as_of: date) -> dict[str, Any]:
    """Score the universe on a historical date; grade with forward
    returns. Look-ahead rules: earnings need earnings_date<=as_of,
    bars need date<=as_of, estimate factors unavailable→excluded."""
    from app.database import db
    syms = [r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM symbol_flywheel")]
    # bars run ~2 horizons past as_of — _tape segments on/before the
    # date (no leak), _fwd_return grades after it
    all_bars = _bars(as_of + timedelta(days=120), syms + ["SPY"])
    spy = all_bars.pop("SPY", [])
    rows = []
    for sym in syms:
        t = _tape(all_bars.get(sym, []), spy, as_of)
        if not t:
            continue
        g = _growth_asof(sym, as_of)
        # mirror the live scanner's hard filters where the replayed
        # factors exist — missing factors pass (can't veto blind)
        if g.get("eps_growth") is not None and \
                g["eps_growth"] < REPLAY_HARD["eps_growth_min"]:
            continue
        if g.get("rev_growth") is not None and \
                g["rev_growth"] < REPLAY_HARD["rev_growth_min"]:
            continue
        if g.get("gm_now") is not None and \
                g["gm_now"] < REPLAY_HARD["gm_min"]:
            continue
        if g.get("dilution_yoy") is not None and \
                g["dilution_yoy"] > REPLAY_HARD["dilution_max"]:
            continue
        if g.get("debt_to_equity") is not None and \
                g["debt_to_equity"] > REPLAY_HARD["debt_to_equity_max"]:
            continue
        sc = _replay_score(g, t)
        if sc is None:
            continue
        row = {"symbol": sym, "score": round(sc, 1), **g, **t}
        for h in HORIZONS:
            fwd = _fwd_return(all_bars[sym], as_of, h)
            spy_fwd = _fwd_return(spy, as_of, h)
            row[f"fwd_{h}"] = fwd
            row[f"excess_{h}"] = (fwd - spy_fwd) if fwd is not None \
                and spy_fwd is not None else None
        rows.append(row)
    rows.sort(key=lambda r: -r["score"])
    return {"as_of": str(as_of), "scored": len(rows), "rows": rows}


def _bucket_stats(rows: list[dict]) -> list[dict]:
    """Hit-rate table by score band — the conviction calibration."""
    out = []
    for lo in range(50, 100, 10):
        band = [r for r in rows if lo <= r["score"] < lo + 10]
        if not band:
            continue
        e = {"band": f"{lo}–{lo+9}", "n": len(band)}
        for h in HORIZONS:
            xs = [r[f"excess_{h}"] for r in band
                  if r.get(f"excess_{h}") is not None]
            if xs:
                e[f"hit_{h}"] = round(sum(1 for x in xs if x > 0)
                                      / len(xs), 3)
                e[f"avg_excess_{h}"] = round(mean(xs), 4)
        out.append(e)
    return out


def run_replay(start: date, end: date, step_days: int = 20
               ) -> dict[str, Any]:
    """Walk the calendar at step_days; pooled bucket stats + a daily
    top-10 portfolio vs SPY. Never refits weights — ENGINE constants
    are frozen so the graded period stays out-of-sample."""
    all_rows, top_ports, d = [], [], start
    while d <= end:
        rep = replay(d)
        rs = rep["rows"]
        all_rows.extend(rs)
        top = rs[:10]
        ex20 = [r["excess_20"] for r in top
                if r.get("excess_20") is not None]
        if ex20:
            top_ports.append({"as_of": str(d), "n": len(ex20),
                              "avg_excess_20": round(mean(ex20), 4)})
        d += timedelta(days=step_days)
    return {"window": [str(start), str(end)],
            "replays": len(top_ports), "picks": len(all_rows),
            "bucket_stats": _bucket_stats(all_rows),
            "top10_excess_20d": round(
                mean(p["avg_excess_20"] for p in top_ports), 4)
            if top_ports else None,
            "factor_ic": _factor_ic(all_rows),
            "caveats": ["partial-factor score — estimate revisions & "
                        "FCF/quality excluded (no point-in-time data)",
                        "survivorship — universe = current flywheel "
                        "coverage, delisted names absent"]}


def _factor_ic(rows: list[dict]) -> dict:
    """Spearman-ish: median fwd excess of top-half vs bottom-half per
    factor — cheap, robust, and tells you which factors earn weight."""
    out = {}
    for fac in ("eps_growth", "rev_growth", "eps_accel", "rev_accel",
                "roe", "fcf_margin", "fcf_growth", "gm_now",
                "rs120", "vol_ratio"):
        vals = [(r[fac], r["excess_20"]) for r in rows
                if r.get(fac) is not None
                and r.get("excess_20") is not None]
        if len(vals) < 20:
            continue
        vals.sort(key=lambda x: x[0])
        mid = len(vals) // 2
        lo, hi = mean(v[1] for v in vals[:mid]), \
            mean(v[1] for v in vals[mid:])
        out[fac] = round(hi - lo, 4)
    return out


# ------------------------------------------------------------- MODE A
def grade_snapshots() -> dict[str, Any]:
    """Fill ret_20d/ret_60d/vs_spy_20d on matured snapshots — the
    honest forward backtest. Idempotent: only grades NULL rows."""
    from app.database import db
    pending = db.execute_query(
        "SELECT DISTINCT snap_date FROM hidden_gem_snapshots "
        "WHERE ret_20d IS NULL AND snap_date <= "
        " CURRENT_DATE - INTERVAL '30 days'")
    graded = 0
    for r in pending:
        as_of = r["snap_date"]
        snaps = db.execute_query(
            "SELECT symbol FROM hidden_gem_snapshots "
            "WHERE snap_date = :d", {"d": as_of})
        syms = [s["symbol"] for s in snaps]
        bars = _bars(as_of + timedelta(days=90), syms + ["SPY"])
        spy = bars.pop("SPY", [])
        for s in snaps:
            series = bars.get(s["symbol"])
            if not series:
                continue
            r20 = _fwd_return(series, as_of, 20)
            r60 = _fwd_return(series, as_of, 60)
            s20 = _fwd_return(spy, as_of, 20)
            db.execute_update(
                "UPDATE hidden_gem_snapshots SET ret_20d=:r, "
                "ret_60d=:r6, vs_spy_20d=:x WHERE snap_date=:d "
                "AND symbol=:s",
                {"d": as_of, "s": s["symbol"], "r": r20, "r6": r60,
                 "x": (r20 - s20) if r20 is not None
                      and s20 is not None else None})
            graded += 1
    return {"graded": graded, "dates": len(pending)}


def performance() -> dict[str, Any]:
    """Version-vs-version performance — 'how is the engine doing over
    the period'. Buckets graded snapshots by score band; later engines
    (gems_v2...) slot alongside v1."""
    from app.database import db
    rows = db.execute_query(
        "SELECT score, aligned, valuation, ret_20d, ret_60d, "
        "vs_spy_20d FROM hidden_gem_snapshots "
        "WHERE ret_20d IS NOT NULL")
    if not rows:
        return {"status": "no matured snapshots yet — shadow "
                "grading needs ~30 days of journal"}
    bands: dict[str, list] = {}
    for r in rows:
        band = f"{int(r['score'] // 10) * 10}s"
        bands.setdefault(band, []).append(r)
    out = []
    for band, rs in sorted(bands.items()):
        xs = [r["vs_spy_20d"] for r in rs
              if r["vs_spy_20d"] is not None]
        out.append({"band": band, "n": len(rs),
                    "hit20": round(sum(1 for x in xs if x > 0)
                                   / len(xs), 3) if xs else None,
                    "avg_excess20": round(mean(xs), 4) if xs else None,
                    "avg_ret20": round(mean(
                        r["ret_20d"] for r in rs
                        if r["ret_20d"] is not None), 4)})
    aligned = [r for r in rows if (r["aligned"] or 0) == 7]
    return {"graded_n": len(rows),
            "by_band": out,
            "full_alignment": {
                "n": len(aligned),
                "hit20": round(sum(
                    1 for r in aligned
                    if (r["vs_spy_20d"] or 0) > 0) / len(aligned), 3)
                if aligned else None}}
