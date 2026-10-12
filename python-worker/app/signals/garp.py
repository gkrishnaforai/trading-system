"""GARP screen — good company at a fair price.

The doctrine: a great company bought at the peak is a bad trade.
This screen intersects the fundamental-health flag (the 'good company'
axis) with valuation (the 'fair price' axis) and the tape (entry
quality), so the output is names that are fundamentally accelerating
or growing AND reasonably priced AND not in freefall.

Score = state base + growth leg + value leg (PEG-style) + quality legs
      + entry-quality momentum ± risk adjustment.
"""
from __future__ import annotations

from typing import Any

# fundamental state → base (the 'good company' filter)
_STATE_BASE = {"accelerating": 25, "growing": 18, "cyclical": 12}
# tape → entry-quality adjust (a pullback in a quality name = the
# discount you want; a knife is just cheaper)
_MOM_ADJ = {"pullback": 8, "basing": 8, "recovery": 8, "breakout": 3,
            "uptrend": 3, "rolling_over": -5, "knife": -10,
            "capitulation": -10, "breakdown": -10, "downtrend": -10}
_RISK_PEN = {"high": -8, "very_high": -15}
# capex-cycle baskets — mirrored from signals/capex_cycle.py
_NEW_BUILD = {"VRT", "ETN", "CRDO", "ALAB", "ONTO", "NVDA", "AVGO", "MU"}
_OPERATORS = {"IREN", "NBIS", "APLD", "CRWV", "EQIX", "MSFT", "AMZN",
              "GOOGL", "ORCL"}


def _peg_points(peg: float) -> int:
    return (25 if peg <= 0.5 else 18 if peg <= 1.0 else
            12 if peg <= 1.5 else 6 if peg <= 2.0 else 0)


def garp_screen(max_pe: float = 40.0, limit: int = 25,
                states: tuple = ("accelerating", "growing",
                                 "cyclical")) -> dict[str, Any]:
    from app.database import db
    rows = db.execute_query(
        "SELECT s.symbol, s.fundamental_state, s.fundamental_risk,"
        " s.fundamental_detail, s.momentum_state, s.momentum_detail,"
        " s.next_earnings_date,"
        " f.rev_growth, f.rev_accel, f.eps_growth, f.beat_streak,"
        " f.est_revision_pct, f.gm_slope, f.muted_reaction, f.fwd_pe,"
        " f.gap_score "
        "FROM stocks s JOIN symbol_flywheel f ON f.symbol = s.symbol "
        "WHERE s.fundamental_state = ANY(:states) "
        "  AND f.fwd_pe IS NOT NULL AND f.fwd_pe > 0 AND f.fwd_pe <= :pe",
        {"states": list(states), "pe": max_pe})

    try:                                        # AI capex-cycle regime
        from app.signals import capex_cycle as _cx_mod
        _cx = _cx_mod.read() or {}
    except Exception:
        _cx = {}
    _cx_flags = set(_cx.get("flags") or [])
    _cx_score = _cx.get("score")

    out = []
    for r in rows:
        sym, state = r["symbol"], r["fundamental_state"]
        det = r.get("fundamental_detail") or {}
        if state == "cyclical" and det.get("cyclical_lean") != "recovery":
            continue                    # cyclical downturn ≠ GARP —
        score, why = _STATE_BASE[state], [f"fund {state}"]  # only recovery

        rg, ra, eg = r.get("rev_growth"), r.get("rev_accel"), \
            r.get("eps_growth")
        if rg and rg > 0:
            g = min(20, rg * 100 * 0.3)
            score += g
            why.append(f"rev {rg * 100:+.0f}%"
                       + (f" accel {ra * 100:+.0f}pts" if ra is not None
                          else ""))
            if ra is not None and ra > 0.05:
                score += 5
        pe = float(r["fwd_pe"])
        if rg and rg > 0.02:
            peg = pe / (rg * 100)
            score += _peg_points(peg)
            why.append(f"fwd P/E {pe:.0f} · PEG {peg:.1f}")
        else:
            why.append(f"fwd P/E {pe:.0f} (no growth leg for PEG)")
            score += 6 if pe <= 15 else 0
        if pe <= 15:
            score += 5

        if (r.get("beat_streak") or 0) >= 3:
            score += 5; why.append(f"{r['beat_streak']}q beats")
        if (r.get("est_revision_pct") or 0) > 0.02:
            score += 5; why.append("estimates rising")
        if (r.get("gm_slope") or 0) > 0.01:
            score += 3; why.append("margin ↑")
        if r.get("muted_reaction"):
            score += 3; why.append("muted reaction")

        mom = r.get("momentum_state")
        adj = _MOM_ADJ.get(mom or "", 0)
        if adj:
            score += adj
            why.append(f"mom {mom} ({'dip discount' if adj > 0 else 'falling — wait'})")
        md = r.get("momentum_detail") or {}
        if isinstance(md, str):
            import json as _j
            try:
                md = _j.loads(md)
            except Exception:
                md = {}
        dp = md.get("dip_phase")
        if dp and mom in {"pullback", "basing", "recovery",
                          "capitulation", "uptrend"}:
            why.append(f"dip {dp.replace('_', ' ')} "
                       f"({md.get('dip_health', '?')}/5)")
            try:
                from app.signals.pattern_priors import prior_for
                pr = prior_for(sym, f"{mom}|{dp or 'none'}")
            except Exception:
                pr = None
            if pr:
                adj = (6 if pr["hit_rate_10d"] >= 0.6
                       and pr["med_ret_10d"] >= 0.04
                       else -6 if pr["hit_rate_10d"] <= 0.35 else 0)
                score += adj
                why.append(
                    f"prior: {round(pr['hit_rate_10d'] * pr['n'])}"
                    f"/{pr['n']} similar → "
                    f"{pr['med_ret_10d'] * 100:+.0f}% median/10d"
                    + ("" if pr["scope"] == "symbol" else " (pooled)"))
        sw = md.get("swing") or {}
        swp = sw.get("phase")
        if swp == "confirmed":
            score += 6
            why.append("higher-low confirmed — pullback structure proven")
        elif swp == "higher_low":
            score += 3
            why.append(f"higher low forming — confirm >"
                       f" ${sw.get('confirm_level')}")
        elif swp == "broken":
            score -= 8
            why.append("⛔ swing structure broken — lower low printed")
        # relative strength percentile — leaders vs laggards
        rs_pct, rs_nh = md.get("rs_pct"), md.get("rs_nh")
        if rs_pct is not None:
            if rs_pct >= 80:
                score += 4
                why.append(f"RS {rs_pct} — leader")
            elif rs_pct <= 30:
                score -= 4
                why.append(f"RS {rs_pct} — laggard")
        if rs_nh:
            score += 3
            why.append("RS line new high — outperforming the tape")
        # earnings distance — an investment into the print is a gamble
        days_er = None
        if r.get("next_earnings_date"):
            try:
                from datetime import date as _d
                ed = r["next_earnings_date"]
                days_er = ((ed if isinstance(ed, _d)
                            else _d.fromisoformat(str(ed)[:10]))
                           - _d.today()).days
            except Exception:
                pass
        if days_er is not None and days_er <= 10:
            why.append(f"⚠️ earnings in {days_er}d — repricing risk")
        pen = _RISK_PEN.get(r.get("fundamental_risk") or "", 0)
        if pen:
            score += pen
            why.append(f"⚠️ risk {r['fundamental_risk']}")
        # AI capex-cycle exposure — long-horizon GARP picks get the same
        # regime nudge: new-build beta discounted under slowdown flags
        if _cx_flags:
            if sym in _NEW_BUILD:
                if _cx_flags & {"CAPEX_SLOWDOWN_ACTIVE",
                                "CAPEX_CONTRACTION"}:
                    score -= 5
                    why.append(f"🏗 capex-beta ({_cx_score}) — build "
                               "cycle slowing")
                else:
                    score -= 2
                    why.append(f"capex watch ({_cx_score})")
            elif sym in _OPERATORS and _cx_flags & {
                    "CAPEX_SLOWDOWN_ACTIVE", "CAPEX_CONTRACTION"}:
                score += 3
                why.append("capex rotation — lifecycle beneficiary")

        out.append({"symbol": sym, "score": round(score, 1),
                    "fund_state": state,
                    "risk": r.get("fundamental_risk"),
                    "fwd_pe": round(pe, 1),
                    "peg": round(pe / (rg * 100), 2) if rg and rg > 0.02
                            else None,
                    "rev_growth": rg, "rev_accel": ra,
                    "beat_streak": r.get("beat_streak"),
                    "momentum": mom, "dip_phase": dp,
                    "swing": sw or None,
                    "rs_pct": rs_pct, "rs_nh": bool(rs_nh),
                    "days_to_earnings": days_er,
                    "why": why})
    out.sort(key=lambda x: -x["score"])
    return {"items": out[:limit], "scanned": len(rows),
            "max_pe": max_pe}


# --- style buckets — one flag set, five investment lanes ----------------------
#
#  compounder   "sure shot" — accelerating/growing, sane risk, fair-ish
#               price, tape not broken. The core book.
#  value        cheap on absolute terms (low P/E or PEG) without being
#               broken — quality at a discount
#  growth       hypergrowth accelerating — valuation is a secondary
#               question (the RB-style lane)
#  multibagger  small-cap / 5x members with accelerating fundamentals —
#               the "could 2x-5x" watchlist
#  recovery     cyclical names whose LEADING legs are turning up while
#               trailing earnings still look weak

_LANES = ("compounder", "value", "growth", "multibagger", "recovery")


def style_screen(limit: int = 15) -> dict[str, Any]:
    from app.database import db
    rows = db.execute_query(
        "SELECT s.symbol, s.market_cap, s.fundamental_state,"
        " s.fundamental_risk, s.fundamental_detail, s.momentum_state,"
        " s.momentum_detail, s.next_earnings_date,"
        " f.rev_growth, f.rev_accel, f.eps_growth, f.beat_streak,"
        " f.est_revision_pct, f.gm_slope, f.muted_reaction, f.fwd_pe,"
        " f.gap_score, sc.tier AS sc_tier, rb.tier AS rb_tier "
        "FROM stocks s JOIN symbol_flywheel f ON f.symbol = s.symbol "
        "LEFT JOIN smallcap_members sc ON sc.symbol = s.symbol "
        "LEFT JOIN rule_breaker_members rb ON rb.symbol = s.symbol "
        "WHERE s.fundamental_state IS NOT NULL"
        "  AND s.fundamental_state <> 'deteriorating'")
    try:                                        # AI capex-cycle regime
        from app.signals import capex_cycle as _cx_mod
        _cx = _cx_mod.read() or {}
    except Exception:
        _cx = {}
    _cx_flags = set(_cx.get("flags") or [])
    _cx_score = _cx.get("score")

    buckets: dict[str, list] = {k: [] for k in _LANES}
    for r in rows:
        sym = r["symbol"]
        state = r["fundamental_state"]
        det = r.get("fundamental_detail") or {}
        lean = det.get("cyclical_lean")
        rg, ra = r.get("rev_growth"), r.get("rev_accel")
        pe = r.get("fwd_pe")
        peg = (float(pe) / (rg * 100)) if (pe and rg and rg > 0.02) else None
        mom = r.get("momentum_state")
        risk = r.get("fundamental_risk")
        mcap = r.get("market_cap")
        small = bool(r.get("sc_tier")) or (mcap is not None
                                         and mcap < 15e9)
        broken_tape = mom in {"knife", "breakdown", "downtrend"}
        why = [f"fund {state}"]
        if rg is not None:
            why.append(f"rev {rg * 100:+.0f}%"
                       + (f" accel {ra * 100:+.0f}pts" if ra is not None
                          else ""))
        if pe:
            why.append(f"fwd P/E {float(pe):.0f}"
                       + (f" · PEG {peg:.2f}" if peg is not None else ""))
        if r.get("sc_tier"):
            why.append(f"5x {r['sc_tier']}")
        if r.get("rb_tier"):
            why.append(f"RB {r['rb_tier']}")
        if mom:
            why.append(f"mom {mom}")
        _md = r.get("momentum_detail") or {}
        if isinstance(_md, str):
            import json as _j
            try:
                _md = _j.loads(_md)
            except Exception:
                _md = {}
        swing = _md.get("swing") or None
        days_er = None
        if r.get("next_earnings_date"):
            try:
                from datetime import date as _d
                ed = r["next_earnings_date"]
                days_er = ((ed if isinstance(ed, _d)
                            else _d.fromisoformat(str(ed)[:10]))
                           - _d.today()).days
            except Exception:
                pass
        cx_tag = None                           # capex-cycle exposure
        if _cx_flags and sym in _NEW_BUILD:
            cx_tag = ("🏗 capex-beta slowing" if _cx_flags & {
                "CAPEX_SLOWDOWN_ACTIVE", "CAPEX_CONTRACTION"}
                else "capex watch")
        elif _cx_flags & {"CAPEX_SLOWDOWN_ACTIVE",
                          "CAPEX_CONTRACTION"} and sym in _OPERATORS:
            cx_tag = "capex rotation candidate"
        if cx_tag:
            why.append(cx_tag)

        def _put(lane: str, lane_score: float, extra: list = None):
            buckets[lane].append(
                {"symbol": sym, "score": round(lane_score, 1),
                 "fund_state": state, "risk": risk, "fwd_pe": pe,
                 "peg": round(peg, 2) if peg is not None else None,
                 "rev_growth": rg, "rev_accel": ra,
                 "beat_streak": r.get("beat_streak"),
                 "momentum": mom, "swing": swing,
                 "rs_pct": _md.get("rs_pct"),
                 "days_to_earnings": days_er,
                 "mcap": mcap, "sc_tier": r.get("sc_tier"),
                 "rb_tier": r.get("rb_tier"),
                 "why": why + (extra or [])})

        base = _STATE_BASE.get(state, 5) \
            + min(20, (rg or 0) * 100 * 0.3) \
            + _MOM_ADJ.get(mom or "", 0) \
            + _RISK_PEN.get(risk or "", 0)

        # 🏛 compounder — sure-shot: growth + sane risk + sane price
        if (state in {"accelerating", "growing"}
                and risk in {"low", "medium"}
                and (pe is None or pe <= 45) and not broken_tape):
            _put("compounder", base
                 + (10 if state == "accelerating" else 0)
                 + (_peg_points(peg) * 0.6 if peg else 0),
                 ["low/med risk — the core book"])
        # 💰 value — genuinely cheap, not broken
        if state != "declining" and (
                (pe is not None and pe <= 20)
                or (peg is not None and peg <= 0.8)):
            _put("value", base
                 + (_peg_points(peg) if peg else 15)
                 + (5 if mom in {"pullback", "basing"} else 0),
                 ["cheap on P/E or PEG — quality at a discount"])
        # 🚀 growth — hypergrowth accelerating; price is secondary
        if rg is not None and rg >= 0.25 and state in {
                "accelerating", "growing", "cyclical"}:
            _put("growth", base + 10 + (5 if (ra or 0) > 0.1 else 0),
                 ["hypergrowth — valuation secondary"])
        # 💎 multibagger — small/5x member with accelerating fundamentals
        if small and state in {"accelerating", "growing"} \
                and (rg or 0) >= 0.15:
            _put("multibagger", base + 12
                 + (8 if r.get("sc_tier") == "runner" else 0),
                 ["small cap + acceleration — the 2x-5x runway"])
        # 🔄 recovery — cyclical with leading legs turning up
        if state == "cyclical" and lean == "recovery" and (
                (r.get("est_revision_pct") or 0) > 0
                or (r.get("beat_streak") or 0) >= 2):
            _put("recovery", base + 8,
                 ["leading legs up while trailing looks weak"])

    for k in buckets:
        buckets[k].sort(key=lambda x: -x["score"])
        buckets[k] = buckets[k][:limit]
    return {"buckets": buckets,
            "counts": {k: len(v) for k, v in buckets.items()},
            "scanned": len(rows)}
