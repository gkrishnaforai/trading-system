"""Hidden Gems — rules-based emerging-growth scanner.

Finds companies whose earnings, revenue, margins, estimates and tape
are improving together — the "fundamental alignment" pattern.

Every input is already computed by existing engines (DRY):
  symbol_flywheel  eps_growth/accel, rev_growth/accel, gm_now/slope,
                   est_revision_pct, beat_streak, gap_score, fwd_pe
  momentum_detail  rs_pct (universe-ranked), dd52w, vs_sma50/200,
                   dip phases, volume dip
  fmp_company_profiles / stocks  market cap, sector

Spec weights are journaled in each row's `parts` so the composite can
be refit once the daily snapshots accrue grading history.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

ENGINE_VERSION = "gems_v1"

# spec §7 — weights as data so a backtest can refit them later
W = {"eps_accel": .20, "rev_accel": .10, "eps_growth": .10,
     "rev_growth": .05, "revision": .20, "fcf_growth": .05,
     "fcf_margin": .05, "gross_margin": .05, "roe": .05,
     "balance_sheet": .05, "rel_strength": .05, "price_vol": .05}

UNIVERSE = {"mcap_min": 5e8, "mcap_max": 5e10, "price_min": 5.0}
HARD = {"eps_growth_min": 0.20, "rev_growth_min": 0.15,
        "revision_min": 0.0, "gm_min": 0.20}
# tape vetoes — a knife isn't "an early-stage winner coming out of a
# base", it's a falling knife; spec keeps momentum soft elsewhere
MOM_VETO = {"knife", "breakdown", "capitulation"}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _s100(x: Optional[float], lo: float, hi: float) -> Optional[float]:
    """Linear map x∈[lo,hi] → 0-100. None in → None out."""
    if x is None:
        return None
    return _clamp((x - lo) / (hi - lo) * 100)


def _universe() -> dict[str, dict]:
    """Flywheel-covered symbols = the curated growth universe; mcap +
    sector from fmp profiles / stocks, price from the latest bars."""
    from app.database import db
    fly = {r["symbol"]: dict(r) for r in db.execute_query(
        "SELECT * FROM symbol_flywheel")}
    if not fly:
        return {}
    prof = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, market_cap, sector, industry "
        "FROM fmp_company_profiles WHERE market_cap IS NOT NULL")}
    sm = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, market_cap, sector FROM stocks "
        "WHERE market_cap IS NOT NULL")}
    mom = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, momentum_state, momentum_detail FROM stocks "
        "WHERE momentum_state IS NOT NULL")}
    try:
        px = {r["symbol"]: float(r["close"]) for r in db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, close FROM daily_bars "
            "ORDER BY symbol, date DESC")}
    except Exception:
        px = {}
    out = {}
    for sym, f in fly.items():
        mcap = (prof.get(sym) or sm.get(sym) or {}).get("market_cap")
        out[sym] = {
            "fly": f,
            "mcap": float(mcap) if mcap else None,
            "sector": (prof.get(sym) or sm.get(sym) or {}).get("sector"),
            "price": px.get(sym),
            "mom": mom.get(sym) or {},
            "qual": _quality_asof(sym)}
    return out


def _quality_asof(sym: str) -> dict:
    """Real quality factors from the quarterly journal — ROE, FCF
    margin/growth, dilution, leverage. Returns {} until the backfill
    covers the symbol; scanner falls back to proxies then."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT revenue, gross_profit, net_income, eps_diluted, "
            "equity, free_cf, shares_diluted, total_debt, cash "
            "FROM fundamental_quarterly WHERE symbol = :s "
            "ORDER BY period_end DESC LIMIT 8", {"s": sym})
    except Exception:
        return {}
    if len(rows) < 5:
        return {}
    out: dict[str, float] = {}
    rev = rows[0].get("revenue")
    if rev:
        if rows[0].get("free_cf") is not None:
            out["fcf_margin"] = rows[0]["free_cf"] / rev
    ni_ttm = sum(float(q["net_income"]) for q in rows[:4]
                 if q.get("net_income") is not None)
    eqs = [float(q["equity"]) for q in rows[:5] if q.get("equity")]
    if ni_ttm and eqs:
        out["roe"] = ni_ttm / (sum(eqs) / len(eqs))
    if len(rows) >= 5:
        f0, f4 = rows[0].get("free_cf"), rows[4].get("free_cf")
        if f0 is not None and f4 is not None and abs(f4) > 1:
            out["fcf_growth"] = f0 / abs(f4) - 1
        s0, s4 = rows[0].get("shares_diluted"), \
            rows[4].get("shares_diluted")
        if s0 and s4:
            out["dilution_yoy"] = s0 / s4 - 1
        d, e = rows[0].get("total_debt"), rows[0].get("equity")
        if d is not None and e:
            out["debt_to_equity"] = d / e
    return out


def _hard_fail(u: dict) -> Optional[str]:
    f = u["fly"]
    eg, rg = f.get("eps_growth"), f.get("rev_growth")
    rv, gm = f.get("est_revision_pct"), f.get("gm_now")
    if eg is not None and eg < HARD["eps_growth_min"]:
        return f"eps growth {eg:.0%} < {HARD['eps_growth_min']:.0%}"
    if rg is not None and rg < HARD["rev_growth_min"]:
        return f"rev growth {rg:.0%} < {HARD['rev_growth_min']:.0%}"
    if rv is not None and rv < HARD["revision_min"]:
        return f"est revisions {rv:.0%} < 0"
    if gm is not None and gm < HARD["gm_min"]:
        return f"gross margin {gm:.0%} < 20%"
    if u.get("mcap") and not UNIVERSE["mcap_min"] <= u["mcap"] \
            <= UNIVERSE["mcap_max"]:
        return "mcap outside $500M–$50B"
    if u.get("price") and u["price"] < UNIVERSE["price_min"]:
        return "price < $5"
    q = u.get("qual") or {}
    # spec's soft hard-filters, now that the journal gives them teeth
    if q.get("dilution_yoy") is not None and q["dilution_yoy"] > 0.15:
        return f"dilution {q['dilution_yoy']:.0%}/yr — extreme"
    if q.get("debt_to_equity") is not None and \
            q["debt_to_equity"] > 3.0 and (q.get("roe") or 0) < 0:
        return "leveraged + unprofitable — balance-sheet red flag"
    if (u["mom"].get("momentum_state") or "") in MOM_VETO:
        return f"momentum {u['mom']['momentum_state']} — knife territory"
    return None


def _score(sym: str, u: dict) -> dict:
    """0-125 composite: core 100 in spec weights + gem bonus ≤25.
    Missing factors (ROE/FCF — no ratios feed yet) fall back to the
    closest populated proxy and are marked in `proxies`."""
    f, det = u["fly"], (u["mom"].get("momentum_detail") or {})
    if isinstance(det, str):
        det = json.loads(det)
    proxies = []

    # acceleration — the spec's signature factor, already computed
    eps_acc = _s100(f.get("eps_accel"), -0.5, 0.5)
    rev_acc = _s100(f.get("rev_accel"), -0.5, 0.5)
    eps_gw = _s100(f.get("eps_growth"), 0.0, 1.0)
    rev_gw = _s100(f.get("rev_growth"), 0.0, 0.60)
    revision = _s100(f.get("est_revision_pct"), -0.10, 0.40)

    # quality leg — real ROE/FCF/dilution/leverage where the journal
    # covers the symbol; proxy fallback marks itself in `proxies`
    q = u.get("qual") or {}
    gm = _s100(f.get("gm_now"), 0.20, 0.75)
    gm_slope = f.get("gm_slope")
    roe = _s100(q.get("roe"), 0, 0.30)
    if roe is None:
        roe = _s100(f.get("beat_streak"), 0, 6)
        if roe is not None:
            proxies.append("roe→beat_streak")
    fcf_g = _s100(q.get("fcf_growth"), 0, 0.50)
    fcf_m = _s100(q.get("fcf_margin"), 0, 0.25)
    if fcf_g is None and fcf_m is None:
        fcf_g = _s100(gm_slope, -0.15, 0.15)
        fcf_m = gm
        if fcf_m is not None:
            proxies.append("fcf→gross-margin structure")
    bal = (_s100(-q["debt_to_equity"], -3.0, 0)
           if q.get("debt_to_equity") is not None else
           _s100(f.get("beat_streak"), 0, 6))
    if q.get("debt_to_equity") is None and bal is not None:
        proxies.append("balance→beat_streak")

    rs = _s100(det.get("rs_pct"), 0, 100) or det.get("rs_pct")
    price_vol = None
    vs50, vs200 = det.get("vs_sma50"), det.get("vs_sma200")
    if vs50 is not None or vs200 is not None:
        pv = 50.0
        pv += 15 if (vs50 or 0) > 0 else -15
        pv += 15 if (vs200 or 0) > 0 else -15
        vd = det.get("vol_dip")
        if vd is not None:
            pv += _clamp((vd - 1) * 40, -10, 20)
        price_vol = _clamp(pv)

    parts_raw = {"eps_accel": eps_acc, "rev_accel": rev_acc,
                 "eps_growth": eps_gw, "rev_growth": rev_gw,
                 "revision": revision, "fcf_growth": fcf_g,
                 "fcf_margin": fcf_m, "gross_margin": gm,
                 "roe": roe, "balance_sheet": bal,
                 "rel_strength": rs, "price_vol": price_vol}
    # missing part → redistribute its weight across populated factors
    avail_w = sum(W[k] for k, v in parts_raw.items() if v is not None)
    core = (sum(parts_raw[k] * W[k] for k in parts_raw
                if parts_raw[k] is not None)
            / avail_w if avail_w else 0)

    # hidden-gem bonus ≤25
    bonus, bonus_why = 0, []
    if u.get("mcap") and u["mcap"] < 1e10:
        bonus += 5; bonus_why.append("mcap<$10B")
    if (f.get("eps_accel") or 0) > 0 and (f.get("eps_growth") or 0) > 0.4:
        bonus += 5; bonus_why.append("EPS accelerating")
    if (f.get("est_revision_pct") or 0) > 0.10:
        bonus += 5; bonus_why.append("post-print revisions ↑")
    if (f.get("rev_accel") or 0) > 0 and (gm_slope or 0) > 0:
        bonus += 5; bonus_why.append("rev accel + margin expansion")
    dd = det.get("dd52w")
    if dd is not None and dd > -0.10 and (det.get("rs_pct") or 0) >= 90:
        bonus += 5; bonus_why.append("≤10% off high + RS≥90")

    # fundamental alignment — the 7-arrow flag (FCF leg proxied by
    # margin structure until the cash-flow feed lands)
    arrows = {
        "revenue": (f.get("rev_growth") or 0) > 0.15,
        "eps": (f.get("eps_growth") or 0) > 0.20,
        "margins": (gm_slope or 0) > 0,
        "fcf/margin": (f.get("gm_now") or 0) > 0.40,
        "estimates": (f.get("est_revision_pct") or 0) > 0,
        "price": (vs50 or 0) > 0 and (vs200 or 0) > 0,
        "volume": (det.get("vol_dip") or 1) > 1.1,
    }
    aligned = sum(arrows.values())

    # valuation — separate bucket, never dominates (spec §10)
    pe = f.get("fwd_pe")
    val = ("extreme" if pe and pe > 60 else
           "elevated" if pe and pe > 35 else
           "reasonable" if pe else "unknown")

    return {"symbol": sym, "core": round(core, 1),
            "bonus": bonus, "bonus_why": bonus_why,
            "final": round(core + bonus, 1),
            "parts": {k: round(v, 1) if v is not None else None
                      for k, v in parts_raw.items()},
            "arrows": arrows, "aligned": aligned,
            "full_alignment": aligned == 7,
            "valuation": val, "fwd_pe": pe,
            "momentum": u["mom"].get("momentum_state"),
            "proxies": proxies,
            "mcap": u.get("mcap"), "sector": u.get("sector"),
            "rs_pct": det.get("rs_pct"), "dd52w": det.get("dd52w")}


def scan() -> dict[str, Any]:
    uni = _universe()
    rows, filtered = [], {}
    for sym, u in uni.items():
        fail = _hard_fail(u)
        if fail:
            filtered[sym] = fail
            continue
        rows.append(_score(sym, u))
    rows.sort(key=lambda r: -r["final"])
    top = rows[:25]
    return {"as_of": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "engine_version": ENGINE_VERSION,
            "weights": W, "hard_filters": HARD, "universe_spec": UNIVERSE,
            "universe_n": len(uni), "passed": len(rows),
            "filtered_n": len(filtered),
            "aligned": [r["symbol"] for r in rows if r["full_alignment"]],
            "rows": top, "filtered_sample": dict(list(filtered.items())[:20])}


def journal(payload: dict) -> None:
    """Daily journal → the change column (NEW/↑/↓/REMOVED) and the
    backtest substrate both come from this table."""
    from app.database import db
    today = date.today().isoformat()
    for r in payload.get("rows") or []:
        db.execute_update(
            "INSERT INTO hidden_gem_snapshots "
            "(snap_date, symbol, engine_version, score, core, bonus, "
            " aligned, valuation, momentum, parts) VALUES "
            "(:d,:s,:ev,:sc,:c,:b,:a,:v,:m,CAST(:p AS jsonb)) "
            "ON CONFLICT (snap_date, symbol) DO UPDATE SET "
            "engine_version=:ev, score=:sc, core=:c, bonus=:b, "
            "aligned=:a, valuation=:v, momentum=:m, "
            "parts=CAST(:p AS jsonb)",
            {"d": today, "s": r["symbol"], "ev": ENGINE_VERSION,
             "sc": r["final"], "c": r["core"], "b": r["bonus"],
             "a": r["aligned"], "v": r["valuation"],
             "m": r["momentum"],
             "p": json.dumps(r["parts"], default=str)})


def changes(rows: list[dict]) -> dict[str, list]:
    """Today vs yesterday — spec §11's change column."""
    from app.database import db
    try:
        prev = {r["symbol"]: float(r["score"]) for r in db.execute_query(
            "SELECT symbol, score FROM hidden_gem_snapshots "
            "WHERE snap_date = (SELECT max(snap_date) FROM "
            " hidden_gem_snapshots WHERE snap_date < CURRENT_DATE)")}
    except Exception:
        return {}
    today = {r["symbol"]: r["final"] for r in rows}
    new = [s for s in today if s not in prev]
    moved = [(s, today[s] - prev[s]) for s in today if s in prev]
    up = sorted([m for m in moved if m[1] >= 5], key=lambda x: -x[1])
    down = sorted([m for m in moved if m[1] <= -5], key=lambda x: x[1])
    removed = [s for s in prev if s not in today]
    return {"new": new, "improving": up, "falling": down,
            "removed": removed}


def run() -> dict[str, Any]:
    payload = scan()
    payload["changes"] = changes(payload.get("rows") or [])
    journal(payload)
    return payload
