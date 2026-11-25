"""Session-tape entry & accumulation — staged entries, not BUY/WAIT.

Three separate questions kept separate per the spec:

  market stability   can we take a SMALL position?  (0-100, from
                     market_stability readings — the tape, not the
                     stock)
  stock accumulation is THIS stock accumulating vs just bouncing
                     with the market? (0-100, per-symbol 5m tape +
                     SBD fundamental leg)
  entry state        how much of the INTENDED position now?
                     starter → add → build → complete, and it can
                     stop at any stage — the remainder is never
                     forced.

The two mistakes the rules exist to prevent: waiting for perfect
confirmation and missing the rebound, or buying while sell pressure
is still active. Plus: a lower price is not automatically a better
entry — a deteriorating business blocks accumulation at any price.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ----------------- market stability score (spec §1A weights) ---------
_MSS_WEIGHTS = {"qqq_vwap": 20, "smh_vwap": 20, "vix": 15,
                "breadth": 15, "ai_leadership": 15, "credit": 15}


def market_stability_score(rd: dict) -> dict[str, Any]:
    """0-100 from journaled raw readings — same raws, no refetch.
    Missing legs renormalize + coverage disclosed."""
    legs: dict[str, Optional[int]] = {}

    m = rd.get("qqq_minutes_above_vwap")
    held = bool(rd.get("qqq_vwap_held"))
    legs["qqq_vwap"] = (90 if held and m >= 120 else
                       75 if m is not None and m >= 90 else
                       60 if m is not None and m >= 45 else
                       40 if m is not None and m > 0 else
                       (20 if m == 0 else None))
    sm = rd.get("smh_minutes_above_vwap")
    legs["smh_vwap"] = (80 if sm is not None and sm >= 90 else
                       65 if sm is not None and sm >= 45 else
                       40 if sm is not None and sm > 0 else
                       (20 if sm == 0 else None))
    vchg = rd.get("vix_chg_open_pct")
    vtr = rd.get("vix_intraday_trend_pct")
    if vchg is not None or vtr is not None:
        easing = (vchg is not None and vchg < -3) or \
                 (vtr is not None and vtr < -1)
        flat = (vchg is not None and -3 <= vchg <= 3)
        legs["vix"] = 85 if easing else 60 if flat else 30
    b = rd.get("breadth_adv_pct")
    legs["breadth"] = (90 if b is not None and b >= 70 else
                       75 if b is not None and b >= 55 else
                       55 if b is not None and b >= 45 else
                       30 if b is not None else None)
    ai = (rd.get("ai_leadership") or {}).get("pct_green")
    legs["ai_leadership"] = (85 if ai is not None and ai >= 75 else
                            70 if ai is not None and ai >= 50 else
                            35 if ai is not None else None)
    cr = rd.get("credit_etfs_chg_open_pct") or {}
    cvals = [v for v in cr.values() if isinstance(v, (int, float))]
    if cvals:
        mn = sum(cvals) / len(cvals)
        legs["credit"] = 80 if mn > 0.2 else 60 if mn >= -0.1 else 30

    scored = {k: v for k, v in legs.items() if v is not None}
    wsum = sum(_MSS_WEIGHTS[k] for k in scored)
    score = (round(sum(scored[k] * _MSS_WEIGHTS[k] for k in scored)
                   / wsum) if wsum else None)
    return {"market_stability_score": score, "legs": legs,
            "coverage": round(wsum / sum(_MSS_WEIGHTS.values()), 2)
            if scored else 0.0}


# ----------------- stock accumulation score (spec §1B) ----------------

def _retests(bars: list[dict], vwap: float) -> int:
    """Successful VWAP retests: dipped to within 0.3% of VWAP from
    above, then closed back above — buyers absorbing the pullback."""
    if len(bars) < 4:
        return 0
    n = 0
    i = 0
    while i < len(bars) - 2:
        b = bars[i]
        if b["c"] > vwap:
            j = i + 1
            touched = False
            while j < len(bars) and bars[j]["c"] > vwap * 0.995:
                if bars[j]["l"] <= vwap * 1.003:
                    touched = True
                j += 1
            if touched and j < len(bars):
                n += 1
            i = j
        else:
            i += 1
    return n


def _higher_lows(bars: list[dict]) -> int:
    """Count of ascending 5m-bar swing lows in the session."""
    if len(bars) < 7:
        return 0
    lows = [b["l"] for b in bars]
    pivots = [lows[i] for i in range(2, len(lows) - 2)
              if lows[i] <= min(lows[i - 2:i] + lows[i + 1:i + 3])]
    return sum(1 for a, b in zip(pivots, pivots[1:]) if b > a)


def _vol_character(bars: list[dict]) -> Optional[float]:
    """Share of volume on UP bars — buying volume vs sell volume."""
    up = sum(b["v"] for b in bars if b["c"] >= b["o"])
    tot = sum(b["v"] for b in bars)
    return up / tot if tot else None


def stock_accumulation(sym: str, bars: list[dict], qqq_chg: Optional[float],
                       smh_chg: Optional[float], cand: dict
                       ) -> dict[str, Any]:
    """Per-candidate 0-100 — the bounce-vs-accumulation distinction.
    cand = the selloff scan row; its sbd/bucket fields supply the
    fundamental leg (already scored, no refetch)."""
    raw: dict[str, Any] = {"symbol": sym}
    if not bars:
        raw.update(score=None, note="no intraday bars")
        return raw

    last = bars[-1]["c"]
    first = bars[0]["o"]
    chg_open = last / first - 1 if first else None
    vw = None
    pv = sum(((b["h"] + b["l"] + b["c"]) / 3) * b["v"] for b in bars)
    tv = sum(b["v"] for b in bars)
    if tv:
        vw = pv / tv
    min_above = sum(5 for b in bars if vw and b["c"] > vw) \
        if vw else None
    fails = 0
    if vw:
        was = bars[0]["c"] > vw
        for b in bars[1:]:
            now = b["c"] > vw
            if now and not was:
                was = True
            elif was and not now:
                fails += 1
                was = False
    retests = _retests(bars, vw) if vw else 0
    hl = _higher_lows(bars)
    hi = max(b["h"] for b in bars)
    lo = min(b["l"] for b in bars)
    close_loc = (last - lo) / (hi - lo) if hi > lo else None
    vshare = _vol_character(bars)

    raw.update(chg_open_pct=round(chg_open * 100, 2)
               if chg_open is not None else None,
               vwap=round(vw, 2) if vw else None,
               minutes_above_vwap=min_above,
               failed_reclaims=fails, successful_retests=retests,
               higher_lows=hl,
               close_location=round(close_loc, 2)
               if close_loc is not None else None,
               up_vol_share=round(vshare, 2) if vshare else None,
               rs_qqq=(round((chg_open - qqq_chg) * 100, 2)
                       if chg_open is not None
                       and qqq_chg is not None else None),
               rs_smh=(round((chg_open - smh_chg) * 100, 2)
                       if chg_open is not None
                       and smh_chg is not None else None))

    # ---- score — 100 pts across the spec's legs -------------------
    legs = {}
    rq = raw.get("rs_qqq")
    legs["rs_qqq"] = (90 if rq is not None and rq >= 2 else
                      75 if rq is not None and rq >= 0.5 else
                      55 if rq is not None and rq >= 0 else
                      30 if rq is not None else None)          # 15
    rs_ = raw.get("rs_smh")
    legs["rs_sector"] = (85 if rs_ is not None and rs_ >= 1 else
                         65 if rs_ is not None and rs_ >= 0 else
                         35 if rs_ is not None else None)      # 10
    if min_above is not None:
        persist = (90 if min_above >= 120 and fails <= 1 else
                   75 if min_above >= 90 else
                   60 if min_above >= 45 else
                   35 if min_above > 0 else 15)
        persist -= min(20, fails * 5)       # failed reclaims dock it
        legs["vwap_persistence"] = max(10, persist)             # 25
    else:
        legs["vwap_persistence"] = None
    legs["retests"] = (90 if retests >= 2 else 70 if retests == 1
                       else 40)                                  # 10
    legs["structure"] = (85 if hl >= 2 else 65 if hl == 1
                         else 40)                                # 10
    cl = raw.get("close_location")
    legs["close_location"] = (85 if cl is not None and cl >= 0.7 else
                             65 if cl is not None and cl >= 0.5 else
                             35 if cl is not None else None)     # 10
    legs["volume"] = (85 if vshare is not None and vshare >= 0.6 else
                      65 if vshare is not None and vshare >= 0.5 else
                      40 if vshare is not None and vshare >= 0.4 else
                      25 if vshare is not None else None)        # 10
    bh = (cand.get("dimensions") or {}).get("business_health")
    bb = cand.get("business_bucket")
    legs["fundamental"] = (85 if isinstance(bh, (int, float))
                           and bh >= 75 else
                           65 if isinstance(bh, (int, float))
                           and bh >= 55 else
                           40 if bb in ("deteriorating",
                                        "severely_impaired") else
                           50)                                   # 10
    W = {"rs_qqq": 15, "rs_sector": 10, "vwap_persistence": 25,
         "retests": 10, "structure": 10, "close_location": 10,
         "volume": 10, "fundamental": 10}
    scored = {k: v for k, v in legs.items() if v is not None}
    wsum = sum(W[k] for k in scored)
    raw["stock_accumulation_score"] = (
        round(sum(scored[k] * W[k] for k in scored) / wsum)
        if wsum else None)
    raw["legs"] = legs
    raw["coverage"] = round(wsum / 100, 2)
    raw["day_low"] = lo
    raw["last"] = last
    return raw


# ---------------------- entry state machine --------------------------

# allocation bands per state — of the INTENDED position, per spec §2
_ALLOC = {"early_stabilization": (10, 20),
          "intraday_confirmation": (20, 30),
          "multi_session_confirmation": (25, 35),
          "recovery_confirmed": (15, 25)}

_BLOCKED_SBD = ("beat_down_business", "structural_risk")


def entry_state(cand: dict, acc: dict, mss: Optional[int],
                stable_sessions: Optional[int],
                stability_label: Optional[str]) -> dict[str, Any]:
    """state + allocation% + explicit add/invalidation conditions —
    or a blocked/no-entry verdict with the reason. Never forces the
    remaining allocation."""
    sym = cand.get("symbol")
    sas = acc.get("stock_accumulation_score")
    sbd_cls = ((cand.get("sbd") or {}).get("class"))

    # ---- hard guards ------------------------------------------------
    if sbd_cls in _BLOCKED_SBD or cand.get("decision") == "reject":
        return {"symbol": sym, "entry_state": "blocked",
                "suggested_action": "no_entry",
                "reason": f"{sbd_cls or cand.get('decision')} — "
                          "a lower price is not a better entry when "
                          "the business is deteriorating",
                "confidence": "high"}
    if sas is None or mss is None:
        return {"symbol": sym, "entry_state": "insufficient_evidence",
                "suggested_action": "wait",
                "reason": "missing intraday tape or stability read",
                "confidence": "low"}

    # ---- missed-move protection (spec §7) ---------------------------
    off_low = ((acc["last"] / acc["day_low"] - 1)
               if acc.get("last") and acc.get("day_low") else None)
    retest = (acc.get("successful_retests") or 0) >= 1 \
        or (acc.get("higher_lows") or 0) >= 1
    extended = off_low is not None and off_low >= 0.08

    # ---- states -----------------------------------------------------
    state = None
    # 4 — recovery confirmed: structure + resistance break + hold
    if (stable_sessions or 0) >= 2 and sas >= 70 and mss >= 70 \
            and retest and (acc.get("close_location") or 0) >= 0.6:
        state = "recovery_confirmed"
    # 3 — multi-session: constructive closes + credit not worsening
    elif (stable_sessions or 0) >= 2 and sas >= 60 and mss >= 60:
        state = "multi_session_confirmation"
    # 2 — intraday confirmed: holds VWAP through retest + volume
    elif (mss >= 65 and sas >= 60 and retest
          and (acc.get("up_vol_share") or 0) >= 0.5
          and (acc.get("minutes_above_vwap") or 0) >= 60):
        state = "intraday_confirmation"
    # 1 — early stabilization: tape improving + stock holds + RS
    elif (mss >= 55 and sas >= 50
          and (acc.get("rs_qqq") or -99) >= 0
          and (acc.get("minutes_above_vwap") or 0) >= 30
          and (stability_label or "") in ("stable", "stabilizing",
                                         "mixed")):
        state = "early_stabilization"

    # tactical-only: weak market, exceptional stock RS — small starter
    tactical = (state is None and sas is not None and sas >= 70
                and (acc.get("rs_qqq") or 0) >= 2
                and mss < 55)

    if state is None and not tactical:
        return {"symbol": sym, "entry_state": "wait",
                "suggested_action": "no_entry_yet",
                "market_stability_score": mss,
                "stock_accumulation_score": sas,
                "reason": "tape not confirming accumulation — "
                          "either market still weak or stock just "
                          "bouncing with it",
                "confidence": "moderate"}

    if state is None and tactical:
        state = "early_stabilization"
        band = (5, 10)                  # tactical cap — smaller than
    else:                                # the standard starter band
        band = _ALLOC[state]

    if extended and not retest:
        return {"symbol": sym, "entry_state": state,
                "suggested_action": "consolidate_wait",
                "suggested_allocation_pct": 0,
                "market_stability_score": mss,
                "stock_accumulation_score": sas,
                "reason": f"+{round(off_low * 100, 1)}% off session "
                          "low without a retest — don't chase; add "
                          "on consolidation or a higher low",
                "confidence": "moderate"}

    lo, hi = band
    alloc = round((lo + hi) / 2)
    add_conditions, invalid = _conditions(state, acc)
    conf = ("high" if state == "recovery_confirmed"
            else "moderate" if sas >= 65 and mss >= 65 else "low")
    return {"symbol": sym,
            "entry_state": state,
            "suggested_action":
                "starter_position" if state == "early_stabilization"
                else "add" if state in ("intraday_confirmation",
                                        "multi_session_confirmation")
                else "complete_position",
            "suggested_allocation_pct": alloc,
            "allocation_band": list(band),
            "market_stability_score": mss,
            "stock_accumulation_score": sas,
            "add_conditions": add_conditions,
            "invalidation_conditions": invalid,
            "confidence": conf,
            "reason": _reason(state, acc, mss, stable_sessions)}


def _conditions(state: str, acc: dict) -> tuple[list, list]:
    nxt = {"early_stabilization": "intraday_confirmation",
           "intraday_confirmation": "multi_session_confirmation",
           "multi_session_confirmation": "recovery_confirmed",
           "recovery_confirmed": None}.get(state)
    adds = {
        "early_stabilization": [
            "hold VWAP through another retest",
            "maintain relative strength vs SMH",
            "close in the upper part of the daily range",
            "next session forms a higher low"],
        "intraday_confirmation": [
            "two consecutive constructive closes or higher lows",
            "credit stops worsening (HY/IG flatten)",
            "stock holds the recovery level overnight"],
        "multi_session_confirmation": [
            "higher low + break of session/week resistance",
            "breakout retest holds",
            "sector relative strength still improving"],
        "recovery_confirmed": []}
    inv = ["sustained VWAP failure",
           "new session low with expanding sell volume",
           "material negative fundamental development"]
    return adds.get(state, []) if nxt else [], inv


def _reason(state: str, acc: dict, mss: Optional[int],
            sess: Optional[int]) -> str:
    m = acc.get("minutes_above_vwap")
    rs = acc.get("rs_qqq")
    base = {"early_stabilization":
            "market stabilizing; stock holding VWAP with positive "
            "RS — early entry accepted, retest risk acknowledged",
            "intraday_confirmation":
            "VWAP held through a retest with buying volume — the "
            "accumulation attempt is confirmed intraday",
            "multi_session_confirmation":
            f"{sess}+ constructive sessions — conviction add, not "
            "the cheapest price",
            "recovery_confirmed":
            "structure + breakout + retest holding — complete the "
            "intended position"}.get(state, "")
    detail = []
    if m is not None:
        detail.append(f"{m}m above VWAP")
    if rs is not None:
        detail.append(f"RS {rs:+.1f}% vs QQQ")
    return f"{base} ({'; '.join(detail)})" if detail else base


# ------------------------- run over candidates ------------------------

def evaluate_candidates(cands: list[dict], raw: dict,
                        stability_rd: dict) -> dict[str, Any]:
    """Score every non-reject selloff candidate against today's tape.
    raw = intraday bars keyed by symbol (must include QQQ/SMH)."""
    from app.signals.intraday_pulse import _day_stats
    qq = _day_stats(raw.get("QQQ") or [])
    sm = _day_stats(raw.get("SMH") or [])
    qqq_chg = qq.get("chg_open")
    smh_chg = sm.get("chg_open")
    mss = market_stability_score(stability_rd)
    out = {"market_stability_score": mss["market_stability_score"],
           "mss_legs": mss["legs"], "entries": {}}
    sess = stability_rd.get("stable_sessions")
    lbl = stability_rd.get("stability_label")
    for c in cands:
        if c.get("decision") == "reject":
            continue
        sym = c.get("symbol")
        acc = stock_accumulation(sym, raw.get(sym) or [],
                                 qqq_chg, smh_chg, c)
        out["entries"][sym] = entry_state(c, acc, mss
                                        ["market_stability_score"],
                                        sess, lbl)
        out["entries"][sym]["accumulation"] = {
            k: acc.get(k) for k in
            ("minutes_above_vwap", "failed_reclaims",
             "successful_retests", "higher_lows", "close_location",
             "up_vol_share", "rs_qqq", "rs_smh",
             "chg_open_pct")}
    return out
