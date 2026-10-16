"""Per-stock health card — one read that composes what every engine
already persists. Not a new scorer: the aggregator surfaces the
three axes side by side and synthesizes the verdict — especially the
CONFLICTS no single flag shows (fundamentals accelerating + tape
knife = 'watch, don't catch the knife').
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)


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
    expensive = valuation == "extreme"

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
    st = db.execute_query(
        "SELECT symbol, company_name, sector, market_cap,"
        " momentum_state, momentum_detail, momentum_updated_at,"
        " fundamental_state, fundamental_detail, fundamental_risk,"
        " fundamental_updated_at,"
        " revision_score, revision_grade, priced_status,"
        " emerging_growth, fwd_detail,"
        " next_earnings_date, rating, price_target"
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
        " beat_streak, est_revision_pct, fwd_pe, gap_score,"
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

    val = gem.get("valuation") or (
        "extreme" if (fly.get("fwd_pe") or 0) > 60 else
        "elevated" if (fly.get("fwd_pe") or 0) > 35 else
        "reasonable" if fly.get("fwd_pe") else "unknown")
    verdict = _verdict(st.get("fundamental_state"),
                       st.get("momentum_state"), val,
                       conv.get("future_score"), conv.get("lane"))

    # fair-value upside vs latest close — the valuation leg of the
    # readiness checks (post-ADR normalization); scenario FVs + spot
    # feed PUT_ENTRY's bull-case-distance asymmetry
    fv_up, scen, spot = None, {}, None
    fv_detail = {}
    try:
        r = db.execute_query(
            "SELECT symbol, fair_value, scenario_fair_values,"
            " expected_fair_value,"
            " quality_flags, regime, method_results, decision, as_of"
            " FROM fair_value_v2_runs WHERE symbol=:s"
            " ORDER BY as_of DESC LIMIT 1", {"s": s})
        p = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s"
            " ORDER BY date DESC LIMIT 1", {"s": s})
        if r and p and r[0]["fair_value"] and p[0]["close"]:
            fv_up = round((float(r[0]["fair_value"]) /
                           float(p[0]["close"]) - 1) * 100, 1)
        if p and p[0]["close"]:
            spot = float(p[0]["close"])
        sc = (r[0].get("scenario_fair_values") if r else None)
        if isinstance(sc, dict):
            scen = sc
        if r:
            fv_detail = _fv_detail(r[0], spot)
    except Exception:
        pass

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
        from app.api.board_api import _sector_flow_map, _SECTOR_TO_ETF
        from app.market_regime.rotation import SECTOR_NAMES
        _etf = _SECTOR_TO_ETF.get((st.get("sector") or "").lower())
        if _etf:
            _m = _sector_flow_map().get(_etf)
            sector_flow = {"etf": _etf, "name": SECTOR_NAMES.get(_etf),
                           "flow": (_m or {}).get("flow"),
                           "score": (_m or {}).get("score")}
    except Exception:
        pass

    return {"symbol": s, "name": st.get("company_name"),
            "sector": st.get("sector"),
            "sector_flow": sector_flow,
            "market_cap": st.get("market_cap"),
            "spot": spot,
            "next_earnings": (str(st.get("next_earnings_date"))
                              if st.get("next_earnings_date") else None),
            "verdict": verdict,
            "fundamental": {"state": st.get("fundamental_state"),
                            "risk": st.get("fundamental_risk"),
                            "as_of": (str(st.get("fundamental_updated_at"))
                                      if st.get("fundamental_updated_at")
                                      else None),
                            "detail": fdet},
            "technical": {"state": st.get("momentum_state"),
                          "as_of": (str(st.get("momentum_updated_at"))
                                    if st.get("momentum_updated_at")
                                    else None),
                          "detail": det},
            "growth": fly,
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
            "readiness": readiness,
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


def _fv_detail(run_row: dict, spot) -> dict:
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
    return {
        "as_of": str(run_row.get("as_of") or "")[:19],
        "regime": run_row.get("regime"),
        "scenarios": scen,
        "expected": run_row.get("expected_fair_value"),
        "flags": run_row.get("quality_flags") or [],
        "spot": spot,
        "methods": methods,
        "analyst": analyst,
        "decision": run_row.get("decision"),
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
    # sector-flow scores — the industry-group leg of the rank. Same
    # math the pulse board runs on cached sector-ETF bars.
    try:
        from app.api.board_api import _sector_flow_map, _SECTOR_TO_ETF
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
