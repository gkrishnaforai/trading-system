"""Deterministic bullish-transition and dip-buying assessment."""
from __future__ import annotations

from typing import Iterable, Optional

from pydantic import BaseModel, Field

from .models import DimensionFacts, MarketSnapshot


TRANSITION_WEIGHTS = {
    "trend_repair": 0.20,
    "breadth": 0.20,
    "momentum": 0.15,
    "leadership": 0.15,
    "volatility": 0.15,
    "macro": 0.10,
    "structure": 0.05,
}


class BullishTransitionAssessment(BaseModel):
    score: float = Field(ge=0.0, le=100.0)
    delta_1d: Optional[float] = None
    delta_5d: Optional[float] = None
    delta_20d: Optional[float] = None
    stage: str = "NO_DIP_BUYING"
    dip_buying_environment: str = "DISABLED"
    size_multiplier: float = Field(ge=0.0, le=1.0)
    components: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    data_sufficient: bool = False
    rules_version: str = "bullish-transition-v1"


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _stage(score: float) -> tuple[str, str, float]:
    if score < 40:
        return "NO_DIP_BUYING", "DISABLED", 0.0
    if score < 55:
        return "WATCH", "WATCH_ONLY", 0.25
    if score < 65:
        return "SELECTIVE", "SELECTIVE", 0.50
    if score < 75:
        return "ACTIVE", "ACTIVE", 0.70
    if score < 85:
        return "CONFIRMED", "CONFIRMED", 0.85
    return "NORMAL", "NORMAL", 1.0


def derive_bullish_transition(
    snapshot: MarketSnapshot,
    facts: DimensionFacts,
    history_scores: Optional[Iterable[dict]] = None,
) -> BullishTransitionAssessment:
    """Calculate a bounded transition score from current facts and stored history."""
    t, m, b, v = snapshot.trend, snapshot.momentum, snapshot.breadth, snapshot.volatility
    p, structure = snapshot.participation, snapshot.structure
    scores = facts.scores
    components = {
        "trend_repair": _clamp((scores.get("trend", 0.0) + scores.get("structure", 0.0)) / 2),
        "breadth": _clamp(scores.get("breadth", 0.0)),
        "momentum": _clamp(scores.get("momentum", 0.0)),
        "leadership": _clamp(scores.get("participation", 0.0)),
        "volatility": _clamp(scores.get("volatility", 0.0)),
        "macro": _clamp(scores.get("macro", 0.0)),
        "structure": _clamp(scores.get("structure", 0.0)),
    }
    available = [name for name, value in components.items() if value != 0 or name in scores]
    weighted = sum(components[name] * TRANSITION_WEIGHTS[name] for name in available)
    total_weight = sum(TRANSITION_WEIGHTS[name] for name in available)
    score = round(max(0.0, min(100.0, 50.0 + 50.0 * weighted / total_weight)), 1) if total_weight else 0.0
    stage, environment, size = _stage(score)
    reasons: list[str] = []
    if b.breadth_chg_5d is not None and b.breadth_chg_5d > 0:
        reasons.append(f"breadth improving {b.breadth_chg_5d:+.1f}pts/5d")
    if m.rsi_5d_change is not None and m.rsi_5d_change > 0:
        reasons.append(f"momentum improving RSI {m.rsi_5d_change:+.1f}/5d")
    if structure.spy_higher_low:
        reasons.append("higher low confirmed")
    if v.vix_chg_5d is not None and v.vix_chg_5d < 0:
        reasons.append(f"VIX easing {v.vix_chg_5d:+.1f}/5d")
    if p.leading:
        reasons.append(f"leadership: {', '.join(p.leading[:3])}")
    if stage in {"SELECTIVE", "ACTIVE", "CONFIRMED", "NORMAL"}:
        reasons.append("transition evidence supports staged dip-buying")
    else:
        reasons.append("transition evidence is not strong enough for dip-buying")

    history = sorted(list(history_scores or []), key=lambda row: row.get("as_of", ""), reverse=True)
    deltas = {}
    for key, offset in (("delta_1d", 1), ("delta_5d", 5), ("delta_20d", 20)):
        previous = next((row.get("score") for row in history if row.get("offset_days") == offset), None)
        if previous is not None:
            deltas[key] = round(score - float(previous), 1)
        else:
            deltas[key] = None

    data_sufficient = bool(snapshot.coverage.get("index")) and len(available) >= 4
    if not data_sufficient:
        stage, environment, size = "WATCH", "WATCH_ONLY", 0.25
        reasons.append("transition coverage incomplete; sizing capped")
    return BullishTransitionAssessment(
        score=score,
        delta_1d=deltas["delta_1d"],
        delta_5d=deltas["delta_5d"],
        delta_20d=deltas["delta_20d"],
        stage=stage,
        dip_buying_environment=environment,
        size_multiplier=size,
        components={k: round(v, 3) for k, v in components.items()},
        reasons=list(dict.fromkeys(reasons)),
        data_sufficient=data_sufficient,
    )
