"""Daily Action Board — the "what do I do TODAY" surface.

Moto: fear → deploy cash into quality dips; greed → take profits.
Target: $100k book, ~$5k/month. This board ranks the day's top ~10
actions — exits first (protect), then accumulates (deploy) — by
combining every persisted signal we already compute:

  tape/posture   VIX + SPY-vs-200dma + regime card (permission, size×)
  exits          open swing trades (monitor flags) + LEAPS book alerts
  accumulate     momentum flag × fundamentals (RB/5x tier, gap score,
                 beat streak) × swing-screen readiness × alert tailwind

Pure read-time synthesis — NO new provider calls except one tiny
yf pull for SPY+^VIX (the posture). Nothing executes; every row is a
suggestion with its evidence chain attached.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ENTRY_SETUPS = {"first_pullback", "mean_reversion", "breakout",
                 "breakout_retest"}
# capex-cycle baskets — mirrored from signals/capex_cycle.py so the
# board can tag exposure without importing the heavy module per row
_NEW_BUILD_SYMS = ["VRT", "ETN", "CRDO", "ALAB", "ONTO", "NVDA", "AVGO",
                   "MU"]
_OPERATOR_SYMS = ["IREN", "NBIS", "APLD", "CRWV", "EQIX", "MSFT",
                  "AMZN", "GOOGL", "ORCL"]

# momentum → accumulate base weight. bearish states excluded entirely
# (they can't be accumulate candidates — that's the flag's job).
_MOM_ACC = {"pullback": 30, "recovery": 22, "breakout": 18,
            "basing": 12, "uptrend": 5}
_MOM_WATCH = {"capitulation"}          # deep wash — starter only w/ strong funds
_MOM_EXIT = {"climax": 30, "breakdown": 30, "knife": 25,
             "rolling_over": 20, "downtrend": 15}


def _tape() -> dict[str, Any]:
    """SPY trend + VIX — the fear/greed posture. One small yf call."""
    try:
        import yfinance as yf
        d = yf.download("SPY ^VIX", period="1y", interval="1d",
                        group_by="ticker", progress=False,
                        auto_adjust=True)
        spy = d["SPY"]["Close"].dropna()
        vix_s = d["^VIX"]["Close"].dropna()
        px = float(spy.iloc[-1])
        sma200 = float(spy.iloc[-200:].mean())
        vix = float(vix_s.iloc[-1])
        vix_prev = float(vix_s.iloc[-6:-1].mean()) if len(vix_s) > 6 else vix
        return {"spy": round(px, 2), "spy_vs_200": round(px / sma200 - 1, 4),
                "spy_1d": round(px / float(spy.iloc[-2]) - 1, 4),
                "spy_5d": round(px / float(spy.iloc[-6]) - 1, 4),
                "vix": round(vix, 1),
                "vix_rising": vix > vix_prev * 1.05}
    except Exception as exc:
        logger.debug("tape fetch failed: %s", exc)
        return {}


def _posture(tape: dict, regime: Optional[dict]) -> dict[str, Any]:
    """The fear/greed dial. Fear deploys cash (into quality dips only);
    greed harvests. Market regime decides aggression, not symbols."""
    env = (regime or {}).get("swing_environment") or {}
    perm = env.get("long_permission") or "unknown"
    mult = env.get("size_multiplier") or 1.0
    vix, vs200 = tape.get("vix"), tape.get("spy_vs_200")
    s1d, s5d = tape.get("spy_1d"), tape.get("spy_5d")
    broken = vs200 is not None and vs200 < 0
    # fear = panic vol OR a genuinely red tape week inside an intact
    # trend — "buy on red days" only holds above the 200dma
    fear = (vix is not None and vix >= 20) or (
        not broken and ((s5d or 0) <= -0.02 or (s1d or 0) <= -0.015))
    greed = (vix is not None and vix < 15) and not broken

    if broken and perm == "blocked":
        stance, note = "DEFENSIVE", ("tape broken + entries blocked — "
                                     "protect book, no new cash")
    elif fear and not broken:
        why = ("VIX ≥20 — panic pricing" if vix and vix >= 20
               else f"red tape (SPY {s5d * 100:+.1f}%/5d) with the "
                    "200dma intact — the dip-buy window")
        stance, note = "FEAR — DEPLOY", (f"{why}; fear is paying you to "
                                         "buy quality dips, in tranches")
    elif broken:
        stance, note = "DEFENSIVE", ("SPY below 200dma — entries half-size "
                                     "or less; exits take priority")
    elif greed:
        stance, note = "GREED — HARVEST", ("calm tape (VIX<15) — lean "
                                           "toward trims/profit-taking over "
                                           "fresh entries")
    else:
        stance, note = "NEUTRAL", ("no extreme either way — play the "
                                   "individual setups")
        if tape.get("vix_rising"):
            note += " — VIX creeping up: prefer tranches over full size"
    _inner = (regime or {}).get("regime_detail") or {}
    rd = {k: _inner.get(k, (regime or {}).get(k)) for k in
          ("condition", "direction", "confidence", "key_drivers",
           "transition_stage", "dip_buying_environment",
           "bullish_transition_score", "interpretation",
           "strategies_preferred", "risk_level")}
    # universe breadth + book risk — stored by the momentum job, free
    try:
        from app.signals import breadth as _br
        breadth = _br.read() or None
    except Exception:
        breadth = None
    try:
        from app.signals import book_risk as _bk
        book = _bk.read() or None
    except Exception:
        book = None
    try:
        from app.signals import geo_context as _geo
        geo = _geo.read() or None
    except Exception:
        geo = None
    try:                                # 20-session forward probabilities
        from app.market_regime.forward import forward_probs
        forward = forward_probs({**rd, "spy_vs_200": vs200}, breadth, geo,
                                vix=vix,
                                vix_rising=bool(tape.get("vix_rising")))
    except Exception:
        forward = None
    try:                                # AI capex-cycle engine
        from app.signals import capex_cycle as _cx
        capex = _cx.read() or None
    except Exception:
        capex = None
    try:                                # dip character — deleveraging
        from app.market_regime.dip_character import classify as _dip
        dip_char = _dip()               # vs rotation vs AI-led
    except Exception:
        dip_char = None
    try:                                # allocation — cash buffer +
        from app.market_regime.allocation import plan as _alloc
        alloc = _alloc(dip_char, forward, vix)   # rotate-to sectors
    except Exception:
        alloc = None
    try:                                # hedge book — insurance state
        from app.options import hedge_book as _hb
        hedge = _hb.state()              # coverage vs regime target
    except Exception:
        hedge = None
    try:                                # crash alpha — put entries +
        from app.options import crash_alpha as _ca
        crash = _ca.state()              # capitulation + PUT→CALL link
    except Exception:
        crash = None
    try:                                # macro event-day judge —
        from app.signals import event_day as _ed
        ev_call = _ed.snapshot() or _ed.read_call()
        event_day = ({**ev_call,
                      "record": _ed.record().get(
                          (ev_call or {}).get("event_kind") or "")}
                     if ev_call else None)
    except Exception:
        event_day = None
    try:                                # morning regime — the daily
        from app.database import db as _db
        import json as _j
        _mr = _db.execute_query(
            "SELECT regime, ai_regime, score, confidence, buckets, "
            "llm, verdict, horizon_1m, horizon_3m "
            "FROM morning_regime_snapshots "
            "ORDER BY as_of DESC LIMIT 1")
        if _mr:
            for _k in ("buckets", "verdict", "llm",
                       "horizon_1m", "horizon_3m"):
                v = _mr[0].get(_k)
                if isinstance(v, str):
                    try:
                        _mr[0][_k] = _j.loads(v)
                    except Exception:
                        pass
            morning = _mr[0]
        else:
            morning = None
    except Exception:
        morning = None
    return {"stance": stance, "note": note, "vix": vix,
            "spy_vs_200": vs200, "spy_1d": s1d, "spy_5d": s5d,
            "permission": perm,
            "size_multiplier": mult,
            "breadth": breadth, "book_risk": book,
            "geo": geo, "forward": forward, "capex": capex,
            "dip_character": dip_char, "allocation": alloc,
            "hedge": hedge, "crash_alpha": crash,
            "event_day": event_day, "morning": morning,
            "regime": (regime or {}).get("regime"),
            "regime_detail": {k: v for k, v in rd.items()
                              if v is not None},
            "as_of": (regime or {}).get("as_of")}


def _latest_screen() -> dict[str, dict]:
    """Latest swing-scan results keyed by symbol (entry setups, ready
    flags) — persisted in screen_runs, free to read."""
    from app.database import db
    rows = db.execute_query(
        "SELECT results FROM screen_runs ORDER BY ran_at DESC LIMIT 1")
    if not rows:
        return {}
    res = rows[0].get("results")
    items = res.get("items") if isinstance(res, dict) else res
    return {it["symbol"]: it for it in items or []}


def _accumulate_scores() -> list[dict[str, Any]]:
    """Score every tracked symbol for the deploy side."""
    from app.database import db
    mom = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, momentum_state, momentum_detail,"
        " next_earnings_date FROM stocks "
        "WHERE momentum_state IS NOT NULL")}
    fw = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, gap_score, beat_streak, est_revision_pct, "
        "muted_reaction, fwd_pe, rev_growth, rev_accel "
        "FROM symbol_flywheel")}
    rb = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, tier FROM rule_breaker_members")}
    sc = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, tier FROM smallcap_members")}
    alerts = {r["symbol"]: r for r in db.execute_query(
        """SELECT DISTINCT ON (symbol) symbol, direction, materiality
           FROM alert_items WHERE created_at > now() - interval '72 hours'
           ORDER BY symbol, created_at DESC""")}
    fh = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, fundamental_state, fundamental_risk,"
        " fundamental_detail FROM stocks"
        " WHERE fundamental_state IS NOT NULL")}
    try:
        gqm = {r["symbol"]: dict(r) for r in db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, percentile, flags"
            " FROM growth_quality_runs WHERE percentile IS NOT NULL"
            " ORDER BY symbol, as_of DESC, id DESC")}
    except Exception:
        gqm = {}
    try:
        from app.signals.focus_intel import fresh_boosts, members
        focus = fresh_boosts()
        focus_syms = set(members())
    except Exception:
        focus, focus_syms = {}, set()
    screen = _latest_screen()
    # execution-phase binding — the strategy engine's calendar gates
    # this board: phase-2 freeze dims entry-ready names to advisory,
    # phase-3 flags names gapped on peer misses as reactive-deploy
    phase = peer_drag = None
    try:
        from app.portfolio_strategy import engine as strategy
        phase = strategy.active_phase()
        peer_drag = strategy.peer_drag_symbols(phase) or set()
    except Exception:
        phase, peer_drag = None, set()
    try:                                        # AI capex-cycle regime
        from app.signals import capex_cycle as _cx_mod
        capex_ctx = _cx_mod.read() or {}
    except Exception:
        capex_ctx = {}
    _NEW_BUILD = set(_NEW_BUILD_SYMS)
    _OPERATORS = set(_OPERATOR_SYMS)

    out = []
    for sym, m in mom.items():
        state = m["momentum_state"]
        base = _MOM_ACC.get(state)
        det = m.get("momentum_detail") or {}
        # wounded-winner test: deep oversold + trend hurt — needs the
        # fundamentals leg (fund>=12) to be a BOUNCE, not a knife-catch
        oversold = (det.get("rsi") is not None and det["rsi"] <= 32) \
            or (det.get("pct_b") is not None and det["pct_b"] <= 0.05)
        is_bounce = state in _MOM_WATCH or \
            (state in {"downtrend", "knife"} and oversold)
        if base is None and not is_bounce:
            continue                       # bearish/neutral → not a buy
        score, why = 0.0, []
        f = fw.get(sym) or {}
        fund_h = fh.get(sym) or {}
        fstate = fund_h.get("fundamental_state")
        if fstate == "deteriorating":
            continue            # broken company getting cheaper ≠ a dip —
        tier = (rb.get(sym) or {}).get("tier")
        sc_tier = (sc.get(sym) or {}).get("tier")
        fund = 0.0
        if tier:
            fund += {"confirmed": 20, "emerging": 14}.get(tier, 7)
            why.append(f"RB {tier}")
        if sc_tier:
            fund += {"runner": 15, "inflecting": 10}.get(sc_tier, 5)
            why.append(f"5x {sc_tier}")
        rg = f.get("rev_growth")
        ra = f.get("rev_accel")
        if rg is not None:
            why.append(f"rev {rg * 100:+.0f}% YoY"
                       + (f" {'accel' if ra > 0 else 'decel'} "
                          f"{ra * 100:+.0f}pts" if ra is not None else ""))
            if ra is not None and ra > 0.10:
                fund += 5            # accelerating growth bonus
            elif ra is not None and ra < -0.20:
                fund -= 5            # decelerating penalty
        if f.get("gap_score"):
            fund += min(15, f["gap_score"] / 5)
            why.append(f"gap {f['gap_score']:.0f}")
        if f.get("beat_streak"):
            fund += min(8, f["beat_streak"] * 1.5)
            why.append(f"{f['beat_streak']}q beats")
        g = gqm.get(sym)
        if g:
            if (g.get("percentile") or 0) >= 75:
                fund += 4
                why.append(f"growth-quality p{g['percentile']:.0f}")
            elif "fcf_negative" in (g.get("flags") or []):
                fund -= 4
                why.append("gq: fcf-negative")
        if f.get("muted_reaction"):
            fund += 6
            why.append("muted reaction")
        if sym in focus_syms:
            fund += 4                    # conviction book — watched on
            why.append("focus book")     # its own merits, not screen mercy
        fe = focus.get(sym)
        if fe:
            fund += 8                    # fresh material development ≤72h
            why.append(f"🎯 {fe['event_type'].replace('_', ' ')} "
                       f"— {fe['title'][:60]}")
        # fundamental health flag — the fundamental axis next to the
        # tape flag; deterioration penalizes, acceleration rewards
        if fstate:
            fund += {"accelerating": 8, "growing": 3, "slowing": -6,
                     "declining": -20, "watch": 0, "cyclical": 0,
                     "turnaround": 2, "pressured": -8,
                     "unknown": 0}.get(fstate, 0)
            why.append(f"fund {fstate}")
            fa = (fund_h.get("fundamental_detail") or {}).get("alert")
            if fa in {"warning", "critical"}:
                why.append(f"⚠️ fundamentals {fa}")
        strong_fund = fund >= 12
        if is_bounce and not strong_fund:
            continue                       # oversold alone isn't a buy —
                                         # without the fundamentals leg
                                         # it's just a cheaper knife
        if is_bounce:
            score += 15                    # starter-size only
            why.append(f"mom {state}"
                       + (f" rsi {det['rsi']:.0f}" if det.get("rsi") else "")
                       + " — wounded winner, starter size / call spread")
        else:
            score += base
            why.append(f"mom {state}")
        # dip phase — direction of travel inside the dip: a pullback
        # whose lows are rising and histogram healing is resolving up;
        # one still printing lower lows is becoming a knife.
        dip = det.get("dip_phase")
        # learned weights — the swing pilot's trade journal can soften
        # or harden these defaults as it proves/disproves each phase
        try:
            from app.signals.swing_pilot import weight
            _dadj = {"turning_up": 6, "stabilizing": 2,
                     "still_falling": -8}
            _w = weight(f"dip:{dip}") if dip else None
            if isinstance(_w, dict) and "adj" in _w:
                _dadj[dip] = _w["adj"]
            _g = weight(f"gate:{state}|{dip or 'none'}")
            if isinstance(_g, dict) and _g.get("enabled") is False:
                score -= 10
                why.append("pilot gate OFF — this pattern loses money")
        except Exception:
            _dadj = {"turning_up": 6, "stabilizing": 2,
                     "still_falling": -8}
        if dip == "turning_up":
            score += _dadj[dip]
            why.append("dip turning up "
                       f"(health {det.get('dip_health', '?')}/5)")
        elif dip == "stabilizing":
            score += _dadj[dip]
            why.append("dip stabilizing")
        elif dip == "still_falling":
            score += _dadj[dip]
            why.append("dip still falling — early, starter only"
                       + (f" (learned {_dadj[dip]})"
                          if _dadj[dip] != -8 else ""))
        # swing structure — the higher-low read: did the stock carve a
        # low ABOVE the prior pivot low, and has it proven it by
        # reclaiming the pullback's counter-swing high?
        sw = det.get("swing") or {}
        swp = sw.get("phase")
        if swp == "confirmed":
            score += 8
            why.append(f"higher low confirmed — reclaimed "
                       f"${sw.get('confirm_level')} "
                       f"(low ${sw.get('swing_low')} > "
                       f"${sw.get('prior_low')})")
        elif swp == "higher_low":
            score += 4
            why.append(f"higher low forming ${sw.get('swing_low')} > "
                       f"${sw.get('prior_low')} — confirm >"
                       f" ${sw.get('confirm_level')}")
        elif swp == "broken":
            score -= 8
            why.append(f"swing structure broken — low "
                       f"${sw.get('swing_low')} under prior "
                       f"${sw.get('prior_low')}")
        # relative strength — the leadership tell: a higher low on an
        # 80+ RS name is a leader resting; the same pattern on a <35
        # name is a laggard. rs_nh = outperforming while the tape dips.
        rs_pct, rs_nh = det.get("rs_pct"), det.get("rs_nh")
        if rs_pct is not None:
            if rs_pct >= 80:
                score += 5
                why.append(f"RS {rs_pct} — leader resting")
            elif rs_pct <= 35 and state in {"pullback", "basing",
                                            "recovery"}:
                score -= 5
                why.append(f"RS {rs_pct} — laggard, not a dip")
        if rs_nh:
            score += 4
            why.append("RS line at 60d high while market corrects")
        # earnings proximity — a swing into the print is a coin flip,
        # not an edge; flag it loud rather than silently veto
        days_to_er = None
        _ed = m.get("next_earnings_date")
        if _ed:
            try:
                days_to_er = (_ed if isinstance(_ed, date)
                              else date.fromisoformat(str(_ed)[:10])
                              ) - date.today()
                days_to_er = days_to_er.days
            except Exception:
                days_to_er = None
        if days_to_er is not None:
            if days_to_er <= 5:
                score -= 12
                why.append(f"⚠️ earnings in {days_to_er}d — binary "
                           "event, not a swing edge")
            elif days_to_er <= 12:
                score -= 5
                why.append(f"earnings in {days_to_er}d — size down or "
                           "wait for the print")
        # AI capex-cycle exposure — new-build equipment beta gets
        # discounted when the capex engine flags a slowdown regime;
        # operators/lifecycle names get the rotation benefit. This is a
        # capital-allocation nudge, never a sell signal.
        _cx = capex_ctx or {}
        cx_flags = set(_cx.get("flags") or [])
        cx_score = _cx.get("score")
        # monetization leg distinguishes WHY capex is slowing:
        #   benign (<50)  = discipline — rev keeps pace, FCF story,
        #                   operators benefit from rotation
        #   sick (>=60)   = demand failure — operators are leveraged
        #                   derivatives of the spend being cut
        cx_mon = ((_cx.get("components") or {}).get("monetization")
                  or {}).get("score")
        cx_demand_fail = cx_mon is not None and cx_mon >= 60
        cx_flag = None
        if cx_score is not None and cx_flags:
            if sym in _NEW_BUILD:
                if "CAPEX_SLOWDOWN_ACTIVE" in cx_flags or \
                        "CAPEX_CONTRACTION" in cx_flags:
                    score -= 6
                    cx_flag = "capex-beta"
                    why.append(f"🏗 capex-beta — engine "
                               f"{_cx.get('band')} {cx_score} slowing")
                elif cx_flags & {"CAPEX_SLOWDOWN_WARNING",
                                 "CAPEX_EARLY_WARNING"}:
                    score -= 3
                    cx_flag = "capex-watch"
                    why.append(f"capex watch ({cx_score}) — build "
                               "beta under review")
            elif sym in _OPERATORS and (
                    "CAPEX_SLOWDOWN_ACTIVE" in cx_flags
                    or "CAPEX_CONTRACTION" in cx_flags):
                if cx_demand_fail:
                    score -= 4
                    cx_flag = "capex-derivative"
                    why.append(f"🏗 order-book risk — slowdown is "
                               f"demand-failure (monetization "
                               f"{cx_mon:.0f}); operator revenue IS "
                               f"the capex being cut")
                else:
                    score += 4
                    cx_flag = "rotation-candidate"
                    why.append("capex rotation candidate — discipline"
                               " slowdown favors lifecycle/FCF "
                               "names" + (f" (monetization {cx_mon:.0f})"
                                         if cx_mon is not None else ""))
        # empirical prior — how this same (state, dip_phase) setup paid
        # on THIS stock historically; pooled fallback when the symbol's
        # own sample is thin. Priors nudge, never decide.
        try:
            from app.signals.pattern_priors import prior_for
            pr = prior_for(sym, f"{state}|{dip or 'none'}")
        except Exception:
            pr = None
        if pr:
            if pr["hit_rate_10d"] >= 0.6 and pr["med_ret_10d"] >= 0.04:
                score += 6
            elif pr["hit_rate_10d"] <= 0.35:
                score -= 6
            why.append(
                f"prior: {round(pr['hit_rate_10d'] * pr['n'])}"
                f"/{pr['n']} similar setups → "
                f"{pr['med_ret_10d'] * 100:+.0f}% median/10d"
                + ("" if pr["scope"] == "symbol" else " (pooled)"))
        score += fund
        si = screen.get(sym) or {}
        entry_ready = (si.get("setup_type") in _ENTRY_SETUPS
                       and si.get("stock_permission")
                       in ("allowed", "limited")
                       and (si.get("score") or 0) >= 60)
        if entry_ready:
            score += 15
            why.append(f"swing {si['setup_type']} ready")
        elif si.get("turn_candidate"):
            score += 8
            why.append("turn candidate")
        a = alerts.get(sym)
        if a:
            if a["direction"] == "POSITIVE" and a["materiality"] == "HIGH":
                score += 8
                why.append("positive catalyst")
            elif a["direction"] == "NEGATIVE" and a["materiality"] == "HIGH":
                score -= 12
                why.append("NEGATIVE catalyst — check before buying")
        if score <= 0:
            continue
        instrument = ("LEAPS call" if state in {"pullback", "recovery",
                                                "breakout"}
                      and strong_fund else "stock")
        # LEAPS zone plan — a pullback isn't "buy now," it's a map.
        # From the stored swing structure: watch the low→prior-low
        # shelf, deeper adds only at the prior low; reclaiming the
        # counter-swing high / AVWAP with volume = repair confirmed.
        levels = None
        if instrument == "LEAPS call" and isinstance(sw, dict):
            pl, sl = sw.get("prior_low"), sw.get("swing_low")
            av, cf = sw.get("avwap"), sw.get("confirm_level")
            if pl and sl:
                levels = {"watch": [round(pl, 2), round(sl, 2)],
                          "reclaim": round(av or cf or 0, 2),
                          "confirm": round(cf, 2) if cf else None}
        entry_status = ("ready" if entry_ready else
                        "watch_zone" if instrument == "LEAPS call"
                        else None)
        if phase:
            pn = phase.get("n")
            if pn == 2 and entry_status == "ready":
                entry_status = "frozen"
                why.append(f"❄️ execution freeze — entry gate passed "
                           f"but phase-2 ({phase.get('name','')[:30]}) "
                           "holds fire until the cluster")
            elif pn == 3 and sym in (peer_drag or set()):
                entry_status = "peer_drag"
                score += 10
                why.append("🎯 peer-drag — down with a cluster-mate's "
                           "print, not its own news; reactive-deploy "
                           "flag (verify it didn't report itself)")
        out.append({"symbol": sym,
                    "action": "BOUNCE" if is_bounce else "ACCUMULATE",
                    "score": round(score, 1), "momentum": state,
                    "instrument": instrument, "why": why,
                    "entry_status": entry_status,
                    "levels": levels,
                    "dip_phase": det.get("dip_phase"),
                    "dip_health": det.get("dip_health"),
                    "swing": det.get("swing"),
                    "rs_pct": rs_pct, "rs_nh": bool(rs_nh),
                    "days_to_earnings": days_to_er,
                    "capex_flag": cx_flag,
                    "prior": pr,
                    "fund_state": fstate,
                    "fund_risk": fund_h.get("fundamental_risk"),
                    "fund_changes": (fund_h.get("fundamental_detail")
                                     or {}).get("changes") or [],
                    "price": si.get("price"), "entry": si.get("entry"),
                    "stop": si.get("stop"), "target": si.get("target"),
                    "in_portfolio": bool(si.get("in_portfolio"))})
    return sorted(out, key=lambda r: -r["score"])


def _short_scores() -> list[dict[str, Any]]:
    """PUT candidates — peaking names with a FRESH momentum crack.

    Doctrine: puts pay on high-multiple cyclicals rolling over, NOT on
    structural growers still accelerating (extension alone ≠ shortable;
    deterioration must be visible). breakdown = late, climax = watch."""
    from app.database import db
    mom = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, momentum_state, momentum_detail,"
        " next_earnings_date FROM stocks "
        "WHERE momentum_state IS NOT NULL")}
    fw = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, fwd_pe, rev_accel FROM symbol_flywheel")}
    rb = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, tier FROM rule_breaker_members")}
    cycl = {r["symbol"]: True for r in db.execute_query(
        "SELECT symbol FROM stocks WHERE cyclical")}
    fh = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, fundamental_state FROM stocks"
        " WHERE fundamental_state IS NOT NULL")}
    out = []
    for sym, m in mom.items():
        state = m["momentum_state"]
        if state not in {"rolling_over", "breakdown", "climax"}:
            continue
        d = m.get("momentum_detail") or {}
        f = fw.get(sym) or {}
        score, why = 0.0, []
        score += {"rolling_over": 30, "breakdown": 18,
                  "climax": 12}[state]
        why.append(f"mom {state}"
                   + (" — fresh crack" if state == "rolling_over"
                      else " — late, smaller size" if state == "breakdown"
                      else " — extended, no crack yet (watch put)"))
        ext = d.get("vs_sma200")
        if ext is not None and ext > 0.40:
            score += 6
            why.append(f"+{ext * 100:.0f}% vs 200dma — stretched")
        pe = f.get("fwd_pe")
        if pe and pe >= 40:
            score += 8
            why.append(f"fwd P/E {pe:.0f} — multiple is the fuel")
        ra = f.get("rev_accel")
        if ra is not None and ra < -0.05:
            score += 8
            why.append(f"growth decel {ra * 100:+.0f}pts — deterioration"
                       " visible")
        if cycl.get(sym):
            score += 8
            why.append("cyclical — extension fades are its habit")
        fst = (fh.get(sym) or {}).get("fundamental_state")
        if fst in {"declining", "deteriorating"}:
            score += 10
            why.append(f"fund {fst} — deterioration confirms the crack")
        if (rb.get(sym) or {}).get("tier") == "confirmed" \
                and ra is not None and ra > 0:
            score -= 15                     # don't short accelerating
            why.append("RB confirmed + accelerating — shorting "
                       "strength is how puts die")
        if score < 25:
            continue
        out.append({"symbol": sym, "action": "PUT",
                    "score": round(score, 1), "momentum": state,
                    "instrument": "LEAPS put",
                    "why": why})
    return out


def _exit_rows(open_trades: list[dict], leaps_book: list[dict],
               mom: dict) -> list[dict[str, Any]]:
    """Held positions ranked by exit urgency."""
    out = []
    for tr in open_trades:
        flags = set(tr.get("flags") or [])
        sym = tr["symbol"]
        state = (mom.get(sym) or {}).get("momentum_state")
        score, why = 0.0, []
        if flags & {"STOP_HIT", "TRAIL_STOP", "REGIME_FLIP"}:
            score += 40
            why.append("/".join(sorted(flags & {"STOP_HIT", "TRAIL_STOP",
                                                "REGIME_FLIP"})))
        if flags & {"CLIMAX", "T1_HIT", "GAIN_100", "GAIN_50"}:
            score += 25
            why.append("/".join(sorted(flags & {"CLIMAX", "T1_HIT",
                                                "GAIN_100", "GAIN_50"})))
        if (tr.get("gain_pct") or 0) >= 25:
            score += 10
            why.append(f"+{tr['gain_pct']:.0f}% open gain")
        if state in _MOM_EXIT:
            score += _MOM_EXIT[state]
            why.append(f"mom {state}")
        if not score:
            continue
        action = "EXIT" if score >= 40 else "TRIM"
        out.append({"symbol": sym, "action": action,
                    "score": round(score + (tr.get("gain_pct") or 0) / 5,
                                   1),
                    "momentum": state, "instrument": "stock (held)",
                    "gain_pct": tr.get("gain_pct"),
                    "suggestion": tr.get("suggestion"), "why": why,
                    "in_portfolio": True})
    for p in leaps_book:
        sym = p["symbol"]
        state = (mom.get(sym) or {}).get("momentum_state")
        alert = p.get("exit_alert")
        if not alert and state not in _MOM_EXIT:
            continue
        score = 45 if alert else _MOM_EXIT.get(state, 0)
        why = [alert] if alert else [f"mom {state}"]
        out.append({"symbol": sym, "action": "EXIT" if alert else "TRIM",
                    "score": score, "momentum": state,
                    "instrument": f"{p['side']} {p.get('strike')} "
                                  f"{str(p.get('expiry') or '')[:10]}",
                    "gain_pct": p.get("pnl_pct"),
                    "why": why, "in_portfolio": True})
    return out


async def build_board(max_items: int = 10) -> dict[str, Any]:
    """Assemble the day's board — exits first, then deploys."""
    from app.database import db
    from app.alerts import service as alert_service

    regime = alert_service.regime_card()
    tape = _tape()
    posture = _posture(tape, regime)

    # open swing trades evaluated against their plans (same monitor the
    # screener page uses — reuses its price fetch)
    open_trades: list[dict] = []
    try:
        from app.trades import service as trade_service
        from app.market_data.service import MarketDataService
        open_trades = await trade_service.monitor_open_trades(
            MarketDataService())
    except Exception as exc:
        logger.debug("trade monitor unavailable: %s", exc)

    leaps_book = db.execute_query(
        "SELECT stock_symbol AS symbol, side, strike, expiry, "
        "exit_alert, unrealized_pct AS pnl_pct "
        "FROM leaps_positions WHERE status = 'open'")
    mom = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, momentum_state FROM stocks "
        "WHERE momentum_state IS NOT NULL")}

    exits = _exit_rows(open_trades, leaps_book, mom)
    accum = _accumulate_scores()
    puts = _short_scores()

    # posture shapes the mix: FEAR boosts deploys, GREED boosts exits,
    # DEFENSIVE halves accumulate scores and favours the short side
    # (puts are how you get paid when the tape won't let you buy)
    if posture["stance"].startswith("GREED"):
        for r in accum:
            r["score"] = round(r["score"] * 0.6, 1)
        for r in exits:
            r["score"] = round(r["score"] * 1.2, 1)
    elif posture["stance"].startswith("FEAR"):
        for r in accum:
            r["score"] = round(r["score"] * 1.15, 1)
        for r in puts:
            r["score"] = round(r["score"] * 1.1, 1)
    elif posture["stance"] == "DEFENSIVE":
        for r in accum:
            r["score"] = round(r["score"] * 0.5, 1)
        for r in puts:
            r["score"] = round(r["score"] * 1.2, 1)

    # held symbols already have an exit row — don't double-list as buys;
    # a symbol can't be both an accumulate and a put either
    held = {r["symbol"] for r in exits}
    accum = [r for r in accum if r["symbol"] not in held]
    acc_syms = {r["symbol"] for r in accum}
    puts = [r for r in puts
            if r["symbol"] not in held | acc_syms]

    # reserve lanes: exits and puts always surface if they exist —
    # with 100+ accumulate candidates the short side would never show
    board = (sorted(exits, key=lambda r: -r["score"])[:5]
             + sorted(puts, key=lambda r: -r["score"])[:3]
             + sorted(accum, key=lambda r: -r["score"]))
    board = board[:max_items]

    equity = db.execute_query(
        "SELECT account_equity FROM portfolio_account_states "
        "ORDER BY as_of DESC LIMIT 1")
    eq = float(equity[0]["account_equity"]) if equity else 100000.0
    tranche = round(eq * 0.02 * (posture["size_multiplier"] or 1.0))

    try:
        from app.signals.focus_intel import recent_events
        focus_devs = recent_events(days=5, min_mat=3)[:14]
    except Exception:
        focus_devs = []

    result = {"posture": posture, "items": board,
            "equity": eq, "suggested_tranche": tranche,
            "focus": focus_devs,
            "counts": {"exits": len(exits), "accumulate": len(accum),
                       "accumulate_ready": sum(
                           1 for r in accum
                           if r.get("entry_status") == "ready"),
                       "accumulate_watch": sum(
                           1 for r in accum
                           if r.get("entry_status") == "watch_zone"),
                       "frozen": sum(
                           1 for r in accum
                           if r.get("entry_status") == "frozen"),
                       "peer_drag": sum(
                           1 for r in accum
                           if r.get("entry_status") == "peer_drag"),
                       "puts": len(puts)},
            "as_of": datetime.now(timezone.utc).isoformat(
                timespec="seconds")}

    # journal the day's picks — idempotent; this is how the board
    # learns (evaluate_pending grades them at 5/10/20d)
    try:
        from app.signals.board_tracking import (
            snapshot_board, snapshot_regime)
        snapshot_board(result)
        snapshot_regime(result.get("posture"))     # regime versioning
    except Exception as exc:
        logger.debug("board snapshot failed: %s", exc)
    return result
