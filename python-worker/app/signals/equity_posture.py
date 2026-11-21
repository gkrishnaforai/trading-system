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
