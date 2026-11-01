"""Theme Opportunity Score — 6 factors, spec weights, leg evidence.

    macro_regime    .20   scenario-weighted fit (from scenarios.py)
    earnings        .25   member revision breadth + fwd growth
    valuation       .20   exposure-weighted fv_upside — is the
                          opportunity already priced in?
    demand          .15   lifecycle stage + member tailwind evidence
    momentum        .10   member ret vs SPY + breadth above 50SMA
    resilience      .10   member quality floor + concentration

Same conventions as metals: weighted legs renormalize over what's
live, missing legs are reported, <40% coverage → no_score.
"""
from __future__ import annotations

from statistics import median
from typing import Any, Optional

from .narratives import STAGE_BASE

WEIGHTS = {"macro_regime": .20, "earnings": .25, "valuation": .20,
           "demand": .15, "momentum": .10, "resilience": .10}


def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _map(v: Optional[float], lo: float, hi: float) -> Optional[float]:
    if v is None:
        return None
    return max(0.0, min(100.0, (v - lo) / (hi - lo) * 100.0))


def _med(vals: list[Optional[float]]) -> Optional[float]:
    xs = [v for v in vals if v is not None]
    return median(xs) if xs else None


# --- leg builders (per-theme, over member rows) -------------------------------

def earnings_leg(members: list[dict]) -> tuple[Optional[float], str]:
    """revision breadth + forward growth — 'are companies about to
    deliver accelerating earnings'."""
    rev = _med([m.get("est_revision_pct") for m in members])
    growth = _med([m.get("rev_growth") for m in members])
    eps = _med([m.get("eps_growth") for m in members])
    raising = [m for m in members
               if (m.get("est_revision_pct") or 0) > 2]
    frac_up = (len(raising) / len(members) * 100) if members else None
    s_rev = _map(rev, -10.0, 10.0)
    s_breadth = _map(frac_up, 20.0, 70.0)
    s_growth = _map((growth or 0) * .5 + (eps or 0) * .5
                    if growth is not None or eps is not None
                    else None, 0.0, 30.0)
    parts = [(s_rev, .4), (s_breadth, .3), (s_growth, .3)]
    live = [(s, w) for s, w in parts if s is not None]
    if not live or sum(w for _, w in live) < .4:
        return None, ""
    score = sum(s * w for s, w in live) / sum(w for _, w in live)
    val = f"rev {rev:+.0f}%" if rev is not None else ""
    val += f" · {frac_up:.0f}% raising" if frac_up is not None else ""
    return score, val.strip(" ·")


def valuation_leg(members: list[dict]) -> tuple[Optional[float], str]:
    """Exposure-weighted fv_upside — priced in or not."""
    ups = [(m.get("fv_upside_pct"), m.get("expo_w", 1.0))
           for m in members if m.get("fv_upside_pct") is not None]
    if not ups:
        return None, ""
    tw = sum(w for _, w in ups)
    med_up = sum(u * w for u, w in ups) / tw
    return _map(med_up, -30.0, 50.0), f"FV upside {med_up:+.0f}%"


def demand_leg(stage: Optional[str],
               members: list[dict]) -> tuple[Optional[float], str]:
    """Lifecycle stage + member tailwind evidence."""
    base = STAGE_BASE.get(stage or "")
    tw = _med([m.get("ai_tailwind") for m in members])
    parts = [(float(base), .55) if base is not None else (None, .55),
             (_map(tw, 30.0, 75.0), .45)]
    live = [(s, w) for s, w in parts if s is not None]
    if not live:
        return None, ""
    score = sum(s * w for s, w in live) / sum(w for _, w in live)
    val = f"stage {stage}" if stage else ""
    val += f" · tailwind {tw:.0f}" if tw is not None else ""
    return score, val.strip(" ·")


def momentum_leg(members: list[dict],
                 spy_ret20: Optional[float],
                 spy_ret60: Optional[float]
                 ) -> tuple[Optional[float], str]:
    rs20 = _med([(m.get("ret20") - spy_ret20)
                 if m.get("ret20") is not None and spy_ret20 is not None
                 else None for m in members])
    breadth = _med([m.get("above_sma50") for m in members])
    s_rs = _map(rs20, -0.10, 0.10)
    s_br = _map(breadth, 20.0, 80.0)
    parts = [(s_rs, .55), (s_br, .45)]
    live = [(s, w) for s, w in parts if s is not None]
    if not live:
        return None, ""
    score = sum(s * w for s, w in live) / sum(w for _, w in live)
    val = f"RS20 {rs20:+.1%}" if rs20 is not None else ""
    val += f" · {breadth:.0f}% >50dma" if breadth is not None else ""
    return score, val.strip(" ·")


def resilience_leg(members: list[dict]) -> tuple[Optional[float], str]:
    """Quality floor + concentration — how the theme survives a bad
    tape. Median business strength minus the weak-tail drag and a
    single-name concentration penalty."""
    bs = _med([m.get("business_strength") for m in members])
    weak = [m for m in members
            if (m.get("business_strength") or 50) < 40]
    frac_weak = len(weak) / len(members) if members else None
    expo = sorted((m.get("expo_w", 0) for m in members), reverse=True)
    top_share = (expo[0] / sum(expo)) if expo and sum(expo) else None
    s_bs = _map(bs, 30.0, 80.0)
    s_weak = _map(frac_weak, 0.60, 0.0)
    s_conc = _map(top_share, 0.60, 0.15)
    parts = [(s_bs, .5), (s_weak, .25), (s_conc, .25)]
    live = [(s, w) for s, w in parts if s is not None]
    if not live:
        return None, ""
    score = sum(s * w for s, w in live) / sum(w for _, w in live)
    val = f"bs {bs:.0f}" if bs is not None else ""
    val += f" · {len(weak)} weak" if members else ""
    return score, val.strip(" ·")


def score(theme_key: str, legs: dict[str, Any],
          scenario_expected: Optional[float]
          ) -> dict[str, Any]:
    """legs keys: members(list), stage, spy_ret20, spy_ret60."""
    members = legs.get("members") or []
    parts = [
        (scenario_expected, "macro_regime", "scenario-weighted fit"),
        (earnings_leg(members), "earnings", ""),
        (valuation_leg(members), "valuation", ""),
        (demand_leg(legs.get("stage"), members), "demand", ""),
        (momentum_leg(members, legs.get("spy_ret20"),
                      legs.get("spy_ret60")), "momentum", ""),
        (resilience_leg(members), "resilience", ""),
    ]
    live, missing, details = [], [], []
    for item, name, note in parts:
        s, val = item if isinstance(item, tuple) else (item, note)
        if s is None:
            missing.append(name)
            continue
        w = WEIGHTS[name]
        live.append((s, w))
        details.append({"name": name, "score": round(s),
                        "weight": w, "value": val})
    if not live or sum(w for _, w in live) < .40:
        return {"score": None, "missing": missing, "legs": details}
    total = sum(w for _, w in live)
    return {"score": round(sum(s * w for s, w in live) / total),
            "missing": missing, "legs": details}
