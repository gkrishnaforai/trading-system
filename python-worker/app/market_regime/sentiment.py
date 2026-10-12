"""Fear & Greed gauge — a computed proxy of the CNN-style sentiment index
(the real one isn't on our data plan). Four components, each scaled 0-100,
from data we already fetch: SPY momentum vs its SMA125, universe breadth
from the latest screen run, inverted VIX, and % of the universe near 20d
highs. Labels mirror the standard bands; components stay visible so the
score is explainable, not a black box.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _label(score: float) -> str:
    if score < 25:
        return "😱 extreme fear"
    if score < 40:
        return "😟 fear"
    if score < 60:
        return "😐 neutral"
    if score < 75:
        return "🙂 greed"
    return "🤑 extreme greed"


# Band → action map. Grounded in the standard contrarian playbook: the index
# is a sizing/de-risking lever, not a timing signal — extremes inform, the
# middle is noise. Backtested edge lives in the fear→recovery transition
# (20-40 band), not at either pole.
_BANDS = [
    (75, "extreme greed", "warning", {
        "stance": "de-risk into strength",
        "swing": "Trim winners in stages (¼–⅓ clips), raise stops to "
                 "breakeven+, NO fresh chases — pullback entries only. "
                 "Euphoria is when giving gains back starts.",
        "invest": "Rebalance, trim oversized positions, build cash. "
                  "New money waits or goes to the ⚠-sector laggards.",
        "size": "0.5× — smallest size; crowded tape reverses hardest",
    }),
    (60, "greed", "info", {
        "stance": "hold, tighten, don't add at highs",
        "swing": "Take partial profits at targets, tighten stops under "
                 "higher lows. New entries only on clean setups — no "
                 "extensions.",
        "invest": "Hold positions; stop deploying new cash at highs.",
        "size": "0.75× — trades need the setup to earn it",
    }),
    (40, "neutral", "info", {
        "stance": "noise zone — trade the setups, not the index",
        "swing": "Full playbook — breakout/retest/pullback entries on "
                 "merit, normal stops and targets.",
        "invest": "Stick to the plan — scheduled adds, no timing calls.",
        "size": "1.0× — baseline size",
    }),
    (25, "fear", "success", {
        "stance": "the swing sweet spot — buy the transition",
        "swing": "Historically the best risk-adjusted entry band: fear "
                 "has done the damage, recovery isn't priced. Entries on "
                 "stabilization setups (first_pullback/mean_reversion), "
                 "smaller size until trend confirms — fear in a downtrend "
                 "is a warning, not a green light.",
        "invest": "Accumulate quality on weakness — tranche buys of "
                  "leaders/market ETFs.",
        "size": "0.75–1.0× — add, but respect that downtrends run",
    }),
    (0, "extreme fear", "success", {
        "stance": "max pessimism = opportunity zone, but confirm first",
        "swing": "No new shorts. Watch for capitulation + stabilization "
                 "(mean_reversion setups on volume dry-up); first entries "
                 "small, add on the trend turn.",
        "invest": "Historically the best long-term accumulation zone — "
                  "deploy reserved cash in tranches, don't wait for the "
                  "exact bottom.",
        "size": "0.5× entries scaling up — bottoms are processes, "
                "not prints",
    }),
]


def _guidance(score: float) -> dict:
    for lo, band, level, g in _BANDS:
        if score >= lo:
            return {"band": band, "level": level, **g}
    return {"band": "extreme fear", "level": "success", **_BANDS[-1][3]}


BANDS_LEGEND = [
    {"range": "75–100", "band": "🤑 extreme greed",
     "action": "trim into strength · raise stops · no chases · 0.5× size"},
    {"range": "60–75", "band": "🙂 greed",
     "action": "partial profits at targets · tighten stops · no new "
               "extensions · 0.75×"},
    {"range": "40–60", "band": "😐 neutral",
     "action": "noise — trade setups on merit · baseline 1.0× size"},
    {"range": "25–40", "band": "😟 fear",
     "action": "swing sweet spot — buy stabilization setups · tranche "
               "accumulate · 0.75–1.0×"},
    {"range": "0–25", "band": "😱 extreme fear",
     "action": "opportunity zone — small entries on trend turn · deploy "
               "cash in tranches · 0.5× scaling up"},
]


async def fear_greed() -> dict[str, Any]:
    from app.market_data.service import get_market_data_service
    from app.market_data import indicators as ind

    svc = get_market_data_service()
    components: dict[str, Optional[float]] = {}
    detail: dict[str, Any] = {}

    # 1 — SPY momentum vs SMA125
    try:
        spy = await svc.get_ohlcv("SPY", period="1y")
        if len(spy) >= 126:
            price = ind.closes(spy).iloc[-1]
            sma125 = ind.sma(spy, 125)
            pct = price / sma125 - 1 if sma125 else 0
            components["momentum"] = _clamp((pct + 0.05) * 1000)
            detail["spy_vs_sma125"] = round(pct * 100, 1)
    except Exception as exc:
        logger.debug("fear/greed momentum failed: %s", exc)

    # 2 — universe breadth (latest screen run's regime census)
    # 3 — % of universe within 5% of its 20d high (stock strength)
    try:
        from app.database import db
        run = db.execute_query(
            "SELECT breadth, results FROM screen_runs "
            "ORDER BY ran_at DESC LIMIT 1")
        if run:
            breadth = run[0].get("breadth") or {}
            up = breadth.get("uptrend_pct")
            if up is not None:
                components["breadth"] = _clamp(float(up))
                detail["uptrend_pct"] = round(float(up), 1)
            rows = run[0].get("results") or []
            near = [r for r in rows if (r.get("dd20") or -1) >= -0.05]
            if rows:
                components["stock_strength"] = _clamp(len(near) / len(rows) * 100)
                detail["near_highs_pct"] = round(len(near) / len(rows) * 100, 1)
    except Exception as exc:
        logger.debug("fear/greed breadth failed: %s", exc)

    # 4 — VIX inverted (low vol = complacency/greed)
    try:
        vix_bars = await svc.get_ohlcv("^VIX", period="3mo")
        if vix_bars:
            vix = ind.closes(vix_bars).iloc[-1]
            components["vix"] = _clamp((35 - vix) * 4)
            detail["vix"] = round(float(vix), 1)
    except Exception as exc:
        logger.debug("fear/greed vix failed: %s", exc)

    vals = [v for v in components.values() if v is not None]
    score = round(sum(vals) / len(vals), 1) if vals else None
    return {
        "score": score,
        "label": _label(score) if score is not None else "unavailable",
        "guidance": _guidance(score) if score is not None else None,
        "bands": BANDS_LEGEND,
        "components": {k: round(v, 1) if v is not None else None
                       for k, v in components.items()},
        "detail": detail,
        "note": "Computed proxy of the fear/greed index — SPY momentum, "
                "universe breadth, near-highs %, inverted VIX.",
    }
