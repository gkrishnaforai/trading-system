"""Forward regime probabilities — the "70% chance of X" read.

A three-way distribution over the next ~20 sessions:

    p_deeper   P(the correction deepens / another leg down)
    p_chop     P(sideways, no resolution either way)
    p_bull     P(the correction resolves — 'growth market' resumes)

Evidence inputs, all deterministic and already computed:
  transition score + 5d delta   (the regime engine's own trajectory)
  breadth_score / hl_broken     (our universe internals — daily_bars)
  VIX level + rising            (the market's own fear gauge)
  SPY vs 200dma                 (trend intact or broken)
  deterioration_score           (regime composite slope)
  geo_risk                      (headline crisis scan, capped weight)

Honest framing: these are evidence-weighted estimates — a transparent
heuristic, not a fitted model. They get stored daily (engine_weights
'regime:forward') so the meta job can calibrate them against realized
20d outcomes once enough history accrues — same loop as priors/weights.
Geopolitical shocks are inherently unpredictable; geo_risk only shifts
the distribution, it can never drive p_deeper to certainty.
"""
from __future__ import annotations

from typing import Any, Optional


def forward_probs(regime_detail: dict | None,
                  breadth: dict | None,
                  geo: dict | None,
                  vix: Optional[float] = None,
                  vix_rising: bool = False) -> dict[str, Any]:
    rd = regime_detail or {}
    br = breadth or {}
    geo = geo or {}
    tscore = rd.get("bullish_transition_score")
    tdelta = rd.get("transition_delta_5d") or 0
    drivers: list[str] = []

    bear = 25.0                               # base rate
    bull = 25.0

    if vix is not None:                          # the fear gauge itself
        if vix >= 25:
            bear += 10; drivers.append(f"VIX {vix:.0f} — stress regime")
        elif vix >= 20:
            bear += 6
        elif vix < 14:
            bull += 5
        if vix_rising:
            bear += 4; drivers.append("VIX rising")

    # transition evidence — the largest single weight
    if tscore is not None:
        bear += max(0.0, (50 - tscore) * 0.55)
        bull += max(0.0, (tscore - 50) * 0.55)
        if tdelta:
            bear -= min(8.0, tdelta * 0.25)
            bull += min(8.0, max(0.0, tdelta) * 0.25)

    # universe internals — our own breadth, free of index optics
    bs = br.get("breadth_score")
    if bs is not None:
        bear += max(0.0, (35 - bs) * 0.45)
        bull += max(0.0, (bs - 55) * 0.40)
        if (br.get("pct_hl_broken") or 0) > 40:
            bear += 8
            drivers.append(f"{br['pct_hl_broken']}% structures broken")
        if (br.get("pct_above_50") or 50) < 30:
            bear += 6
            drivers.append("breadth thin — <30% above 50dma")

    # regime-level facts
    if (rd.get("risk_level") or "") in {"high", "very_high"}:
        bear += 6
    det = rd.get("deterioration_score")
    if det is not None and det < -0.3:
        bear += min(12.0, -det * 15)
        drivers.append(f"deterioration {det:+.2f}")

    # geopolitical overlay — shifts, never decides
    gr = geo.get("geo_risk")
    if gr:
        bear += min(10.0, gr * 0.12)
        if gr >= 50:
            drivers.append(f"geo-risk elevated ({gr}/100)")
    flow = (geo.get("defensive") or {}).get("flow")
    if flow == "risk-off":
        bear += 7
        drivers.append("defensive flows — money hiding in gold/bonds")
    elif flow == "cautious":
        bear += 3

    # SPY vs its 200dma — trend intact or broken
    vs200 = (rd.get("spy_vs_200") or rd.get("spy_vs_200dma"))
    if vs200 is not None and vs200 < 0:
        bear += 8
        drivers.append("SPY under 200dma")

    # normalize to a 3-way split; chop absorbs the residual
    bear = max(5.0, min(80.0, bear))
    bull = max(5.0, min(80.0, bull))
    chop = max(10.0, 100 - bear - bull)
    total = bear + bull + chop
    p_deep, p_bull, p_chop = (round(bear / total * 100),
                              round(bull / total * 100),
                              round(chop / total * 100))

    lead = max(("dip", p_deep), ("growth", p_bull), ("chop", p_chop),
               key=lambda kv: kv[1])
    return {"p_deeper_dip_20d": p_deep, "p_chop_20d": p_chop,
            "p_bullish_20d": p_bull,
            "lead_scenario": lead[0],
            "confidence": "low" if abs(bear - bull) < 12 else "medium",
            "horizon": "~20 sessions", "drivers": drivers[:6],
            "note": ("evidence-weighted heuristic — calibrates against "
                     "realized outcomes as history accrues")}
