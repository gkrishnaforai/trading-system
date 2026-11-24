"""Equity posture — the "what do I do with cash" synthesis.

Composed on read from three already-journaled legs:

  stance   — valuation x earnings environment rating
             (index_valuation_daily; is the backdrop paid?)
  alarms   — correction character + action bias; the selloff
             diagnosis (correction_evals): is current weakness a
             buyable dip or a structural break?
  fed      — path_3_6m lean (fed_predictions): the tide. Easing
             lifts risk assets; tightening fights every rally.

The trader's order of operations: character first. If the selloff's
diagnosis is earnings recession or credit stress, nothing else
matters — that is when dips keep dipping. If weakness is buyable
(positioning flush, no structural alarm), the stance + fed decide
whether "buy the dip" is constructive, selective, or a trap.

Derived verdict — inputs are journaled, so composing on read needs
no schema and stays consistent with whatever was presented.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def _p(key: str, tone: str, headline: str, why: str) -> Dict[str, str]:
    label = {"constructive": "Constructive",
             "dip_buyer": "Buy the dip",
             "selective": "Selective",
             "hold": "Hold",
             "build_cash": "Build cash",
             "raise_cash": "Raise cash"}[key]
    return {
        "posture": key,
        "posture_label": label,
        "posture_tone": tone,
        "posture_headline": headline,
        "posture_detail": why,
    }


def compose(stance: Optional[str] = None,
            alarms: Optional[Dict[str, Any]] = None,
            fed: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """stance: 'favorable'|'leaning_favorable'|'neutral'|
    'leaning_unfavorable'|'unfavorable'. alarms: correction_alarms
    latest() — uses action.bias + character. fed: fed_path.read() —
    uses path_3_6m.lean."""
    bias = char = sev = None
    if alarms:
        bias = (alarms.get("action") or {}).get("bias")
        char = alarms.get("correction_character")
        sev = alarms.get("severity")
    fed_lean = ((fed or {}).get("path_3_6m") or {}).get("lean")
    st = stance
    why = (f"stance:{st or '—'} + alarm:{(char or 'none').replace('_', ' ')}"
           f"/{(bias or '—').replace('_', ' ')}"
           f" + fed:{(fed_lean or '—').replace('_', ' ')}")

    # 1. character gate — the selloff diagnosis dominates everything
    if bias == "sell":
        return _p("raise_cash", "bad",
                  "Selloff is structural — raise cash into bounces",
                  why)
    if bias == "slow_buys":
        return _p("build_cash", "bad",
                  "Earnings or credit deteriorating — build cash; "
                  "don't initiate", why)
    if bias == "hold":
        return _p("hold", "warn",
                  "Stress unresolved — pause new buys, re-check "
                  "when it stops worsening", why)

    # 2. dip is buyable (accumulate* / none) — modulate stance x fed.
    # _priced leans mean the move is already in the front end — still
    # the same direction for posture purposes.
    tight = fed_lean in ("tightening_bias", "tightening_priced")
    easy = fed_lean in ("easing_bias", "easing_priced")
    if st == "unfavorable":
        return _p("build_cash", "bad",
                  "Weak backdrop — use rallies to build cash", why)
    if st == "leaning_unfavorable":
        if tight:
            return _p("build_cash", "warn",
                      "Weak-leaning backdrop and the fed tightening — "
                      "trim into strength", why)
        return _p("selective", "warn",
                  "Backdrop tilts weak — dips in quality names "
                  "only", why)
    if st == "neutral" or not st:
        if tight:
            return _p("selective", "warn",
                      "Dip is buyable but the fed is a headwind — "
                      "selective sizes only", why)
        if easy:
            return _p("dip_buyer", "ok",
                      "Dip is buyable and the fed is easing — "
                      "stage adds on weakness", why)
        return _p("hold", "warn",
                  "Mixed backdrop, no structural alarm — patience "
                  "beats chasing", why)
    # favorable / leaning_favorable
    if tight:
        return _p("selective", "warn",
                  "Good backdrop but the fed is a headwind — size "
                  "adds smaller", why)
    if easy:
        return _p("constructive", "ok",
                  "Fundamentals support and the fed is at your "
                  "back — add on weakness", why)
    return _p("dip_buyer", "ok",
              "Weakness is the opportunity — stage adds into "
              "the dip", why)


_TONE_SC = {"ok": 1, "warn": 0, "bad": -1}
_TAPE_DIR = {
    "aligned": 1, "buyers_in_control": 1,
    "watch_reversal": 0.5, "sellers_exhausting": 0.5,
    "narrow_fragile": -0.5, "fragile": -0.5,
    "sellers_regaining": -1, "tape_breaking": -1, "defensive": -1,
}
_DIR_LABEL = [
    (3, ("Upward", "ok")),
    (1, ("Leaning up", "ok")),
    (-1, ("Sideways", "warn")),
    (-2, ("Leaning down", "warn")),
    (-9, ("Downward", "bad")),
]
_DIR_WORD = {
    "Upward": "a constructive tape — fundamentals and rates aligned",
    "Leaning up": "mildly constructive — the setup tilts higher",
    "Sideways": "a mixed tape — no dominant direction; range chop "
                "until a leg resolves",
    "Leaning down": "pressure near-term — weak tape or headwinds "
                    "outweigh the fundamental case",
    "Downward": "defensive — multiple legs against equities; "
                "rallies are suspect",
}


def compose_direction(valuation=None, posture=None, rates=None,
                      alarms=None, intraday=None):
    """The heading — where stocks are pointed, near-term.

    Weighted vote across the three journaled verdicts plus the live
    tape and alarm severity; the note names what would flip it —
    so 'down' always carries its upside catalyst and 'up' its risk."""
    st_tone = (valuation or {}).get("stance_tone")
    po_tone = (posture or {}).get("posture_tone")
    rt_tone = (rates or {}).get("rates_tone")
    rt_dir = (rates or {}).get("rates_direction")
    sev = (alarms or {}).get("severity")
    char = ((alarms or {}).get("correction_character")
            or "none").replace("_", " ")
    tape_state = (intraday or {}).get("state")

    if st_tone is None and rt_tone is None:
        return {}
    base = (sum(_TONE_SC.get(t, 0)
                for t in (st_tone, po_tone, rt_tone))
            + _TAPE_DIR.get(tape_state or "", 0))
    if sev == "alarm":
        base -= 2
    elif sev == "warning":
        base -= 1

    label = tone = None
    for thresh, (lab, tn) in _DIR_LABEL:
        if base >= thresh:
            label, tone = lab, tn
            break
    word = _DIR_WORD[label]

    # the flip catalyst — what changes this read
    notes = []
    if rt_dir == "cooling" and label in ("Sideways", "Leaning down",
                                         "Downward"):
        notes.append("upside if hike odds keep unwinding")
    if rt_dir == "reheating" and label in ("Upward", "Leaning up",
                                           "Sideways"):
        notes.append("downside risk: reheating inflation")
    if sev in ("warning", "alarm") and label != "Downward":
        notes.append(f"downside trigger: {char} escalating")
    if label in ("Upward", "Leaning up") and not notes:
        notes.append("risk: positioning squeeze if tape stalls")

    detail = (f"stance:{(valuation or {}).get('stance') or '—'} + "
              f"posture:{(posture or {}).get('posture') or '—'} + "
              f"rates:{rt_dir or '—'} + tape:{tape_state or '—'} + "
              f"alarm:{char}/{sev or 'none'}"
              f" → score {base:+.1f}")
    return {
        "direction": label.lower().replace(" ", "_"),
        "direction_label": label,
        "direction_tone": tone,
        "direction_headline": word + (
            (" — " + "; ".join(notes)) if notes else ""),
        "direction_detail": detail,
    }


# ---- horizon ladder -------------------------------------------------
# The same evidence means different things at different scales; each
# horizon draws only on legs that predict at that scale, and each is
# journaled so it can be graded on its own clock (next-day verifies
# fast, months accrue the slow track record).

def _fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compose_outlook(intraday=None, fragility=None, valuation=None,
                    rates=None, alarms=None, regime=None,
                    fed=None) -> dict:
    """Three horizons, each from the legs that predict at that scale:

    next_day    tape state + journaled base rates + fragility
                continuation/exhaustion 1d + the forecast legs
    weeks_1_2   leverage-cycle phase + second-leg risk + exhaustion +
                fragility 5d/10d probabilities — mechanical risk,
                the horizon where forced selling lives
    months_1_3  equity rating + rates direction + regime + fed lean —
                valuation/earnings/rates are the only legs with any
                business predicting months out
    """
    out: dict = {}

    # ---- next day ---------------------------------------------------
    tape = (intraday or {}).get("state")
    br = (intraday or {}).get("base_rate") or {}
    fc = (intraday or {}).get("forecast") or {}
    probs = (fragility or {}).get("probabilities") or {}

    def _p(fam: str, h: str):
        return _fnum((probs.get(fam) or {}).get(h))

    score = _TAPE_DIR.get(tape or "", 0)
    ev: list[str] = []
    if tape:
        ev.append(f"tape {tape.replace('_', ' ')}")
    nm = _fnum(br.get("next_median"))
    if nm is not None:
        score += 1 if nm > 0 else -1
        ev.append(
            f"{br.get('n')} prior sessions ending "
            f"{(br.get('state') or '').replace('_', ' ')} → "
            f"next-day med {nm * 100:+.1f}%")
    cont1, exh1 = _p("continuation", "1d"), _p("exhaustion", "1d")
    if cont1 is not None and exh1 is not None:
        if cont1 - exh1 >= 0.05:
            score -= 0.5
        elif exh1 - cont1 >= 0.05:
            score += 0.5
        ev.append(f"fragility 1d cont {cont1 * 100:.0f}% · "
                  f"exh {exh1 * 100:.0f}%")
    pcg = _fnum(fc.get("prob_close_green"))
    if pcg is not None:
        score += (pcg - 0.5) * 2
        ev.append(f"close-green {pcg * 100:.0f}%")
    fw = ((intraday or {}).get("eval") or {}).get("forced_watch") or {}
    nw = fw.get("n")
    if nw and nw >= 2:
        # warnings stack against tomorrow — 2 checks = mild drag,
        # 5 = the full forced-unwind footprint
        score -= min(nw - 1, 3) * 0.5
        ev.append(f"forced-watch {nw}/5 "
                  f"({(fw.get('verdict') or '').replace('_', ' ')})")
    if not ev:
        nd = None
    else:
        nd = ("leaning_up" if score >= 1 else
              "leaning_down" if score <= -1 else "mixed")
    out["next_day"] = {
        "verdict": nd, "score": round(score, 2),
        "tone": "ok" if nd == "leaning_up" else
                "bad" if nd == "leaning_down" else "warn",
        "evidence": ev}

    # ---- 1-2 weeks --------------------------------------------------
    lc = (fragility or {}).get("leverage_cycle") or {}
    phase = lc.get("phase")
    sld = ((fragility or {}).get("second_leg_down") or {}).get("risk")
    exh_s = _fnum(((fragility or {}).get("exhaustion") or {})
                  .get("score"))
    vuln = _fnum((fragility or {}).get("vulnerability"))
    band = (fragility or {}).get("band")
    sev = (alarms or {}).get("severity")
    char = ((alarms or {}).get("correction_character")
            or "").replace("_", " ")
    wk, wtone = None, None
    if sld == "HIGH" or phase == "firing":
        wk, wtone = "vulnerable", "bad"
    elif phase == "discharging" and (exh_s or 0) >= 40:
        wk, wtone = "stabilizing", "warn"
    elif phase in ("discharging", "discharged"):
        wk, wtone = "discharging", "warn"
    elif vuln is not None and vuln >= 60:
        wk, wtone = "fragile", "bad"
    elif vuln is not None and vuln >= 40:
        wk, wtone = "elevated", "warn"
    elif vuln is not None:
        wk, wtone = "calm", "ok"
    wev = []
    if vuln is not None:
        wev.append(f"fragility {vuln:.0f} {band or ''}".strip())
    if phase:
        wev.append(f"leverage {phase}")
    if sld:
        wev.append(f"second-leg {str(sld).lower()}")
    if exh_s is not None:
        wev.append(f"exhaustion {exh_s:.0f}")
    if char:
        wev.append(f"{char} {sev or ''}".strip())
    out["weeks"] = {"verdict": wk, "tone": wtone, "evidence": wev}

    # ---- 1-3 months --------------------------------------------------
    _RATING_SC = {"favorable": 2, "leaning_favorable": 1, "neutral": 0,
                  "leaning_unfavorable": -1, "unfavorable": -2}
    _RATE_SC = {"cooling": 1, "reheating": -1}
    _REGIME_SC = {"strong_risk_on": 2, "risk_on": 1, "neutral": 0,
                  "risk_off": -1, "stress": -2,
                  "bull_low_vol": 1, "bull_high_vol": 1, "bull": 1,
                  "bullish_correction": 0.5, "transition": 0,
                  "distribution": -1, "distribution_risk": -1,
                  "bear": -2, "macro_risk_off": -1}
    _FED_SC = {"easing_priced": 1, "easing_bias": 1, "hold": 0,
               "tightening_bias": -1, "tightening_priced": -1}
    rating = (valuation or {}).get("stance")
    rdir = (rates or {}).get("rates_direction")
    reg = regime or (((valuation or {}).get("regime") or ""))
    lean = ((fed or {}).get("lean"))
    mscore = (_RATING_SC.get(rating or "", 0) +
              _RATE_SC.get(rdir or "", 0) +
              _REGIME_SC.get(reg or "", 0) +
              _FED_SC.get(lean or "", 0))
    mev = []
    if rating:
        mev.append(f"equity {rating.replace('_', ' ')}")
    if rdir:
        mev.append(f"rates {rdir}")
    if reg:
        mev.append(f"regime {reg.replace('_', ' ')}")
    if lean:
        mev.append(f"fed {lean.replace('_', ' ')}")
    mo = ("constructive" if mscore >= 2 else
          "leaning_constructive" if mscore >= 1 else
          "cautious" if mscore <= -1 and mscore > -2 else
          "defensive" if mscore <= -2 else "neutral")
    out["months"] = {
        "verdict": mo, "score": round(mscore, 1),
        "tone": "ok" if mscore >= 1 else "bad" if mscore <= -2
                else "warn",
        "evidence": mev}
    return out
