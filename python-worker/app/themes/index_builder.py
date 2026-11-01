"""Index builder — constituent scores → capped weights.

Two versions per theme, per spec:

  pure     exposure-tier weighted, limited intervention — measures
           the theme itself (pure 1.0 / derivative .55 / spec .35)
  quality  constituent-score weighted — emphasizes stronger
           businesses (what the opportunity layer would tilt toward)

Eligibility floor: a member needs evidence — a research run OR an
FV run OR a flywheel row. No name is added to hit a count: an
18-name theme is represented by 18.
"""
from __future__ import annotations

from typing import Any, Optional

EXPO_W = {"pure": 1.0, "derivative": 0.55, "speculative": 0.35}
MAX_NAME = 0.06
MIN_NAME = 0.005
MAX_NAME_PURE = 0.10


def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def constituent_score(m: dict) -> Optional[float]:
    """spec's 25/20/20/15/10/10 over member facts:
    expo .25 · quality .20 · growth .20 · revision .15 ·
    financial .10 · valuation .10. Renormalizes over live legs."""
    expo = EXPO_W.get(m.get("exposure"), 0.0)
    bs = _f(m.get("business_strength"))
    growth = _f(m.get("rev_growth"))
    eps = _f(m.get("eps_growth"))
    g = ((growth or 0) * .5 + (eps or 0) * .5
         if growth is not None or eps is not None else None)
    g_s = None if g is None else max(0.0, min(100.0, g / 30.0 * 100))
    rev = _f(m.get("est_revision_pct"))
    rev_s = None if rev is None else max(
        0.0, min(100.0, (rev + 10.0) / 20.0 * 100))
    fcf = _f(m.get("fcf_positive_share"))        # theme-level, may
    up = _f(m.get("fv_upside_pct"))               # be absent
    up_s = None if up is None else max(
        0.0, min(100.0, (up + 30.0) / 80.0 * 100))
    parts = [(expo * 100, .25),
             (bs, .20), (g_s, .20), (rev_s, .15),
             (fcf, .10), (up_s, .10)]
    live = [(s, w) for s, w in parts if s is not None]
    if not live or sum(w for _, w in live) < .40:
        return None
    return round(sum(s * w for s, w in live) /
                 sum(w for _, w in live), 1)


def _cap_weights(raw: dict[str, float], cap: float,
                 min_w: float) -> dict[str, float]:
    """Proportional → capped, excess redistributed, below-min dropped.
    Iterates to convergence (cap redistribution can re-cap).
    Cap is skipped when n×cap < 1 — infeasible bounds would flatten
    a 2-name index to 50/50 and erase the ranking."""
    if not raw:
        return {}
    total = sum(raw.values())
    w = {s: v / total for s, v in raw.items() if v > 0}
    for _ in range(10 if len(w) * cap >= 1 else 0):
        over = {s: v for s, v in w.items() if v > cap}
        if not over:
            break
        excess = sum(v - cap for v in over.values())
        for s in over:
            w[s] = cap
        room = {s: v for s, v in w.items() if s not in over}
        if not room:
            break
        rs = sum(room.values())
        for s in room:
            w[s] += excess * (w[s] / rs if rs else 1 / len(room))
    w = {s: v for s, v in w.items() if v >= min_w}
    total = sum(w.values()) or 1
    return {s: round(v / total, 4) for s, v in sorted(
        w.items(), key=lambda kv: -kv[1])}


def build(theme_key: str, members: list[dict]) -> dict[str, Any]:
    """members: [{symbol, exposure, bs, growth, revision, upside...}].
    Returns both index versions + eligibility report."""
    eligible, ineligible = [], []
    for m in members:
        has_evidence = (m.get("business_strength") is not None
                        or m.get("fv_upside_pct") is not None
                        or m.get("rev_growth") is not None
                        or m.get("est_revision_pct") is not None)
        (eligible if has_evidence else ineligible).append(m)

    pure_raw = {m["symbol"]: EXPO_W.get(m.get("exposure"), 0.0)
                for m in eligible}
    pure_raw = {s: v for s, v in pure_raw.items() if v > 0}
    pure_w = _cap_weights(pure_raw, MAX_NAME_PURE, MIN_NAME)

    scored = {m["symbol"]: constituent_score(m) for m in eligible}
    scored = {s: v for s, v in scored.items() if v is not None}
    qual_w = _cap_weights(scored, MAX_NAME, MIN_NAME)

    return {"pure": {"weights": pure_w, "n": len(pure_w)},
            "quality": {"weights": qual_w, "scores": scored,
                        "n": len(qual_w)},
            "ineligible": [m["symbol"] for m in ineligible]}


# --- notes — why this stock is on the list and what we expect --------------

def role(weight: Optional[float], exposure: Optional[str]) -> str:
    """Index member's job in the sleeve — anchor/core/satellite from
    weight × tier."""
    w = weight or 0.0
    pos = "anchor" if w >= 0.045 else "core" if w >= 0.02 \
        else "satellite"
    tier = {"pure": "pure-play", "derivative": "derivative",
            "speculative": "speculative"}.get(exposure or "",
                                              "member")
    return f"{tier} {pos}"


def pool_note(tier: Optional[str], thesis: Optional[str],
              m: dict) -> str:
    """Why this name is in the pool + what we'd need to see. Tier
    drives the expectation frame; live facts append the scorecard."""
    base = {
        "pure": "direct theme exposure — expecting the thesis to "
                "show in revenue mix",
        "derivative": "adjacent exposure — benefits if theme spend "
                      "broadens; expecting mix shift, not a pure bet",
        "speculative": "speculative pure-play — binary upside if the "
                       "thesis converts; small size only, expecting "
                       "proof of economics before promotion",
    }.get(tier or "", "theme candidate")
    facts = []
    if m.get("business_strength") is not None:
        facts.append(f"bs {m['business_strength']:.0f}")
    if m.get("fv_upside_pct") is not None:
        facts.append(f"upside {m['fv_upside_pct']:+.0f}%")
    if m.get("est_revision_pct") is not None:
        facts.append(f"rev {m['est_revision_pct']:+.0f}%")
    tail = f" ({', '.join(facts)})" if facts else " (no evidence yet)"
    return base + tail
