"""Theme composition — cross-sectional member comparison inside a
theme. The review framework made concrete: same metrics side by
side, ranked, so 'of these 8 names, which two do I add' is a
deterministic answer not a narrative.

Columns: spot, fwd P/E, PEG (fwd pe / fwd growth), FY+2 growth,
backlog growth, FCF, lifecycle stage, FV upside, confidence.
Composite rank: growth + fv upside + estimate quality; thin-data
members sink rather than inventing numbers."""

from __future__ import annotations

from typing import Any, Dict, List

from app.database import db


def _latest_fv(syms: List[str]) -> Dict[str, dict]:
    rows = db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, expected_fair_value,"
        " fair_value, decision"
        " FROM fair_value_v2_runs WHERE symbol = ANY(:s)"
        " ORDER BY symbol, run_ts DESC", {"s": syms})
    return {r["symbol"]: r for r in rows}


def composition(theme_key: str) -> Dict[str, Any]:
    from app.signals.future_themes import registry
    reg = registry(include_candidates=False)
    t = reg.get(theme_key)
    if not t:
        return {"error": f"theme '{theme_key}' not found"}
    members = t.get("members") or {}
    syms = list(members.keys())
    if not syms:
        return {"theme": theme_key, "name": t.get("name"), "rows": []}

    fly = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, fwd_eps_avg, eps_ttm, est_revision_pct,"
        " num_analysts FROM symbol_flywheel WHERE symbol = ANY(:s)",
        {"s": syms})}
    spot = {r["symbol"]: float(r["close"]) for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, close FROM daily_bars"
        " WHERE symbol = ANY(:s) ORDER BY symbol, date DESC",
        {"s": syms})}
    fv = _latest_fv(syms)
    fy2 = {r["symbol"]: float(r["eps_avg"]) for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, eps_avg"
        " FROM symbol_estimate_snapshots WHERE symbol = ANY(:s)"
        " AND period_end > CURRENT_DATE + INTERVAL '18 months'"
        " AND eps_avg IS NOT NULL ORDER BY symbol, as_of DESC",
        {"s": syms})}
    bkl = {r["symbol"]: r for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, backlog_yoy,"
        " book_to_bill FROM backlog_conversion"
        " WHERE symbol = ANY(:s) ORDER BY symbol, as_of DESC",
        {"s": syms})}
    fin = {r["symbol"]: r for r in db.execute_query(
        "SELECT DISTINCT ON (stock_symbol) stock_symbol,"
        " free_cash_flow_ttm, market_cap"
        " FROM stock_financials WHERE stock_symbol = ANY(:s)"
        " ORDER BY stock_symbol, as_of_date DESC", {"s": syms})}

    rows: List[Dict[str, Any]] = []
    for s in syms:
        f = fly.get(s) or {}
        sp = spot.get(s)
        fe = (f.get("fwd_eps_avg") or None)
        fe = float(fe) if fe else None
        fwd_pe = round(sp / fe, 1) if sp and fe and fe > 0 else None
        fg = (fe / float(f["eps_ttm"]) - 1) if (
            fe and f.get("eps_ttm") and float(f["eps_ttm"]) > 0) else None
        peg = round(fwd_pe / (fg * 100), 2) if (
            fwd_pe and fg and 0 < fg <= 0.6) else None
        fy2g = (fy2.get(s) / fe - 1) if (fy2.get(s) and fe) else None
        v = fv.get(s) or {}
        exp = v.get("expected_fair_value") or v.get("fair_value")
        exp = float(exp) if exp else None
        up = round((exp / sp - 1) * 100, 1) if exp and sp else None
        dec = (v.get("decision") or {})
        life = ((dec.get("lifecycle") or {}).get("stage"))
        rows.append({
            "symbol": s,
            "role": members.get(s),
            "spot": sp,
            "fwd_pe": fwd_pe,
            "peg": peg,
            "fy2_growth_pct": round(fy2g * 100, 1) if fy2g else None,
            "backlog_yoy_pct": bkl.get(s, {}).get("backlog_yoy"),
            "book_to_bill": bkl.get(s, {}).get("book_to_bill"),
            "fcf_ttm": (fin.get(s) or {}).get("free_cash_flow_ttm"),
            "lifecycle": life,
            "fv_expected": round(exp, 2) if exp else None,
            "fv_upside_pct": up,
            "confidence": dec.get("valuation_confidence"),
            "analysts": f.get("num_analysts"),
        })

    # rank: growth + FV upside + coverage; missing data sinks the name
    def _score(r):
        g = r["fy2_growth_pct"] or 0
        u = r["fv_upside_pct"] or 0
        cov = 5 if (r["analysts"] or 0) >= 5 else -10
        conf = {"high": 10, "medium": 4}.get(r["confidence"], 0)
        return g * 0.4 + u * 0.4 + cov + conf

    for r in rows:
        r["score"] = round(_score(r), 1)
    rows.sort(key=lambda r: (r["score"] or -999), reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return {"theme": theme_key, "name": t.get("name"),
            "members": len(rows), "rows": rows,
            "note": ("rank = fy2 growth + FV upside + coverage; "
                     "theme-appropriate columns per archetype TBD")}
