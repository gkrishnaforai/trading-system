"""Growth-quality composite — separates structural growers from
cyclical peaks and manufactured EPS.

Why this exists: a single growth number (revenue OR EPS) is gameable.
Revenue alone rewards unprofitable share-buying; EPS alone rewards
buybacks and margin games; high growth in a cyclical is often a *sell*
signal, not a buy signal. The composite asks four independent questions:

    growth_slope      — is growth ACCELERATING? (level AND delta)
    earnings_quality  — is the growth cash-backed and per-share real?
    revision_momentum — is the street raising the forward curve?
    structural_proof  — has this persisted, is it cycle-independent?

Each component scores 0-100 on deterministic, versioned scales; the
composite is a weighted blend — percentile-ranked across the tracked
universe, never absolute-cutoff (cutoffs break across macro regimes).

Weights (versioned): slope 30 / quality 20 / revisions 25 / structural 25.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MODEL_VERSION = "growth_quality.v1"
W = {"slope": 0.30, "quality": 0.20, "revisions": 0.25, "structural": 0.25}
# hard gates: below these the growth is either fake or uninvestable
GATE_MIN_YEARS_DATA = 2          # need at least 2 fiscal years to score slope
GATE_MAX_DILUTION = 0.03         # >3%/yr share growth dents per-share returns


def _f(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _lin(v: Optional[float], lo: float, hi: float) -> Optional[float]:
    """Linear 0-100 scale: v<=lo → 0, v>=hi → 100."""
    if v is None:
        return None
    return _clip((v - lo) / (hi - lo) * 100)


def _weighted_momentum(vals: List[Optional[float]]) -> Optional[float]:
    """0.5(G0-G1)+0.3(G1-G2)+0.2(G2-G3) — direction AND persistence,
    not just the latest step. One accelerated quarter ≠ a trend."""
    v = [x for x in vals if x is not None][-4:]
    # diffs carry their own weights — dropping a base-effect pair
    # (earlier level off a ~zero base, e.g. +437%→+2350%) must not
    # promote an older diff into the 0.5 slot. And at triple-digit
    # growth a negative diff is normalization, not deterioration —
    # NBIS +621%→+454% is "−167pts" arithmetically but not a slowing
    # business; clamp that pair to neutral rather than discarding it
    pairs = []
    for i, w in zip(range(len(v) - 1, 0, -1), (0.5, 0.3, 0.2)):
        if abs(v[i - 1]) > 2.0:
            continue
        d = v[i] - v[i - 1]
        pairs.append((0.0 if (v[i] > 1.0 and d < 0) else d, w))
    if not pairs:
        return None
    ws = sum(w for _, w in pairs)
    return sum(d * w for d, w in pairs) / ws


def _level_relative_delta(cur: Optional[float], prev: Optional[float]
                          ) -> Optional[float]:
    """Single-period accel with the same two guards: prior level off
    a ~zero base → noise (None); triple-digit level decelerating →
    normalization (0), not deterioration."""
    if cur is None or prev is None:
        return None
    if cur > 1.0 and cur < prev:
        return 0.0                       # hypergrowth normalization
    if abs(prev) > 2.0:
        return None                      # ~zero base → unmeasurable
    return cur - prev


def _growth_series(sym: str) -> List[Dict[str, Any]]:
    """Per-fiscal-year growth rows, oldest→newest."""
    from app.database import db
    rows = db.execute_query(
        """SELECT payload->'income_statement_growth' g
           FROM stock_insights_snapshots
           WHERE stock_symbol=:s AND source='fmp_income_statement_growth'
           ORDER BY generated_at""", {"s": sym})
    out = []
    for r in rows:
        g = r["g"] if isinstance(r["g"], dict) else json.loads(r["g"])
        out.append(g)
    return out


def _fcf_growth_latest(sym: str) -> Optional[float]:
    from app.database import db
    r = db.execute_query(
        """SELECT payload->'cash_flow_growth'->>'growthFreeCashFlow' v
           FROM stock_insights_snapshots
           WHERE stock_symbol=:s AND source='fmp_cash_flow_growth'
           ORDER BY generated_at DESC LIMIT 1""", {"s": sym})
    return _f(r[0]["v"]) if r else None


def _fundamentals(sym: str) -> Dict[str, Any]:
    from app.database import db
    r = db.execute_query(
        """SELECT payload->'fundamentals' f FROM stock_insights_snapshots
           WHERE stock_symbol=:s AND source='fmp_fundamentals'
           ORDER BY generated_at DESC LIMIT 1""", {"s": sym})
    if not r:
        return {}
    f = r[0]["f"]
    return f if isinstance(f, dict) else json.loads(f)


def _estimate_revisions(sym: str, as_of: date) -> Dict[str, Any]:
    """Same-period eps_avg change across snapshot history — the revision
    signal. History is young (curve capture started recently); thin
    windows are flagged, not faked."""
    from app.database import db
    rows = db.execute_query(
        """SELECT period_end, eps_avg, num_analysts, as_of
           FROM symbol_estimate_snapshots
           WHERE symbol=:s AND as_of <= :a
           ORDER BY period_end, as_of""", {"s": sym, "a": as_of})
    by_period: Dict[Any, list] = {}
    for r in rows:
        by_period.setdefault(r["period_end"], []).append(r)
    deltas, breadth_up, breadth_total, analysts = [], 0, 0, []
    for pe, hist in by_period.items():
        eps = [(h["as_of"], _f(h["eps_avg"])) for h in hist if _f(h["eps_avg"])]
        if len(eps) >= 2:
            first, last = eps[0][1], eps[-1][1]
            if first and abs(first) > 1e-6:
                d = (last - first) / abs(first)
                deltas.append(d)
                breadth_total += 1          # only computable periods count
                if d > 0:
                    breadth_up += 1
        if hist and _f(hist[-1]["num_analysts"]):
            analysts.append(_f(hist[-1]["num_analysts"]))
    return {"deltas": deltas,
            "mean_delta": sum(deltas) / len(deltas) if deltas else None,
            "breadth_up": breadth_up, "breadth_total": breadth_total,
            "analysts": max(analysts) if analysts else None,
            "periods": len(by_period)}


def _margin_trend(sym: str) -> Optional[float]:
    """Gross-margin trajectory, latest minus oldest in stored series."""
    from app.database import db
    rows = db.execute_query(
        """SELECT gross_profit_margin m FROM financial_ratios
           WHERE symbol=:s AND gross_profit_margin IS NOT NULL
           ORDER BY fiscal_date_ending DESC LIMIT 5""", {"s": sym})
    ms = [_f(r["m"]) for r in rows if _f(r["m"]) is not None]
    return ms[0] - ms[-1] if len(ms) >= 2 else None


def _lt_curve_exists(sym: str, as_of: date) -> Optional[int]:
    from app.database import db
    r = db.execute_query(
        "SELECT MAX(period_end) p FROM symbol_estimate_snapshots WHERE symbol=:s",
        {"s": sym})
    if not r or not r[0]["p"]:
        return None
    return (r[0]["p"] - as_of).days


def _tailwind_evidence(sym: str) -> int:
    from app.database import db
    r = db.execute_query(
        "SELECT count(*) c FROM tailwinds WHERE symbol=:s AND status='active' "
        "AND direction='tailwind'", {"s": sym})
    return int(r[0]["c"]) if r else 0


def compute_growth_quality(sym: str, as_of: Optional[date] = None) -> Dict[str, Any]:
    """Deterministic composite. Missing inputs degrade gracefully with
    flags — a name can score on 3 of 4 components but says so."""
    sym = sym.upper()
    as_of = as_of or date.today()
    flags: List[str] = []

    # ---------- growth_slope (30%) — level AND acceleration ----------
    gs = _growth_series(sym)
    rev_gs = [_f(g.get("growthRevenue")) for g in gs]
    eps_gs = [_f(g.get("growthEPSDiluted")) or _f(g.get("growthEPS")) for g in gs]
    dil = [_f(g.get("growthWeightedAverageShsOutDil")) or
           _f(g.get("growthWeightedAverageShsOut")) for g in gs]
    rev_g, eps_g = rev_gs[-1] if rev_gs else None, eps_gs[-1] if eps_gs else None
    rev_accel = (_level_relative_delta(rev_gs[-1], rev_gs[-2])
                 if len(rev_gs) >= 2 else None)
    eps_accel = (_level_relative_delta(eps_gs[-1], eps_gs[-2])
                 if len(eps_gs) >= 2 else None)
    # multi-period trajectory — weighted delta over up to 4 periods;
    # falls back to the single-period accel when history is thin
    rev_mom = _weighted_momentum(rev_gs)
    eps_mom = _weighted_momentum(eps_gs)
    rev_dir = rev_mom if rev_mom is not None else rev_accel
    eps_dir = eps_mom if eps_mom is not None else eps_accel
    # earnings operating leverage — EPS accelerating faster than
    # revenue means incremental revenue converts disproportionately
    op_lev = (eps_dir - rev_dir
              if eps_dir is not None and rev_dir is not None else None)
    if op_lev is not None:
        if op_lev > 0.05:
            flags.append("operating_leverage")
        elif op_lev < -0.05:
            flags.append("earnings_lagging_revenue")
    if len(gs) < GATE_MIN_YEARS_DATA:
        flags.append("thin_history")
    level = None
    if rev_g is not None or eps_g is not None:
        parts = [x for x in (_lin(rev_g, 0, 0.40), _lin(eps_g, 0, 0.50)) if x is not None]
        level = sum(parts) / len(parts) if parts else None
    slope = None
    if rev_dir is not None or eps_dir is not None or op_lev is not None:
        parts = [x for x in (_lin(rev_dir, -0.15, 0.15),
                             _lin(eps_dir, -0.20, 0.20),
                             _lin(op_lev, -0.15, 0.15)) if x is not None]
        slope = sum(parts) / len(parts) if parts else None
    slope_score = None
    if level is not None and slope is not None:
        slope_score = _clip(0.45 * level + 0.55 * slope)
    elif level is not None:
        slope_score = level
        flags.append("no_slope_data")

    # ---------- earnings_quality (20%) ----------
    fund = _fundamentals(sym)
    fcf, ni = _f(fund.get("free_cash_flow")), _f(fund.get("net_income"))
    fcf_g = _fcf_growth_latest(sym)
    dil_latest = dil[-1] if dil else None
    conv = (fcf / ni) if (fcf and ni and ni != 0) else None
    eq_parts = []
    if fcf is not None:
        eq_parts.append(100.0 if fcf > 0 else 10.0)
        if fcf <= 0:
            flags.append("fcf_negative")
    if fcf_g is not None:
        eq_parts.append(_lin(fcf_g, -0.25, 0.50))
    if conv is not None:
        eq_parts.append(_lin(conv, 0.0, 1.3))
    if dil_latest is not None:
        dil_score = _lin(-dil_latest, -GATE_MAX_DILUTION, 0.0)
        eq_parts.append(dil_score if dil_score is not None else 50.0)
        if dil_latest > GATE_MAX_DILUTION:
            flags.append("dilutive")
    quality_score = _clip(sum(eq_parts) / len(eq_parts)) if eq_parts else None

    # ---------- revision_momentum (25%) ----------
    rev = _estimate_revisions(sym, as_of)
    rm_parts = []
    if rev["mean_delta"] is not None:
        rm_parts.append(_lin(rev["mean_delta"], -0.08, 0.15))
    if rev["breadth_total"]:
        rm_parts.append(_lin(rev["breadth_up"] / rev["breadth_total"], 0, 1))
    if rev["analysts"]:
        rm_parts.append(_lin(rev["analysts"], 0, 15))  # coverage = signal reliability
    revisions_score = _clip(sum(rm_parts) / len(rm_parts)) if rm_parts else None
    if rev["breadth_total"] < 2:
        flags.append("revision_history_thin")

    # ---------- structural_proof (25%) ----------
    rev_cagr = None
    rg_valid = [x for x in rev_gs if x is not None]
    if len(rg_valid) >= 3:
        prod = 1.0
        for g in rg_valid[-3:]:
            prod *= (1 + g)
        rev_cagr = prod ** (1 / 3) - 1
    durable = sum(1 for x in rg_valid[-3:] if x > 0) if rg_valid else 0
    marg = _margin_trend(sym)
    lt_days = _lt_curve_exists(sym, as_of)
    tw = _tailwind_evidence(sym)
    cyc = _cyclical_flag(sym)
    lev = _flywheel_legs(sym)
    nde = lev.get("net_debt_ebitda")
    bq = _business_quality(lev)
    tr = lev.get("surprise_trend")
    if tr is not None:
        if tr < -5:
            flags.append("beats_shrinking")
        elif tr > 5:
            flags.append("beats_growing")
    st_parts = []
    if rev_cagr is not None:
        st_parts.append(_lin(rev_cagr, 0, 0.25))
    st_parts.append(_lin(durable, 0, 3))
    if marg is not None:
        st_parts.append(_lin(marg, -0.04, 0.04))
    if lt_days is not None:
        st_parts.append(_lin(lt_days, 180, 1500))   # 18mo+ curve = duration belief
    st_parts.append(_lin(tw, 0, 3))                  # tailwind channels exist
    # capex efficiency — only for genuinely capital-intensive names
    # (capex/rev >25%): does each $1 of buildout convert to new gross
    # profit? NBIS's +454% on $20B+ capex is judged by this, not FCF
    ce, cr = lev.get("capex_eff"), lev.get("capex_rev")
    if cr is not None and cr > 0.25 and ce is not None:
        st_parts.append(_lin(ce, -0.2, 0.6))
        flags.append("capex_productive" if ce > 0.3
                     else "capex_hungry" if ce < 0 else "capex_heavy")
    structural_score = _clip(sum(st_parts) / len(st_parts)) if st_parts else None
    if cyc is True:
        structural_score = (structural_score or 50) * 0.7   # cyclical discount
        flags.append("cyclical")
    # leverage — a heavily-indebted balance sheet discounts the
    # durability of everything else (TLN ~11.8x on restructured debt)
    if nde is not None and nde > 3.5:
        structural_score = (structural_score or 50) * (
            0.8 if nde <= 6 else 0.65)
        flags.append("leverage_high" if nde <= 6
                     else "leverage_extreme")

    # ---------- composite ----------
    comps = {"growth_slope": slope_score, "earnings_quality": quality_score,
             "revision_momentum": revisions_score, "structural_proof": structural_score}
    weights = {"growth_slope": W["slope"], "earnings_quality": W["quality"],
               "revision_momentum": W["revisions"], "structural_proof": W["structural"]}
    scored = {k: v for k, v in comps.items() if v is not None}
    if scored:
        wsum = sum(weights[k] for k in scored)
        composite = _clip(sum(comps[k] * weights[k] for k in scored) / wsum)
    else:
        composite = None
        flags.append("no_data")

    return {
        "symbol": sym, "as_of": as_of.isoformat(), "model_version": MODEL_VERSION,
        "score": round(composite, 1) if composite is not None else None,
        "components": {k: round(v, 1) if v is not None else None for k, v in comps.items()},
        "detail": {
            "rev_g_latest": rev_g, "rev_g_prev": rev_gs[-2] if len(rev_gs) >= 2 else None,
            "rev_accel": rev_accel, "eps_g_latest": eps_g, "eps_accel": eps_accel,
            "rev_momentum": rev_mom, "eps_momentum": eps_mom,
            "operating_leverage": op_lev,
            "surprise_trend": tr, "roic": lev.get("roic"),
            "roe": lev.get("roe"),
            "rev_breadth_30d": lev.get("rev_breadth_30d"),
            "business_quality": round(bq, 1) if bq is not None else None,
            "capex_eff": ce, "capex_rev": cr,
            "rev_cagr_3y": rev_cagr, "fcf": fcf, "fcf_growth": fcf_g,
            "fcf_conversion": conv, "dilution": dil_latest,
            "rev_mean_delta": rev["mean_delta"],
            "rev_breadth": f"{rev['breadth_up']}/{rev['breadth_total']}",
            "analysts": rev["analysts"], "margin_trend": marg,
            "lt_curve_days": lt_days, "tailwinds": tw, "cyclical": cyc,
            "net_debt_ebitda": nde,
            "debt_to_equity": lev.get("debt_to_equity"),
            "fy_count": len(gs),
        },
        "flags": flags,
        "business_quality": round(bq, 1) if bq is not None else None,
    }


_CYCLICAL_SECTORS = {"Energy", "Utilities", "Materials"}


def _cyclical_flag(sym: str) -> Optional[bool]:
    """Curated stocks.cyclical wins; when unset, sector is the default
    — merchant energy/utility/materials names are price-takers on a
    commodity cycle whether they've been tagged or not."""
    from app.database import db
    r = db.execute_query(
        "SELECT cyclical, sector FROM stocks WHERE symbol=:s",
        {"s": sym})
    if not r:
        return None
    if r[0]["cyclical"] is not None:
        return bool(r[0]["cyclical"])
    if (r[0].get("sector") or "") in _CYCLICAL_SECTORS:
        return True
    return None


def _flywheel_legs(sym: str) -> dict:
    """Flywheel-persisted balance-sheet + trajectory legs — leverage
    (the TLN gap), ROIC/ROE (business quality), surprise trend."""
    from app.database import db
    r = db.execute_query(
        "SELECT net_debt_ebitda, debt_to_equity, surprise_trend,"
        " rev_breadth_30d, roic, roe, capex_eff, capex_rev "
        "FROM symbol_flywheel "
        "WHERE symbol=:s", {"s": sym})
    return r[0] if r else {}


def _business_quality(lev: dict) -> Optional[float]:
    """Standalone BQ — 'what IS this company' — deliberately OUT of
    the growth composite: a great trajectory on a leveraged,
    low-return business is not a great business (the TLN split).
    ROIC is the anchor; ROE and balance-sheet cleanliness support."""
    parts = [x for x in (
        _lin(lev.get("roic"), -0.05, 0.20),      # cost-of-capital ≈ 50
        _lin(lev.get("roe"), -0.10, 0.30),
        _lin(-lev["net_debt_ebitda"], -8, 0)
        if lev.get("net_debt_ebitda") is not None else None,
    ) if x is not None]
    return _clip(sum(parts) / len(parts)) if parts else None


def journal_run(res: Dict[str, Any]) -> None:
    """Append-only journal — same inputs today → skip."""
    from app.database import db
    payload = {k: res["detail"].get(k) for k in
               ("rev_g_latest", "eps_g_latest", "fcf", "fcf_conversion",
                "rev_mean_delta", "lt_curve_days", "fy_count")}
    ih = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    try:
        dup = db.execute_query(
            "SELECT 1 FROM growth_quality_runs WHERE symbol=:s AND as_of=:a "
            "AND inputs_hash=:h LIMIT 1",
            {"s": res["symbol"], "a": res["as_of"], "h": ih})
        if dup:
            return
        db.execute_query(
            """INSERT INTO growth_quality_runs
              (symbol, as_of, score, components, detail, flags, inputs_hash, model_version)
            VALUES (:s,:a,:sc,CAST(:c AS jsonb),CAST(:d AS jsonb),
                    CAST(:f AS jsonb),:h,:mv)""",
            {"s": res["symbol"], "a": res["as_of"], "sc": res.get("score"),
             "c": json.dumps(res.get("components")), "d": json.dumps(res.get("detail")),
             "f": json.dumps(res.get("flags")), "h": ih, "mv": res.get("model_version")})
    except Exception as exc:
        logger.debug("growth_quality journal %s failed: %s", res.get("symbol"), exc)


def run_universe(symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Score the tracked universe and return percentile-ranked results.
    Percentiles are what the UI shows — ranking beats cutoffs."""
    from app.database import db
    if symbols is None:
        rows = db.execute_query(
            """SELECT DISTINCT symbol FROM (
                 SELECT symbol FROM portfolio_holdings WHERE status<>'sold'
                 UNION
                 SELECT s.symbol FROM watchlist_stocks ws
                   JOIN stocks s ON s.id=ws.stock_id) t""")
        symbols = [r["symbol"] for r in rows]
    results = []
    for s in symbols:
        try:
            r = compute_growth_quality(s)
            journal_run(r)
            results.append(r)
        except Exception as exc:
            logger.debug("growth_quality %s: %s", s, exc)
    scored = sorted([r for r in results if r.get("score") is not None],
                    key=lambda r: r["score"])
    n = len(scored)
    for i, r in enumerate(scored):
        r["percentile"] = round((i + 0.5) / n * 100, 1) if n else None
        db.execute_query(
            "UPDATE growth_quality_runs SET percentile=:p "
            "WHERE symbol=:s AND as_of=:a AND percentile IS NULL",
            {"p": r["percentile"], "s": r["symbol"], "a": r["as_of"]})
    return results


def card_for(sym: str) -> Optional[Dict[str, Any]]:
    """Latest journaled run for the Stock page."""
    from app.database import db
    r = db.execute_query(
        """SELECT score, components, detail, flags, percentile, as_of
           FROM growth_quality_runs WHERE symbol=:s
           ORDER BY as_of DESC, id DESC LIMIT 1""", {"s": sym.upper()})
    return dict(r[0]) if r else None
