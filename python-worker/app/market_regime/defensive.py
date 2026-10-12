"""Deterministic defensive-state assessment — the bearish twin of
transition.py.

Same contract as the bullish side: the dimension scores in
DimensionFacts are the evidence (already [-1,+1] bullish), so the
defensive score is their weighted inversion — no new fetches, no
parallel data path. The state machine adds what the score can't:
hysteresis (streaks of consecutive daily assessments) and an emergency
bypass for crash days.

  escalate    >=50 x2d WATCH · >=60 x3d HEDGE · >=70 x3d DEFENSIVE
              capitulation_score >=60 -> CAPITULATION (immediate — it
              is its own composite detector, not a streak input)
  de-escalate <50 x3d step down · <42 x3d NORMAL
              CAPITULATION -> RECOVERY once the washout passes
              RECOVERY -> NORMAL when the bullish transition confirms
  emergency   SPY -4% day · VIX >=35 spiking +25% · score >=85
              -> DEFENSIVE today, persistence bypassed

Downstream consumers read `stage`, never the score — the score is
evidence, the state is policy.
"""
from __future__ import annotations

from typing import Iterable, Optional

from pydantic import BaseModel, Field

from .models import DimensionFacts, MarketSnapshot

DEFENSIVE_WEIGHTS = {
    "trend": 0.25,
    "breadth": 0.20,
    "momentum": 0.15,
    "volatility": 0.15,
    "macro": 0.15,
    "structure": 0.10,
}

STAGES = ("NORMAL", "WATCH", "HEDGE", "DEFENSIVE", "CAPITULATION",
          "RECOVERY")
_RANK = {"NORMAL": 0, "WATCH": 1, "HEDGE": 2, "DEFENSIVE": 3}

_CAPITULATION_MIN = 60
_EMERGENCY_SCORE = 85
_EMERGENCY_RET1 = -0.04
_EMERGENCY_VIX, _EMERGENCY_VIX_CHG = 35.0, 0.25


class DefensiveTransitionAssessment(BaseModel):
    score: float = Field(ge=0.0, le=100.0)
    delta_1d: Optional[float] = None
    delta_5d: Optional[float] = None
    delta_20d: Optional[float] = None
    stage: str = "NORMAL"
    emergency: bool = False
    streak: int = 0               # consecutive days at/above the
                                  #  threshold that set this stage
    components: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    data_sufficient: bool = False
    rules_version: str = "defensive-transition-v1"


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _streak_ge(daily: list[dict], threshold: float) -> int:
    """Consecutive most-recent daily scores >= threshold, today first."""
    n = 0
    for row in daily:
        if row.get("score") is None or float(row["score"]) < threshold:
            break
        n += 1
    return n


def _streak_lt(daily: list[dict], threshold: float) -> int:
    n = 0
    for row in daily:
        if row.get("score") is None or float(row["score"]) >= threshold:
            break
        n += 1
    return n


def _resolve_stage(last_stage: Optional[str], daily: list[dict],
                   capitulation: Optional[float], emergency: bool,
                   bull_stage: Optional[str]) -> tuple[str, int]:
    """State machine. `daily` is today-first per-date score rows
    (today's candidate score already prepended by the caller)."""
    last = last_stage or "NORMAL"
    s50 = _streak_ge(daily, 50)
    s60 = _streak_ge(daily, 60)
    s70 = _streak_ge(daily, 70)
    d50 = _streak_lt(daily, 50)
    d42 = _streak_lt(daily, 42)
    today = daily[0]["score"] if daily else 0.0

    # capitulation overrides everything — its composite already encodes
    # washout depth; streak-counting it would double-count persistence
    if capitulation is not None and capitulation >= _CAPITULATION_MIN:
        return "CAPITULATION", 1
    if emergency:
        return "DEFENSIVE", 1

    if last == "CAPITULATION":
        if d50 >= 3:
            return "RECOVERY", d50
        return "DEFENSIVE", 1          # washout over, tape still hot
    if last == "RECOVERY":
        if today >= 55:
            return "WATCH", s50        # re-escalation
        if bull_stage in {"ACTIVE", "CONFIRMED", "NORMAL"}:
            return "NORMAL", 0         # bullish transition confirmed
        return "RECOVERY", 0

    # persistence-encoded escalation target
    target = "NORMAL"
    tgt_streak = 0
    if s70 >= 3:
        target, tgt_streak = "DEFENSIVE", s70
    elif s60 >= 3:
        target, tgt_streak = "HEDGE", s60
    elif s50 >= 2:
        target, tgt_streak = "WATCH", s50

    if _RANK.get(target, 0) > _RANK.get(last, 0):
        return target, tgt_streak
    if _RANK.get(target, 0) < _RANK.get(last, 0):
        # de-escalation needs its own exit streak — otherwise hold
        if _RANK.get(last, 0) >= _RANK["HEDGE"] and d50 >= 3:
            return "WATCH", d50
        if last == "WATCH" and d42 >= 3:
            return "NORMAL", d42
        return last, 0
    return target, tgt_streak


def derive_defensive_transition(
    snapshot: MarketSnapshot,
    facts: DimensionFacts,
    history_scores: Optional[Iterable[dict]] = None,
    daily: Optional[list[dict]] = None,
    last_stage: Optional[str] = None,
    capitulation_score: Optional[float] = None,
    bull_stage: Optional[str] = None,
) -> DefensiveTransitionAssessment:
    """Bearish mirror of derive_bullish_transition — same inputs,
    inverted composite, plus streak-gated stage resolution."""
    scores = facts.scores
    components = {
        name: _clamp(-scores.get(name, 0.0))
        for name in DEFENSIVE_WEIGHTS
    }
    available = [n for n in components if n in scores]
    weighted = sum(components[n] * DEFENSIVE_WEIGHTS[n] for n in available)
    total_weight = sum(DEFENSIVE_WEIGHTS[n] for n in available)
    score = round(max(0.0, min(100.0, 50.0 + 50.0 * weighted / total_weight)),
                  1) if total_weight else 0.0

    t, m, v = snapshot.trend, snapshot.momentum, snapshot.volatility
    b, structure = snapshot.breadth, snapshot.structure

    emergency = bool(
        (m.ret1 is not None and m.ret1 <= _EMERGENCY_RET1)
        or (v.vix is not None and v.vix >= _EMERGENCY_VIX
            and v.vix_chg_1d is not None
            and v.vix_chg_1d >= _EMERGENCY_VIX_CHG)
        or score >= _EMERGENCY_SCORE)

    # today's candidate row leads the streak window
    rows = [{"score": score}] + [r for r in (daily or [])]
    stage, streak = _resolve_stage(last_stage, rows, capitulation_score,
                                   emergency, bull_stage)

    reasons: list[str] = []
    if not t.above_sma200:
        reasons.append("SPY below SMA200")
    if (t.days_below_ema20 or 0) >= 3:
        reasons.append(f"{t.days_below_ema20}d below 20EMA — "
                       "character change, not a poke")
    if b.pct_above_sma50 is not None and b.pct_above_sma50 <= 35:
        reasons.append(f"breadth weak — {b.pct_above_sma50:.0f}% "
                       "above SMA50")
    if v.vix is not None and v.vix >= 25:
        reasons.append(f"VIX {v.vix:.0f} — vol regime elevated")
    if structure.dist_from_52w_high is not None \
            and structure.dist_from_52w_high <= -0.10:
        reasons.append(f"{structure.dist_from_52w_high:.0%} off "
                       "52w high")
    if emergency:
        reasons.append("EMERGENCY — crash-day bypass, hysteresis "
                       "suspended")
    if capitulation_score is not None and capitulation_score >= _CAPITULATION_MIN:
        reasons.append(f"capitulation composite {capitulation_score:.0f}"
                       " — monetization zone")
    if stage == "RECOVERY":
        reasons.append("washout passed — recovery capital stage armed")

    deltas = {}
    history = sorted(list(history_scores or []),
                     key=lambda r: r.get("as_of", ""), reverse=True)
    for key, offset in (("delta_1d", 1), ("delta_5d", 5),
                        ("delta_20d", 20)):
        previous = next((r.get("score") for r in history
                         if r.get("offset_days") == offset), None)
        deltas[key] = round(score - float(previous), 1) \
            if previous is not None else None

    data_sufficient = bool(snapshot.coverage.get("index")) \
        and len(available) >= 4
    if not data_sufficient:
        stage = min(stage, "WATCH", key=lambda s: _RANK.get(s, 1))
        reasons.append("defensive coverage incomplete — state capped "
                       "at WATCH")
    return DefensiveTransitionAssessment(
        score=score,
        delta_1d=deltas["delta_1d"],
        delta_5d=deltas["delta_5d"],
        delta_20d=deltas["delta_20d"],
        stage=stage,
        emergency=emergency,
        streak=streak,
        components={k: round(v, 3) for k, v in components.items()},
        reasons=list(dict.fromkeys(reasons)),
        data_sufficient=data_sufficient,
    )
