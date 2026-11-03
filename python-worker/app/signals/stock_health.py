"""Per-stock health card — one read that composes what every engine
already persists. Not a new scorer: the aggregator surfaces the
three axes side by side and synthesizes the verdict — especially the
CONFLICTS no single flag shows (fundamentals accelerating + tape
knife = 'watch, don't catch the knife').
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _leadership(det: dict, fly: dict) -> dict | None:
    """Sector-relative leadership — RS rank + the day-level
    defense/offense pattern + the estimate-stability confirmation
    leg. Selection vocabulary for 'one name in the group' reads —
    a prioritization input, never an entry trigger."""
    if det.get("rs_pct") is None:
        return None
    return {"rs_pct": det.get("rs_pct"),
            "rs_nh": det.get("rs_nh"),
            "bench": det.get("rs_bench") or "SPY",
            "quality": det.get("rs_quality"),
            "down_cap": det.get("down_cap"),
            "down_n": det.get("down_n"),
            "up_cap": det.get("up_cap"),
            "up_n": det.get("up_n"),
            "rebound_x": det.get("rebound_x"),
            "est_rev": fly.get("est_revision_pct")}


def _pe_guidance(fwd_pe: float | None, eps_ttm: float | None,
                 fwd_eps: float | None,
                 estimate_age_days: int | None,
                 ttm_age_days: int | None = None) -> dict[str, Any]:
    """Growth-adjusted P/E screen, not a standalone buy signal.

    The estimate must be positive and recently refreshed, and the
    trailing EPS base must also be positive before comparing growth.
    """
    base = {"growth_pct": None, "peg_like": None,
            "reasonable_pe_max": None, "stretched_pe_above": None}
    if fwd_eps is None or fwd_eps <= 0 or fwd_pe is None:
        return {**base, "label": "P/E not usable",
                "reason": "No positive forward EPS estimate; use a sales, cash-flow, or scenario valuation method."}
    if estimate_age_days is None or estimate_age_days < 0:
        return {**base, "label": "Estimate freshness unknown",
                "reason": "Forward P/E is shown, but the estimate date is unavailable; do not rely on the growth screen."}
    if estimate_age_days > 45:
        return {**base, "label": "Estimate is stale",
                "reason": f"Consensus snapshot is {estimate_age_days} days old; refresh estimates before using forward P/E guidance."}
    if ttm_age_days is not None and ttm_age_days > 180:
        return {**base, "label": "Trailing EPS is stale",
                "reason": f"Latest reported EPS is {ttm_age_days} days old; refresh reported results before using the growth screen."}
    if eps_ttm is None:
        return {**base, "label": "Trailing EPS unavailable",
                "reason": "Fewer than four recent reported quarters are available; forward growth versus TTM EPS cannot be verified."}
    if eps_ttm <= 0:
        return {**base, "label": "Profitability transition",
                "reason": "Trailing EPS is not positive, so forward EPS growth and a PEG-style comparison are not meaningful."}

    # read-time sanity vs the reported basis — a stored estimate on
    # the wrong basis (far-year row, unit mismatch) passes the NULL
    # and age checks but is not a usable forward multiple. Needs a
    # sane denominator; near-zero TTM can't judge the ratio.
    if eps_ttm >= 0.25 and not (0.05 <= fwd_eps / eps_ttm <= 6.0):
        return {**base,
                "label": "Estimate basis suspect",
                "reason": (f"Forward EPS ${fwd_eps:.2f} is {fwd_eps / eps_ttm:.1f}x "
                           f"reported TTM EPS ${eps_ttm:.2f} — the stored "
                           "estimate is likely on the wrong fiscal-year "
                           "basis. Do not use this forward P/E until the "
                           "flywheel refreshes.")}

    growth_pct = (fwd_eps / eps_ttm - 1) * 100
    growth_data = {
        **base,
        "growth_pct": round(growth_pct, 1),
        "reasonable_pe_max": round(max(0.0, growth_pct) * 1.5, 1),
        "stretched_pe_above": round(max(0.0, growth_pct) * 2.5, 1),
    }
    if growth_pct <= 0:
        return {**growth_data, "label": "Avoid on P/E basis",
                "reason": "Consensus forward EPS is not growing versus trailing EPS; a low multiple alone is not a buy case."}

    peg_like = fwd_pe / growth_pct
    growth_data["peg_like"] = round(peg_like, 2)
    if peg_like <= 1:
        label = "Attractive on growth screen"
        reason = "Forward P/E is at or below expected EPS growth; confirm growth durability, cash conversion, and fair-value buy-below."
    elif peg_like <= 1.5:
        label = "Reasonable on growth screen"
        reason = "Forward P/E is within 1.5x expected EPS growth; use the fair-value buy-below as the price gate."
    elif peg_like <= 2.5:
        label = "Premium"
        reason = "The multiple is ahead of expected EPS growth; require unusually durable growth and strong cash-flow quality."
    else:
        label = "Stretched / avoid"
        reason = "Forward P/E is more than 2.5x expected EPS growth; estimates may need to rise materially to justify the price."
    if growth_pct > 50:
        reason += " Growth exceeds 50%, so base effects can make this screen overly optimistic."
    return {**growth_data, "label": label, "reason": reason}


def _multiples(spot: float | None, earnings_rows: list[dict],
              fly: dict, today: date | None = None,
              spot_date: date | None = None,
              eps_period: date | None = None,
              eps_fy2: float | None = None,
              fy2_period: date | None = None) -> dict[str, Any]:
    """Build price multiples from reported EPS and the existing estimate feed."""
    today = today or date.today()

    def _as_date(value) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            return None

    eps_values = []
    for row in earnings_rows:
        try:
            value = float(row.get("eps_actual"))
            if value == value and abs(value) != float("inf"):
                eps_values.append(value)
        except (TypeError, ValueError):
            continue
    eps_ttm = round(sum(eps_values), 2) if len(eps_values) == 4 else None
    ttm_date = max((_as_date(r.get("earnings_date"))
                    for r in earnings_rows), default=None)
    ttm_age = (today - ttm_date).days if ttm_date else None

    try:
        fwd_eps = float(fly["fwd_eps_avg"])
        if fwd_eps != fwd_eps or abs(fwd_eps) == float("inf"):
            fwd_eps = None
    except (KeyError, TypeError, ValueError):
        fwd_eps = None
    try:
        price = float(spot) if spot is not None else None
        if price is not None and (price <= 0 or abs(price) == float("inf")):
            price = None
    except (TypeError, ValueError):
        price = None
    pe_ttm = (round(price / eps_ttm, 1)
              if price and eps_ttm and eps_ttm > 0 else None)
    fwd_pe = (round(price / fwd_eps, 1)
              if price and fwd_eps and fwd_eps > 0 else None)

    estimate_date = _as_date(fly.get("updated_at"))
    estimate_age = ((today - estimate_date).days
                    if estimate_date else None)
    spot_age = ((today - spot_date).days if spot_date else None)
    guidance = _pe_guidance(
        fwd_pe, eps_ttm, fwd_eps, estimate_age, ttm_age)
    if spot_age is not None and spot_age > 4 and fwd_pe is not None:
        # a stale close makes the multiple meaningless — a frozen
        # 2024 price against today's consensus reads as cheap
        guidance = {
            "label": "Stale price",
            "reason": (f"Spot close is {spot_age} days old; forward "
                       "P/E is computed against a stale price and "
                       "should not be trusted until daily_bars "
                       "refreshes.")}

    # PEG-anchored fair-value band — the market pays a multiple
    # roughly proportional to DURABLE growth, so anchor price zones
    # at 1.0x/1.5x/2.0x the consensus growth rate instead of a fixed
    # P/E cutoff. spot_peg = where the price actually sits in band.
    g_pct = (guidance or {}).get("growth_pct")
    spot_peg = (guidance or {}).get("peg_like")
    peg_band = None
    if fwd_eps and g_pct is not None and g_pct > 0:
        lo = round(fwd_eps * g_pct * 1.0, 2)
        mid = round(fwd_eps * g_pct * 1.5, 2)
        hi = round(fwd_eps * g_pct * 2.0, 2)
        zone = None
        if spot_peg is not None:
            zone = ("below band" if spot_peg < 1.0 else
                    "fair zone" if spot_peg <= 1.5 else
                    "rich" if spot_peg <= 2.0 else
                    "priced for perfection")
        peg_band = {"growth_pct": g_pct, "peg_1_0_price": lo,
                    "peg_1_5_price": mid, "peg_2_0_price": hi,
                    "spot_peg": spot_peg, "zone": zone}

    # multi-year discounted view — hyper-growth names are priced on
    # FY+2/FY+3 earnings a year early; discounting the out-year EPS
    # back at a justified exit multiple shows what 'priced in' means
    fy2_pe = fy2_equiv = None
    if eps_fy2 and price:
        fy2_pe = round(price / eps_fy2, 1)
        if g_pct is not None and g_pct > 0:
            exit_m = g_pct * 1.2          # mid-band exit multiple
            fy2_equiv = round(eps_fy2 * exit_m / 1.10, 2)

    # the growth-adjusted fair value is the 1.5x-PEG anchor — state
    # it explicitly with the spot delta so the band isn't just three
    # unlabeled prices
    fv_growth = (peg_band or {}).get("peg_1_5_price")
    fv_growth_upside = (round((fv_growth / price - 1) * 100, 1)
                        if fv_growth and price else None)
    return {
        "spot": price,
        "eps_ttm": eps_ttm,
        "pe_ttm": pe_ttm,
        "ttm_as_of": ttm_date.isoformat() if ttm_date else None,
        "ttm_age_days": ttm_age,
        "spot_age_days": spot_age,
        "fwd_eps": fwd_eps,
        "fwd_eps_period": (eps_period.isoformat()
                           if eps_period else None),
        "fwd_pe": fwd_pe,
        "estimate_as_of": estimate_date.isoformat() if estimate_date else None,
        "estimate_age_days": estimate_age,
        "analyst_count": fly.get("num_analysts"),
        "guidance": guidance,
        "spot_peg": spot_peg,
        "peg_band": peg_band,
        "fv_growth": fv_growth,
        "fv_growth_upside_pct": fv_growth_upside,
        "fy2_eps": eps_fy2,
        "fy2_period": fy2_period.isoformat() if fy2_period else None,
        "fy2_pe": fy2_pe,
        "fy2_equiv": fy2_equiv,
    }


def _verdict(fund: Optional[str], mom: Optional[str],
             valuation: Optional[str],
             future_score: Optional[float],
             lane: Optional[str] = None) -> dict[str, str]:
    """The honest one-line read — conflicts get named, not hidden."""
    strong_fund = fund in ("accelerating", "growing")
    weak_fund = fund in ("declining", "deteriorating")
    hot_tape = mom in ("breakout", "uptrend", "climax")
    dip = mom in ("pullback", "basing")
    broken = mom in ("knife", "capitulation", "breakdown",
                     "downtrend", "rolling_over")
    expensive = valuation in ("extreme", "elevated")

    if strong_fund and mom == "climax" and not expensive:
        v, why = "deploy on dips", ("aligned but at euphoria — the "
                                    "system's own rule: extended means "
                                    "wait for the pullback/stall")
    elif strong_fund and hot_tape and not expensive:
        v, why = "deploy", ("fundamentals strong + tape confirming — "
                            "the aligned profile")
    elif strong_fund and dip and not expensive:
        v, why = "deploy on dips", ("fundamentals strong, tape in a "
                                    "pullback — entries, not chases")
    elif strong_fund and broken:
        v, why = "watch", ("fundamentals strong but the tape is "
                           "broken — don't catch the knife; wait for "
                           "the base")
    elif weak_fund and hot_tape:
        v, why = "momentum-only", ("tape strong, fundamentals "
                                   "deteriorating — trade it, don't "
                                   "marry it; tight stops")
    elif not strong_fund and not weak_fund and hot_tape and not expensive:
        v, why = "deploy", ("tape-led — fundamentals cooling but not "
                            "broken; ride it, tighter review")
    elif strong_fund and expensive:
        v, why = "future shelf", ("right company, rich price — "
                                  "watch for the valuation to come "
                                  "to you")
    elif weak_fund and broken:
        v, why = "avoid", "fundamentals and tape both broken"
    elif weak_fund:
        v, why = "avoid", "fundamentals deteriorating"
    elif fund == "turnaround" and (dip or broken):
        v, why = "watch", ("trailing weak but estimates turning up — "
                           "early accumulation zone, prove it small")
    elif fund == "turnaround":
        v, why = "watch", ("estimates turning up on a weak base — "
                           "unproven; watch for confirmation")
    elif fund == "pressured" and hot_tape:
        v, why = "momentum-only", ("tape strong but estimates being "
                                   "cut — ride light, tight review")
    elif fund == "pressured":
        v, why = "watch", ("estimates being cut while trailing "
                           "holds — early warning")
    elif future_score and future_score >= 50:
        v, why = "future shelf", ("thesis exposure without "
                                  "confirmation yet — the watch "
                                  "bucket")
    elif broken:
        v, why = "avoid", "tape broken"
    elif lane == "deploy":
        v, why = "deploy", "the conviction engine has it in the deploy lane"
    else:
        v, why = "neutral", "no strong signal either way"
    return {"verdict": v, "why": why}


def _readiness(mom: Optional[str], det: dict, fund: Optional[str],
               fly: dict, q: dict, conv: dict,
               fv_up: Optional[float],
               val: Optional[str] = None,
               pe_ctx: Optional[dict] = None,
               gq: Optional[dict] = None,
               priced: Optional[str] = None) -> dict[str, Any]:
    """Use-case readiness — swing / invest / LEAP call / LEAP put —
    each a deterministic checklist of stored-data facts mirroring the
    engines' own gates. Every line names the rule and the value."""
    det = det or {}
    # swing / invest / leap_call checklists now live in
    # pulse_action_rules.yaml `use_cases` — same interpreter, same
    # missing-data semantics and fv_valid contract as Portfolio Pulse.
    # leap_put stays put_entry-driven (factor scoring, not a list).
    from app.signals import pulse_engine
    _uc_row = {"mom_state": mom, "fund_state": fund,
               "momentum_detail": det, "fv_upside": fv_up,
               "priced_status": priced,
               "rev_growth": fly.get("rev_growth"),
               "eps_growth": fly.get("eps_growth"),
               "future_score": conv.get("future_score"),
               "lane": conv.get("lane"),
               "gq_score": (gq or {}).get("score"),
               "structural_proof": ((gq or {}).get("components") or {})
                                    .get("structural_proof")}
    out = {uc: pulse_engine.eval_use_case(_uc_row, uc)
           for uc in ("swing", "invest", "leap_call")}

    # ---- 📕 LEAP puts — PUT_ENTRY_SCORE drives the verdict ----------
    # extension identifies, exhaustion + support failure earn the entry;
    # category A (strong biz, multiple compression) is the only lane
    # that can go 'ready' — B-type caps at watch by design.
    pe = (pe_ctx or {}).get("pe") or {}
    band = pe.get("band") or "none"
    cat = pe.get("category") or "speculative"
    _r = lambda ok, line: {"ok": bool(ok), "line": line}
    put_rules = [
        _r(f["pts"] > 0,
           f"{f['name']} {f['pts']:.0f}/{f['weight']} — {f['note']}")
        for f in pe.get("factors") or []
    ] or [_r(False, "no tape data — momentum refresh needed")]
    if cat != "valuation_put":
        put_rules.append(_r(
            False, "category gate — "
            + (pe.get("category_note") or "not A-type")))
    if pe.get("chase_block"):
        put_rules.append(_r(
            False, "already broke — the entry was earlier, don't chase"))
    stage_txt = ""
    if pe.get("stage"):
        stage_txt = "staged entry: " + " → ".join(
            f"${s['level']} ({s['tranche']})" for s in pe["stage"])
    pe_state = ("ready" if cat == "valuation_put"
                and band in ("starter", "add", "major") else
                "close" if band in ("watch", "starter", "add", "major")
                else "no")
    out["leap_put"] = {"state": pe_state,
                       "score": pe.get("score"),
                       "of": 100, "band": band,
                       "category": cat,
                       "category_note": pe.get("category_note"),
                       "stage": pe.get("stage"), "stage_txt": stage_txt,
                       "rules": put_rules}
    return out


def card(sym: str) -> dict[str, Any]:
    """Compose the full card — every engine's persisted read on one
    symbol, plus real LTM quality from the quarterly journal."""
    from app.database import db
    s = sym.upper()
    try:
        st = db.execute_query(
            "SELECT symbol, company_name, sector, market_cap,"
            " momentum_state, momentum_detail, momentum_updated_at,"
            " fundamental_state, fundamental_detail, fundamental_risk,"
            " fundamental_updated_at,"
            " revision_score, revision_grade, priced_status,"
            " emerging_growth, fwd_detail,"
            " next_earnings_date, next_earnings_session,"
            " next_earnings_source, next_earnings_updated_at,"
            " rating, price_target, industry"
            " FROM stocks WHERE symbol=:s",
            {"s": s})
    except Exception:
        # pre-026 schema — provenance columns absent; degrade to the
        # narrow select rather than 500 the card
        st = db.execute_query(
            "SELECT symbol, company_name, sector, market_cap,"
            " momentum_state, momentum_detail, momentum_updated_at,"
            " fundamental_state, fundamental_detail, fundamental_risk,"
            " fundamental_updated_at,"
            " revision_score, revision_grade, priced_status,"
            " emerging_growth, fwd_detail,"
            " next_earnings_date, rating, price_target, industry"
            " FROM stocks WHERE symbol=:s",
            {"s": s})
    st = dict(st[0]) if st else {"symbol": s}

    def _j(v):
        import json
        return json.loads(v) if isinstance(v, str) else (v or {})

    det = _j(st.get("momentum_detail"))
    fdet = _j(st.get("fundamental_detail"))
    fly = db.execute_query(
        "SELECT rev_growth, rev_accel, eps_growth, eps_accel,"
        " eps_growth_ttm, beat_streak, est_revision_pct, fwd_pe,"
        " fwd_eps_avg, last_report_date, gap_score, fcf_ttm, fcf_margin,"
        " num_analysts, updated_at FROM symbol_flywheel WHERE symbol=:s",
        {"s": s})
    fly = dict(fly[0]) if fly else {}
    conv = db.execute_query(
        "SELECT snap_date, rank, score, lane, future_score, sources,"
        " daily_pick, weekly_pick, monthly_pick, theme"
        " FROM conviction_snapshots WHERE symbol=:s"
        " ORDER BY snap_date DESC LIMIT 1", {"s": s})
    conv = dict(conv[0]) if conv else {}
    gem = db.execute_query(
        "SELECT snap_date, score, aligned, valuation"
        " FROM hidden_gem_snapshots WHERE symbol=:s"
        " ORDER BY snap_date DESC LIMIT 1", {"s": s})
    gem = dict(gem[0]) if gem else {}
    hedge = db.execute_query(
        "SELECT snap_date, score, tier, corr_target, beta_to_target,"
        " iv_hv, setup FROM hedge_universe_snapshots WHERE symbol=:s"
        " ORDER BY snap_date DESC LIMIT 1", {"s": s})
    hedge = dict(hedge[0]) if hedge else {}
    call = db.execute_query(
        "SELECT call_date, rank, score, entry_px, stop_px, target_px"
        " FROM daily_calls WHERE symbol=:s"
        " ORDER BY call_date DESC LIMIT 1", {"s": s})
    call = dict(call[0]) if call else {}
    sec = {}
    try:
        r = db.execute_query(
            "SELECT rpo, crpo, rpo_period, goodwill,"
            " goodwill_assets_pct, acq_spend_fy, shares_step_ratio,"
            " split_suspect, rpo_yoy, crpo_share, def_rev_cur,"
            " def_rev_yoy, gw_impair_fy, as_of FROM symbol_sec_facts"
            " WHERE symbol=:s", {"s": s})
        if r:
            sec = dict(r[0])
            sec["as_of"] = str(sec["as_of"]) if sec.get("as_of") \
                else None
            sec["rpo_period"] = str(sec["rpo_period"]) \
                if sec.get("rpo_period") else None
        f2 = db.execute_query(
            "SELECT fcf_ttm, fcf_margin, fcf_growth, acq_rev_pct"
            " FROM symbol_flywheel WHERE symbol=:s", {"s": s})
        if f2:
            sec.update({k: f2[0][k] for k in f2[0]})
    except Exception:
        pass
    sec = sec or None
    review = None
    try:
        from app.signals import event_review
        review = event_review.latest(s)
    except Exception:
        pass

    from app.signals.conviction import _quality, _future
    q = _quality(s)
    if not conv:
        # off-List names still get a live future score — the shelf
        # question ('small now, huge TAM later') shouldn't need a
        # conviction snapshot row to answer
        fs, _ = _future(s, fly, q, st.get("market_cap"))
        conv = {"future_score": fs}
    from app.signals.future_themes import registry
    themes = [{"key": k, "name": t["name"], "exposure": t["members"][s],
               "stage": t["stage"]}
              for k, t in registry().items() if s in t["members"]]
    try:
        rot = {r["theme_key"]: r for r in db.execute_query(
            "SELECT DISTINCT ON (theme_key) theme_key, call, rank,"
            " score FROM theme_rotation_runs"
            " ORDER BY theme_key, as_of DESC")}
        for t in themes:
            rr = rot.get(t["key"])
            if rr:
                t["rotation"] = {"call": rr["call"],
                                 "rank": rr["rank"],
                                 "score": rr["score"]}
    except Exception:
        pass

    # fair-value upside vs latest close — the valuation leg of the
    # readiness checks (post-ADR normalization); scenario FVs + spot
    # feed PUT_ENTRY's bull-case-distance asymmetry
    fv_up, scen, spot = None, {}, None
    spot_date = None
    fv_detail = {}
    _fund_as_of = _fundamentals_data_as_of(s)
    try:
        r = db.execute_query(
            "SELECT symbol, fair_value, scenario_fair_values,"
            " expected_fair_value,"
            " quality_flags, regime, method_results, decision, as_of,"
            " inputs_watermark, spot_at_run, model_version"
            " FROM fair_value_v2_runs WHERE symbol=:s"
            " ORDER BY as_of DESC LIMIT 1", {"s": s})
        p = db.execute_query(
            "SELECT close, date FROM daily_bars WHERE symbol=:s"
            " ORDER BY date DESC LIMIT 1", {"s": s})
        if r and p and r[0]["fair_value"] and p[0]["close"]:
            fv_up = round((float(r[0]["fair_value"]) /
                           float(p[0]["close"]) - 1) * 100, 1)
        if p and p[0]["close"]:
            spot = float(p[0]["close"])
            _sd = p[0].get("date")
            spot_date = (_sd if isinstance(_sd, date)
                         else date.fromisoformat(str(_sd)[:10])
                         if _sd else None)
        sc = (r[0].get("scenario_fair_values") if r else None)
        if isinstance(sc, dict):
            scen = sc
        if r:
            fv_detail = _fv_detail(r[0], spot, _fund_as_of)
    except Exception:
        pass

    # Use the same growth-adjusted read for the stock verdict and the
    # price card; fixed P/E cutoffs ignore how fast earnings are growing.
    earnings_rows = []
    try:
        earnings_rows = db.execute_query(
            "SELECT earnings_date, eps_actual FROM earnings_data"
            " WHERE stock_symbol=:s AND eps_actual IS NOT NULL"
            " ORDER BY earnings_date DESC LIMIT 4", {"s": s})
    except Exception:
        pass
    eps_period = fy2_eps = fy2_period = None
    try:
        # the fiscal year fwd_eps_avg covers + the FY+2 estimate for
        # the discounted out-year view — flywheel picks the first
        # annual estimate > today+60d; snapshots share the rule
        ep = db.execute_query(
            "SELECT DISTINCT ON (period_end) period_end, eps_avg"
            " FROM symbol_estimate_snapshots WHERE symbol=:s"
            " AND period_end > :cut AND eps_avg IS NOT NULL"
            " ORDER BY period_end, as_of DESC LIMIT 2",
            {"s": s, "cut": date.today() + timedelta(days=60)})
        if ep:
            _ep = ep[0].get("period_end")
            eps_period = (_ep if isinstance(_ep, date)
                          else date.fromisoformat(str(_ep)[:10])
                          if _ep else None)
        if len(ep) > 1:
            fy2_eps = float(ep[1]["eps_avg"]) \
                if ep[1].get("eps_avg") is not None else None
            _ep2 = ep[1].get("period_end")
            fy2_period = (_ep2 if isinstance(_ep2, date)
                          else date.fromisoformat(str(_ep2)[:10])
                          if _ep2 else None)
    except Exception:
        pass
    multiples = _multiples(spot, earnings_rows, fly,
                           spot_date=spot_date, eps_period=eps_period,
                           eps_fy2=fy2_eps, fy2_period=fy2_period)
    pe_label = (multiples.get("guidance") or {}).get("label")
    if pe_label in ("Attractive on growth screen",
                    "Reasonable on growth screen"):
        val = "reasonable"
    elif pe_label == "Premium":
        val = "elevated"
    elif pe_label == "Stretched / avoid":
        val = "extreme"
    else:
        val = gem.get("valuation") or "unknown"
    verdict = _verdict(st.get("fundamental_state"),
                       st.get("momentum_state"), val,
                       conv.get("future_score"), conv.get("lane"))

    from app.signals import put_entry, tape_diagnosis
    pe = put_entry.score(det, st.get("momentum_state"),
                         st.get("fundamental_state"), fly, scen,
                         spot, put_entry._regime(), sym=s)
    gq = _try_growth_quality(s)
    readiness = _readiness(st.get("momentum_state"), det,
                           st.get("fundamental_state"), fly, q,
                           conv, fv_up, val, {"pe": pe}, gq,
                           st.get("priced_status"))
    tws = _try_tailwinds(s)
    # catalyst badge — a corroborated channel makes a 'close' verdict
    # actionable; never overrides a failed gate, just flags the signal
    tw_b = 0.0
    tw_top = None
    if tws:
        from app.signals.tailwinds import bonus as _twb, _TIER_BONUS
        tw_b = _twb(s)
        tw_top = max(tws, key=lambda t:
                     _TIER_BONUS.get(t["tier"], 1)
                     + (t.get("hit_count") or 0))
        readiness["catalyst"] = {
            "bonus": round(tw_b, 1),
            "channel": tw_top["channel"],
            "tier": tw_top["tier"],
            "direction": tw_top["direction"],
            "hits": tw_top.get("hit_count") or 1,
            "corroborated": tw_top["tier"] in ("shipping", "revenue")
                or (tw_top.get("hit_count") or 0) >= 3,
        }

    # sector flow — which capital-flow state this stock's sector ETF is
    # in (inflow / rotating in / outflow / quiet). Same cached map the
    # pulse board uses; context for "is rotation reaching this name",
    # not an entry signal.
    sector_flow = None
    try:
        from app.api.board_api import _sector_flow_map
        from app.market_regime.rotation import (
            SECTOR_NAMES, THEME_ETFS, _SECTOR_TO_ETF,
            _INDUSTRY_TO_THEME_ETF)
        _etf = _SECTOR_TO_ETF.get((st.get("sector") or "").lower())
        # industry refines the broad GICS sector — a semi name reads
        # against SMH, software against IGV, not the XLK blend
        _ind = (st.get("industry") or "").lower()
        for _pat, _tetf in _INDUSTRY_TO_THEME_ETF:
            if _pat in _ind:
                _etf = _tetf
                break
        if _etf:
            _flow = _sector_flow_map()
            _m = _flow.get(_etf)
            if _m is None and _etf != _SECTOR_TO_ETF.get(
                    (st.get("sector") or "").lower()):
                # theme ETF has no bar coverage — fall back to the
                # parent sector rather than show an empty read
                _etf = _SECTOR_TO_ETF.get(
                    (st.get("sector") or "").lower())
                _m = _flow.get(_etf) if _etf else None
            if _etf:
                sector_flow = {
                    "etf": _etf,
                    "name": SECTOR_NAMES.get(_etf)
                            or THEME_ETFS.get(_etf),
                    "flow": (_m or {}).get("flow"),
                    "score": (_m or {}).get("score")}
    except Exception:
        pass

    # last realized print + the analysis verdict on it — 'the last
    # quarterly analysis' the page can cite beside the report-date
    # clock (which stays honest: the print date IS the data age)
    last_print = None
    try:
        lp = db.execute_query(
            "SELECT e.earnings_date, e.eps_estimate, e.eps_actual,"
            " e.surprise_percentage, e.adjusted_eps_actual,"
            " e.one_time_items, e.revenue_estimate, e.revenue_actual,"
            " w.verdict, w.detail"
            " FROM earnings_data e"
            " LEFT JOIN earnings_watch w"
            "   ON w.symbol=e.stock_symbol"
            "  AND w.earnings_date=e.earnings_date"
            " WHERE e.stock_symbol=:s AND e.eps_actual IS NOT NULL"
            " ORDER BY e.earnings_date DESC LIMIT 1", {"s": s})
        if lp:
            last_print = dict(lp[0])
            last_print["earnings_date"] = str(
                last_print["earnings_date"])
            it = last_print.get("one_time_items")
            last_print["one_time_items"] = (
                it if isinstance(it, list) else None)
            # NB: not `det` — that name holds momentum_detail for the
            # whole card (technical detail, leadership, diagnosis);
            # shadowing it here leaked earnings detail into the tape panel
            lpdet = _j(last_print.get("detail"))
            last_print["narrative"] = lpdet.get("narrative")
            last_print["drivers"] = lpdet.get("drivers") or []
            last_print.pop("detail", None)
    except Exception:
        pass

    # earnings event — canonical fields (stocks.next_earnings_* are
    # derived from earnings_events by the indexer) + provenance + the
    # staleness invariant: a journaled print NEWER than the 'next'
    # date means the calendar is stale, and a next_earnings_updated_at
    # older than a month is unverified, not verified
    earnings = None
    try:
        today = date.today()
        ne = st.get("next_earnings_date")
        verified_at = st.get("next_earnings_updated_at")
        lp_date = None
        if last_print and last_print.get("earnings_date"):
            try:
                lp_date = date.fromisoformat(
                    str(last_print["earnings_date"])[:10])
            except Exception:
                lp_date = None
        issues: list[str] = []
        ne_date = None
        if ne:
            try:
                ne_date = (ne.date() if isinstance(ne, datetime)
                           else ne)
            except Exception:
                ne_date = None
        if lp_date and ne_date and lp_date > ne_date:
            issues.append(
                "a newer print exists than the 'next' date — "
                "earnings calendar is stale")
        if ne_date and ne_date < today:
            issues.append("next earnings date is in the past — "
                          "calendar not refreshed since the print")
        verified_age = None
        if verified_at:
            try:
                va = (verified_at.date()
                      if isinstance(verified_at, datetime)
                      else verified_at)
                verified_age = (today - va).days
                if verified_age > 30:
                    issues.append(
                        f"earnings date last verified {verified_age}d "
                        "ago — unverified")
            except Exception:
                verified_age = None
        else:
            if ne_date:
                issues.append("earnings date unverified "
                              "(no verification stamp)")
        if ne_date or issues or lp_date:
            earnings = {
                "date": str(ne_date) if ne_date else None,
                "days": ((ne_date - today).days if ne_date else None),
                "session": st.get("next_earnings_session"),
                "source": st.get("next_earnings_source"),
                "verified_at": str(verified_at)[:10]
                    if verified_at else None,
                "verified_age_days": verified_age,
                "last_print_date": str(lp_date) if lp_date else None,
                "stale": bool(issues),
                "issues": issues,
            }
    except Exception:
        earnings = None

    # 60-bar sparkline — canonical daily_bars, server-rendered; the
    # last-bar date rides along so a stale price feed is visible
    # instead of looking current
    spark: list[float] = []
    spark_as_of = None
    try:
        sp = db.execute_query(
            "SELECT close, date FROM daily_bars WHERE symbol=:s"
            " ORDER BY date DESC LIMIT 60", {"s": s})
        spark = [float(r["close"]) for r in reversed(sp)
                 if r.get("close") is not None]
        if sp and sp[0].get("date"):
            spark_as_of = str(sp[0]["date"])[:10]
    except Exception:
        spark = []

    # data confidence — one rolled-up trust grade across every
    # staleness/quality flag the card already computes. Per-section
    # flags tell you WHERE the rot is; this tells you whether to trust
    # the page today.
    conf_issues: list[str] = []
    try:
        if fv_detail.get("valuation_status") == "needs_validation":
            vi = fv_detail.get("valuation_issues") or []
            conf_issues.append(
                "valuation: " + ", ".join(vi) if vi
                else "valuation flagged")
        if "extreme_gap" in (fv_detail.get("flags") or []):
            conf_issues.append("fv vs spot gap is extreme")
        if earnings and earnings.get("stale"):
            conf_issues.append(
                "; ".join(earnings["issues"]))
        try:
            fl_at = fly.get("updated_at")
            fl_d = (fl_at.date() if isinstance(fl_at, datetime)
                    else fl_at)
            if fl_d and (date.today() - fl_d).days > 10:
                conf_issues.append(
                    f"fundamentals engine {(date.today() - fl_d).days}d "
                    "stale")
            elif not fl_d:
                conf_issues.append("no fundamentals engine data")
        except Exception:
            pass
        try:
            mo_at = st.get("momentum_updated_at")
            mo_d = (mo_at.date() if isinstance(mo_at, datetime)
                    else mo_at)
            if mo_d and (date.today() - mo_d).days > 3:
                conf_issues.append(
                    f"tape engine {(date.today() - mo_d).days}d stale")
            elif not mo_d:
                conf_issues.append("no tape engine data")
        except Exception:
            pass
        try:
            if spark_as_of:
                sa = date.fromisoformat(spark_as_of)
                if (date.today() - sa).days > 4:
                    conf_issues.append(
                        f"price feed {(date.today() - sa).days}d stale")
            else:
                conf_issues.append("no price bars")
        except Exception:
            pass
    except Exception:
        pass
    data_confidence = {
        "grade": ("high" if not conf_issues
                  else "medium" if len(conf_issues) == 1 else "low"),
        "issues": conf_issues,
    }

    return {"symbol": s, "name": st.get("company_name"),
            "sector": st.get("sector"),
            "sector_flow": sector_flow,
            "market_cap": st.get("market_cap"),
            "spot": spot,
            "next_earnings": (str(st.get("next_earnings_date"))
                              if st.get("next_earnings_date") else None),
            "earnings": earnings,
            "last_print": last_print,
            "multiples": multiples,
            "spark": spark,
            "spark_as_of": spark_as_of,
            "data_confidence": data_confidence,
            "verdict": verdict,
            "fundamental": {"state": st.get("fundamental_state"),
                            "risk": st.get("fundamental_risk"),
                            "as_of": (str(st.get("fundamental_updated_at"))
                                      if st.get("fundamental_updated_at")
                                      else None),
                            "data_as_of": _fund_as_of,
                            "detail": fdet},
            "technical": {"state": st.get("momentum_state"),
                          "as_of": (str(st.get("momentum_updated_at"))
                                    if st.get("momentum_updated_at")
                                    else None),
                          "detail": det},
            "growth": fly,
            "leadership": _leadership(det, fly),
            "forward": {"revision_score": st.get("revision_score"),
                        "revision_grade": st.get("revision_grade"),
                        "priced_status": st.get("priced_status"),
                        "emerging_growth": st.get("emerging_growth"),
                        "detail": _j(st.get("fwd_detail"))},
            "quality": q,
            "valuation": val,
            "conviction": conv, "hidden_gem": gem,
            "hedge": hedge, "swing_call": call,
            "fv_upside_pct": fv_up, "fv": fv_detail,
            "fv_v1": _try_fv_v1(s, spot),
            "lt_power": _try_lt_power(s),
            "growth_quality": gq,
            "capex": _try_capex(s),
            "sec": sec,
            "review": review,
            "readiness": readiness,
            "selloff": _try_selloff(s),
            "thesis": _try_thesis(s, fv_up,
                                  st.get("momentum_state")),
            "liquidity": _try_liquidity(s, fly),
            "tailwinds": tws, "watches": _try_watches(s),
            "diagnosis": tape_diagnosis.diagnose(
                s, sector=st.get("sector"),
                momentum_state=st.get("momentum_state"),
                momentum_detail=det,
                fundamental_state=st.get("fundamental_state"),
                priced_status=st.get("priced_status"),
                next_earnings=st.get("next_earnings_date")),
            "themes": themes,
            "analyst": {"rating": st.get("rating"),
                        "price_target": st.get("price_target")}}


def _method_explain(method_key: str, inputs: dict,
                    scenarios: dict) -> dict:
    """Per-scenario 'why this number' — recomputed from the run's own
    inputs_used so the explanation is deterministic, not narrative.
    PE/PEG families → implied EPS × multiple; EV/S → implied multiple
    on revenue; PB → BVPS × P/B; DCF → its assumption string."""
    out: dict[str, str] = {}
    mk = method_key or ""
    eps = inputs.get("eps_ttm") or inputs.get("eps_forward")
    basis = "fwd EPS" if inputs.get("eps_forward") else "EPS"
    bvps = inputs.get("book_value_per_share")
    rev = inputs.get("revenue_ttm")
    sh = inputs.get("shares_outstanding")
    nd = (inputs.get("total_debt") or 0) - \
        (inputs.get("cash_and_equivalents") or 0)
    for k, v in (scenarios or {}).items():
        if v is None:
            continue
        try:
            fv = float(v)
        except Exception:
            continue
        if (mk.startswith("pe_") or mk.startswith("peg")) and eps:
            out[k] = f"{basis} {float(eps):.2f} × {fv / float(eps):.1f}x"
        elif mk.startswith("pb_") and bvps:
            out[k] = f"BVPS {float(bvps):.2f} × {fv / float(bvps):.2f}x"
        elif mk.startswith("ev_sales") and rev and sh:
            mult = (fv * float(sh) + nd) / float(rev)
            out[k] = (f"rev {float(rev) / 1e9:.1f}B × {mult:.1f}x EV/S"
                      " − net debt")
        elif mk.startswith("ev_fcf") and inputs.get("fcf_ttm") and sh:
            fcf = float(inputs["fcf_ttm"])
            mult = (fv * float(sh) + nd) / fcf
            out[k] = (f"FCF {fcf / 1e9:.1f}B × {mult:.1f}x EV/FCF"
                      " − net debt")
        elif mk.startswith("dcf"):
            g = inputs.get("param.growth")
            out[k] = "10y DCF on FCF (growth fade → terminal)"
    return out


def _fundamentals_data_as_of(sym: str) -> str | None:
    """Latest raw fundamentals data date for the symbol — the
    provider-data clock, distinct from fundamental_updated_at (the
    scoring clock). Freshest of: the flywheel's last_report_date (the
    earnings report the current analysis actually consumed) and the
    fundamentals_snapshots period. A score recomputed today on a
    5-month-old payload is stale data, not fresh analysis — but a
    one-shot refresh that never writes snapshots shouldn't look stale
    either."""
    try:
        from app.database import db
        fr = db.execute_query(
            "SELECT MAX(d) AS d FROM ("
            "  SELECT last_report_date::date AS d FROM symbol_flywheel"
            "    WHERE symbol=:s AND last_report_date IS NOT NULL"
            "  UNION ALL"
            "  SELECT as_of_date FROM fundamentals_snapshots"
            "    WHERE symbol=:s"
            ") t", {"s": sym})
        if fr and fr[0].get("d"):
            return str(fr[0]["d"])[:10]
    except Exception:
        pass
    return None


def _fv_detail(run_row: dict, spot, fund_as_of=None) -> dict:
    """The scenario ladder with provenance: each target carries the
    per-method contributions and an implied-multiple explanation, so
    'why this number' is reconstructible from the run itself."""
    scen = run_row.get("scenario_fair_values") or {}
    methods = []
    for mr in (run_row.get("method_results") or []):
        if mr.get("status") != "ok" or not mr.get("fair_price"):
            continue
        iu = mr.get("inputs_used") or {}
        mscen = (mr.get("metrics") or {}).get("scenario_fair_values") or {}
        methods.append({
            "key": mr.get("method_key"),
            "w": (mr.get("metrics") or {}).get("blend_weight"),
            "fv": mr.get("fair_price"),
            "scenarios": mscen,
            "explain": _method_explain(mr.get("method_key"), iu, mscen),
        })
    # street targets — context for comparison only; removed from the
    # engine blend in v2.1 so our number stays ours
    analyst = {}
    try:
        from app.database import db
        ar = db.execute_query(
            "SELECT consensus_price_target, price_target_high,"
            " price_target_low, analyst_count, consensus_date"
            " FROM consensus_data WHERE symbol=:s"
            " ORDER BY consensus_date DESC LIMIT 1",
            {"s": run_row["symbol"]})
        if ar:
            analyst = {k: ar[0].get(k) for k in
                       ("consensus_price_target", "price_target_high",
                        "price_target_low", "analyst_count")}
            analyst["as_of"] = str(ar[0].get("consensus_date") or "")
    except Exception:
        pass
    # valuation gate — a blend is decision-grade only when its inputs
    # are fresh AND its methods agree within reason. Stale fundamentals
    # (>120d, past a quarter cycle) or a method >3x away from its peers
    # (split/unit bugs land here) demote the read to needs_validation.
    issues: list[str] = []
    if fund_as_of:
        try:
            age = (date.today()
                   - date.fromisoformat(str(fund_as_of)[:10])).days
            if age > 120:
                issues.append(f"stale_inputs:{age}d")
        except Exception:
            pass
    # pre_earnings blends die by stale balance-sheet inputs — the
    # survival tree prices p_survival off cash/debt/burn, so a name
    # passes the 120d fundamentals gate while its runway math is two
    # months out of date (TEM: 86d-old inputs → $1.10 FV on a $67
    # stock). Inputs-watermark age is the honest clock here.
    reg = str(run_row.get("regime") or "")
    inp = str(run_row.get("inputs_watermark") or "")[:10]
    if "pre_earnings" in reg and inp:
        try:
            iage = (date.today() - date.fromisoformat(inp)).days
            if iage > 45 and not any(
                    i.startswith("stale_inputs") for i in issues):
                issues.append(f"stale_inputs:{iage}d")
        except Exception:
            pass
    # a blend at a fraction of spot is model-vs-market mismatch —
    # diagnostic context, never a trade target; demote like the
    # other validation gates
    if "extreme_gap" in (run_row.get("quality_flags") or []):
        issues.append("extreme_gap")
    fvs = sorted(m["fv"] for m in methods if m.get("fv"))
    if len(fvs) >= 3:
        med = fvs[len(fvs) // 2]
        for m in methods:
            fv = m.get("fv")
            if fv and (fv < med * 0.35 or fv > med * 3):
                m["outlier"] = True
                issues.append(f"outlier_method:{m['key']}")
    # run staleness — the card serves stored runs without resolving, so
    # surface it: >24h old (the resolver's own reuse bound) or built by a
    # different model version (a formula/routing change invalidates the
    # run even when inputs are unchanged — the Oct-18 pre_earnings gate
    # left 434 stale runs untouched for days). The health endpoint fires
    # a background recompute when this is set.
    stale = None
    try:
        from datetime import datetime, timezone
        asof = run_row.get("as_of")
        if isinstance(asof, str):
            asof = datetime.fromisoformat(asof.replace("Z", "+00:00"))
        if asof and asof.tzinfo is None:
            asof = asof.replace(tzinfo=timezone.utc)
        if asof:
            age_h = (datetime.now(timezone.utc)
                     - asof).total_seconds() / 3600
            if age_h > 24:
                stale = f"run_age:{age_h:.0f}h"
    except Exception:
        pass
    if not stale:
        try:
            from app.fair_value_v2.service import FairValueV2Service
            cur = FairValueV2Service().runner.model_version
            if (run_row.get("model_version")
                    and run_row["model_version"] != cur):
                stale = "model_changed"
        except Exception:
            pass
    return {
        "as_of": str(run_row.get("as_of") or "")[:19],
        "inputs_as_of": str(run_row.get("inputs_watermark") or "")[:10]
                        or None,
        "fundamentals_as_of": fund_as_of,
        "spot_at_run": run_row.get("spot_at_run"),
        "regime": run_row.get("regime"),
        "scenarios": scen,
        "expected": run_row.get("expected_fair_value"),
        "flags": run_row.get("quality_flags") or [],
        "spot": spot,
        "methods": methods,
        "analyst": analyst,
        "decision": run_row.get("decision"),
        "stale": stale,
        "valuation_status": "ok" if not issues else "needs_validation",
        "valuation_issues": issues,
    }


def _try_tailwinds(sym: str) -> list:
    try:
        from app.signals import tailwinds as _tw
        return _tw.for_symbol(sym)
    except Exception:
        return []


def _try_lt_power(sym: str) -> dict:
    """Long-duration repricing lens — deterministic; never None-safe
    beyond returning {} on failure."""
    try:
        from app.signals.lt_power import lt_power_for_card
        return lt_power_for_card(sym) or {}
    except Exception:
        return {}


def _try_selloff(sym: str) -> dict:
    """Drawdown attribution for the card — the same classify/score/
    gate/plan the selloff scan runs, evaluated live for this symbol
    on stored data. Falls back to the latest journaled candidate row
    when live eval can't run; {} when there's no selloff to read."""
    try:
        from app.signals import selloff
        return selloff.for_symbol(sym) or {}
    except Exception:
        pass
    try:
        from app.database import db
        r = db.execute_query(
            "SELECT as_of, classification, score, decision, gates,"
            " entry_plan, score_legs, tape, fund"
            " FROM selloff_candidates WHERE symbol=:s"
            " ORDER BY as_of DESC LIMIT 1", {"s": sym.upper()})
        if r:
            out = dict(r[0])
            out["as_of"] = str(out["as_of"])
            out["candidate"] = True
            out["stale"] = True      # journaled scan row, not live
            return out
    except Exception:
        pass
    return {}


def _liq_sensitivity(fly: dict) -> Optional[str]:
    """Per-stock exposure to liquidity tightening — the signal is
    market-wide, sensitivity is per-stock. High-duration names
    (negative FCF, extreme multiple) take the hit first; self-funding
    compounders barely feel it. No fundamental evidence → no tier."""
    try:
        fcf_t, fcf_m, pe = (fly.get("fcf_ttm"), fly.get("fcf_margin"),
                            fly.get("fwd_pe"))
        if fcf_t is None and fcf_m is None and pe is None:
            return None
        if fcf_t is not None and float(fcf_t) < 0:
            return "high"       # cash burn needs external funding
        if pe is not None and float(pe) >= 40:
            return "elevated"   # priced for distant cash flows
        if (fcf_m is not None and float(fcf_m) >= 0.15
                and pe is not None and float(pe) < 25):
            return "low"        # self-funding compounder
        return "moderate"
    except Exception:
        return None


def _try_liquidity(sym: str, fly: dict) -> dict:
    """Market-liquidity context for the card — journaled snapshot +
    this name's sensitivity to it. The same score shows on every
    card; what differs is how exposed THIS name is. Posture context,
    never a stock verdict."""
    try:
        from app.signals import liquidity_engine
        liq = liquidity_engine.read()
        if not liq:
            return {}
        return {"score": liq.get("liquidity_score"),
                "band": liq.get("band"),
                "direction": liq.get("liquidity_direction"),
                "transmission": liq.get("equity_transmission"),
                "as_of": liq.get("as_of"),
                "age_days": liq.get("age_days"),
                "sensitivity": _liq_sensitivity(fly)}
    except Exception:
        return {}


def _try_growth_quality(sym: str) -> dict:
    """Latest growth-quality composite for the card; {} when no run."""
    try:
        from app.signals.growth_quality import card_for
        return card_for(sym) or {}
    except Exception:
        return {}


def _try_fv_v1(sym: str, spot) -> dict:
    """Legacy v1 engine number for side-by-side with the v2 ladder —
    the engine still runs (fundamentals_api blends it) so comparing
    against the stored v2 run is honest diagnostics, not double
    counting. {} when data is insufficient."""
    try:
        from app.services.fair_value_service import FairValueService
        res = FairValueService().calculate_fair_value(sym)
        if not res or not res.fair_value or res.fair_value <= 0:
            return {}
        methods = {}
        for k, v in (res.individual_valuations or {}).items():
            try:
                fv = float(v)
            except Exception:
                continue
            if fv > 0:
                methods[k] = round(fv, 2)
        regime = str(((res.fundamentals or {})
                      .get("data_quality") or {}).get("regime") or "")
        vm = res.valuation_metrics or {}
        out = {"fv": round(float(res.fair_value), 2),
               "regime": regime or None,
               "rating": vm.get("valuation_rating"),
               "methods": methods}
        if spot:
            out["upside_pct"] = round(
                (float(res.fair_value) / spot - 1) * 100, 1)
        return out
    except Exception:
        return {}


def _try_capex(sym: str) -> dict:
    """AI capex-cycle context for the card — this symbol's basket
    exposure against the live engine reading. Display context only;
    the score/flags are owned by the engine, nothing here feeds the
    readiness checklists."""
    try:
        from app.signals import capex_cycle as _cx
        p = _cx.read() or {}
        if not p.get("band"):
            return {}
        return {"score": p.get("score"), "band": p.get("band"),
                "flags": p.get("flags") or [],
                "d3m": p.get("d3m"),
                "exposure": _cx.symbol_exposure(sym),
                "flag": _cx.symbol_flag(sym, p),
                "as_of": str(p.get("as_of") or "")[:19]}
    except Exception:
        return {}


def _try_thesis(sym: str, fv_up=None, mom_state=None) -> dict:
    """Archetype thesis flag — status + direction vs the prior nightly
    eval + which legs just confirmed/refuted + the deterministic
    'like / want confirmed' report. Symbols outside the pilot get a
    lazy first eval via the archetype fallback rules so the card works
    for any tracked name. mom_state feeds the stance's tape clause so
    the thesis verdict never reads as a timing call."""
    import json as _json
    from app.database import db

    def _load() -> dict:
        r = db.execute_query(
            "SELECT archetype, secondary, status, status_dir,"
            " prev_status, status_since, hyp_changes, hypotheses,"
            " score, detail, vetoes, as_of"
            " FROM symbol_thesis WHERE symbol=:s", {"s": sym.upper()})
        return dict(r[0]) if r else {}

    try:
        t = _load()
        if not t:
            from app.signals import thesis_health
            thesis_health.evaluate(sym.upper())
            t = _load()
        if not t:
            return {}
        for k in ("detail", "hypotheses", "hyp_changes", "vetoes"):
            if isinstance(t.get(k), str):
                t[k] = _json.loads(t[k])
        for k in ("as_of", "status_since"):
            if t.get(k) is not None:
                t[k] = str(t[k])
        from app.signals.thesis_health import build_report
        t["report"] = build_report(t, fv_up, mom_state)
        return t
    except Exception:
        return {}


def _try_watches(sym: str) -> list:
    """Open thesis_watches — falsifiable checks a doc extraction set."""
    try:
        from app.database import db
        return [dict(r) for r in db.execute_query(
            "SELECT metric, threshold, horizon, direction, source"
            " FROM thesis_watches WHERE symbol=:s AND status='open'"
            " ORDER BY created_at DESC LIMIT 6", {"s": sym.upper()})]
    except Exception:
        return []


_ORDER = {"ready": 0, "close": 1, "no": 2}


def board() -> dict[str, Any]:
    """Readiness screener — the per-symbol readiness checklist run
    board-wide on stored data (no fresh fetches). Returns each use
    case's list sorted ready → close → no."""
    from app.database import db
    from app.signals import pulse_engine as pe
    today = date.today()
    stocks = [dict(r) for r in db.execute_query(
        "SELECT s.symbol, s.company_name, s.sector, s.momentum_state,"
        " s.momentum_detail, s.momentum_updated_at,"
        " s.fundamental_state, s.priced_status, s.market_cap,"
        " s.revision_grade, s.emerging_growth, s.next_earnings_date,"
        " prev.state AS prev_state"
        " FROM stocks s"
        " LEFT JOIN LATERAL ("
        "   SELECT state FROM momentum_state_log l"
        "   WHERE l.symbol = s.symbol AND l.as_of < CURRENT_DATE"
        "   ORDER BY l.as_of DESC LIMIT 1) prev ON true"
        " WHERE s.momentum_state IS NOT NULL"
        " OR s.fundamental_state IS NOT NULL")]
    fly = {r["symbol"]: dict(r) for r in db.execute_query(
        "SELECT symbol, rev_growth, eps_growth, fwd_pe,"
        " est_revision_pct, beat_streak FROM symbol_flywheel")}
    conv = {r["symbol"]: dict(r) for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, lane, future_score"
        " FROM conviction_snapshots ORDER BY symbol, snap_date DESC")}
    fv = {}
    scen_map = {}
    for r in db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, fair_value,"
            " scenario_fair_values FROM symbol_fair_values"
            " WHERE fair_value IS NOT NULL ORDER BY symbol, as_of DESC"):
        fv[r["symbol"]] = float(r["fair_value"])
        if isinstance(r.get("scenario_fair_values"), dict):
            scen_map[r["symbol"]] = r["scenario_fair_values"]
    px = {r["symbol"]: float(r["close"]) for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, close FROM daily_bars"
        " ORDER BY symbol, date DESC")}
    # strongest active channel per symbol — the ✦ badge on rows
    tw_map = {r["symbol"]: dict(r) for r in db.execute_query(
        "SELECT DISTINCT ON (t.symbol) t.symbol, t.channel, t.tier,"
        " t.direction, t.hit_count FROM tailwinds t"
        " WHERE t.status='active' ORDER BY t.symbol,"
        " CASE t.tier WHEN 'revenue' THEN 0 WHEN 'shipping' THEN 1"
        " WHEN 'announced' THEN 2 ELSE 3 END, t.hit_count DESC")}
    gq_map = {r["symbol"]: dict(r) for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, score, percentile,"
        " components, flags FROM growth_quality_runs"
        " ORDER BY symbol, as_of DESC, id DESC")}
    # archetype-thesis flags — status + direction so screener rows can
    # show ▲/▼/● without a per-symbol lookup
    try:
        th_map = {r["symbol"]: dict(r) for r in db.execute_query(
            "SELECT symbol, status, status_dir, prev_status"
            " FROM symbol_thesis")}
    except Exception:
        th_map = {}
    # sector-flow scores — the industry-group leg of the rank. Same
    # math the pulse board runs on cached sector-ETF bars.
    try:
        from app.api.board_api import _sector_flow_map
        from app.market_regime.rotation import _SECTOR_TO_ETF
        _flow = _sector_flow_map()
    except Exception:
        _flow, _SECTOR_TO_ETF = {}, {}

    import json
    from app.signals import put_entry
    regime = put_entry._regime()
    sections: dict[str, list] = {"swing": [], "invest": [],
                                 "leap_call": [], "leap_put": []}
    latest = None
    skipped: list[str] = []
    for st in stocks:
        s = st["symbol"]
        try:
            det = st.get("momentum_detail") or {}
            if isinstance(det, str):
                det = json.loads(det)
            fv_v, px_v = fv.get(s), px.get(s)
            fv_up = round((fv_v / px_v - 1) * 100, 1) \
                if fv_v and px_v else None
            fl = fly.get(s) or {}
            val = ("extreme" if (fl.get("fwd_pe") or 0) > 60 else
                   "elevated" if (fl.get("fwd_pe") or 0) > 35 else
                   "reasonable" if fl.get("fwd_pe") else None)
            rd = _readiness(st.get("momentum_state"), det,
                            st.get("fundamental_state"), fl,
                            {}, conv.get(s) or {}, fv_up, val,
                            {"pe": put_entry.score(
                                det, st.get("momentum_state"),
                                st.get("fundamental_state"), fl,
                                scen_map.get(s) or {}, px_v, regime)},
                            gq_map.get(s), st.get("priced_status"))
            upd = st.get("momentum_updated_at")
            if upd and (latest is None or str(upd) > str(latest)):
                latest = str(upd)
            twr = tw_map.get(s)
            catalyst = (f"✦{twr['channel']}({twr['tier']},"
                        f"{twr['hit_count']}src)" if twr else None)
            # rank ctx — normalized + stage0 once per symbol. The
            # checklist is the binary gate; rank is the continuous order
            # the planner deploys capital by. leap_put ranks by its
            # put-entry score (already 0-100).
            gq = gq_map.get(s) or {}
            prev = st.get("prev_state")
            cur = st.get("momentum_state")
            _rk_c = pe._normalize({
                "mom_state": cur,
                "fund_state": st.get("fundamental_state"),
                "revision_grade": st.get("revision_grade"),
                "priced_status": st.get("priced_status"),
                "fv_upside": fv_up,
                "emerging_growth": st.get("emerging_growth"),
                "earn_days": ((st["next_earnings_date"] - today).days
                              if st.get("next_earnings_date") else None),
                "tape_dir": ("improving" if prev and cur != prev
                             and cur in ("pullback", "recovery", "basing",
                                         "uptrend", "breakout")
                             else "flat"),
                "momentum_detail": det,
                "px": px_v,
                "gq_pct": gq.get("percentile"),
                "beat_streak": fl.get("beat_streak"),
                "est_revision_pct": fl.get("est_revision_pct"),
                "sector_score": _flow.get(
                    _SECTOR_TO_ETF.get((st.get("sector") or "").lower(),
                                       "SPY"), {}).get("score")})
            _rk_c.update(pe._stage0(_rk_c))
            for key in sections:
                r = rd[key]
                _rk = ({"rank": r["score"], "parts": {"put_entry":
                            {"raw": r["score"], "norm": r["score"]}}}
                       if key == "leap_put" else pe.rank(key, _rk_c))
                fails = [x["line"] for x in r["rules"] if not x["ok"]]
                _sw = det.get("swing") if isinstance(det, dict) else None
                # jsonb is free-form — a string/list swing value would
                # 500 the whole board on .get; only dict carries levels
                _sw = _sw if isinstance(_sw, dict) else {}
                sections[key].append({
                    "symbol": s, "name": st.get("company_name"),
                    "state": r["state"], "score": r["score"],
                    "of": r["of"], "fails": fails,
                    "rank": _rk["rank"], "parts": _rk["parts"],
                    "mom": st.get("momentum_state"),
                    # swing structure as first-class fields — so the
                    # board can filter confirmed / higher_low-forming /
                    # broken names directly, not just inside a check line
                    "swing_phase": _sw.get("phase"),
                    "confirm_level": _sw.get("confirm_level"),
                    "avwap": _sw.get("avwap"),
                    "prior_low": _sw.get("prior_low"),
                    "fund": st.get("fundamental_state"),
                    "thesis": (th_map.get(s) or {}).get("status"),
                    "thesis_dir": (th_map.get(s) or {}).get("status_dir"),
                    "fv_upside": fv_up,
                    "mcap_b": round((st.get("market_cap") or 0) / 1e9, 1),
                    "catalyst": catalyst,
                    "pe_band": r.get("band"), "pe_cat": r.get("category"),
                    "stage_txt": r.get("stage_txt"),
                })
        except Exception as exc:
            # one corrupt row must not 500 the whole board — skip the
            # symbol, log the failure (the custodian code-bug rule sees
            # it in the tail), and surface the skipped list in the
            # payload so the page can warn
            logger.warning("readiness row skipped %s: %r", s, exc)
            skipped.append(s)
    for key in sections:
        # ready-first, then continuous rank desc — symbol is the
        # final tiebreak only. Checklist score no longer orders
        # inside `ready` (it ties at max for every eligible name).
        sections[key].sort(key=lambda r: (_ORDER.get(r["state"], 3),
                                          -(r["rank"] or 0),
                                          r["symbol"]))
    # journal every eval — first write of the day wins per
    # rules_version. readiness_evals is the transitions feed + the
    # training substrate for the use-case checklists.
    try:
        from app.signals import pulse_engine
        rv, en = pulse_engine.rules_version(), pulse_engine.ENGINE_VERSION
        db.execute_many(
            "INSERT INTO readiness_evals (symbol, as_of, use_case,"
            " state, score, of, fails, mom, fund, rank, parts,"
            " rules_version, engine_version)"
            " VALUES (:s, CURRENT_DATE, :u, :st, :sc,"
            " :of, CAST(:f AS jsonb), :m, :fn, :rk,"
            " CAST(:pt AS jsonb), :rv, :en)"
            " ON CONFLICT (symbol, as_of, use_case, rules_version)"
            " DO NOTHING",
            [{"s": r["symbol"], "u": key, "st": r["state"],
              "sc": r["score"], "of": r["of"],
              "f": json.dumps(r["fails"]), "m": r["mom"],
              "fn": r["fund"], "rk": r["rank"],
              "pt": json.dumps(r["parts"], default=str),
              "rv": rv, "en": en}
             for key, rows in sections.items() for r in rows])
    except Exception:
        pass
    return {"as_of": latest, "sections": sections,
            "skipped": skipped,
            "counts": {k: {s: sum(1 for r in v if r["state"] == s)
                           for s in ("ready", "close", "no")}
                       for k, v in sections.items()}}
