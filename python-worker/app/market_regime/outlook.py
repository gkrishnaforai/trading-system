"""Deterministic next-session scenario outlook.

Derives "what tomorrow's conditions favor" from today's regime facts,
transition trajectory, volatility term structure, and the event calendar.
This is scenario analysis, not prediction — confidence is capped and every
scenario carries explicit confirmation/invalidation conditions. The LLM may
explain the output but never authors it.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from .models import DimensionFacts, MarketRegime, MarketSnapshot
from app.market_events import MarketEvent, EventStatus, EventSeverity


class OutlookScenario(BaseModel):
    label: str
    likelihood: str                        # base_case | alternative | tail_risk
    narrative: str
    confirmations: List[str] = Field(default_factory=list)
    invalidations: List[str] = Field(default_factory=list)


class NextSessionOutlook(BaseModel):
    as_of: Optional[datetime] = None
    bias: str = "neutral"                  # constructive | neutral | cautious | defensive
    confidence: str = "low"                # capped: 1-day horizon never earns "high"
    base_case: OutlookScenario
    alternative: OutlookScenario
    tail_risk: Optional[OutlookScenario] = None
    watch_levels: dict = Field(default_factory=dict)
    event_risks: List[str] = Field(default_factory=list)
    drivers: List[str] = Field(default_factory=list)
    sizing_guidance: str = "unknown"
    disclaimer: str = (
        "Scenario analysis from deterministic regime evidence — not a prediction. "
        "Overnight news, earnings, and macro releases can invalidate any scenario."
    )


def _scenario(label: str, likelihood: str, narrative: str,
              confirmations: List[str], invalidations: List[str]) -> OutlookScenario:
    return OutlookScenario(label=label, likelihood=likelihood, narrative=narrative,
                           confirmations=confirmations, invalidations=invalidations)


def derive_next_session_outlook(
    snap: MarketSnapshot,
    facts: DimensionFacts,
    regime: MarketRegime,
    event: Optional[MarketEvent] = None,
) -> NextSessionOutlook:
    trend = snap.trend
    momentum = snap.momentum
    breadth = snap.breadth
    vol = snap.volatility
    structure = snap.structure

    trend_score = regime.trend_score if regime.trend_score is not None else 0.0
    deterioration = regime.deterioration_score if regime.deterioration_score is not None else 0.0
    transition_score = regime.bullish_transition_score
    transition_delta = regime.transition_delta_1d
    transition_improving = transition_delta is not None and transition_delta > 0

    pending_event = (
        event is not None
        and event.status == EventStatus.SCHEDULED
        and event.severity in {EventSeverity.HIGH, EventSeverity.EXTREME}
    )
    event_risks: List[str] = []
    if event is not None and event.status == EventStatus.SCHEDULED:
        when = event.scheduled_at.strftime("%Y-%m-%d %H:%M UTC") if event.scheduled_at else "time unknown"
        event_risks.append(f"{event.event_name} scheduled ({when}) — gap risk around the release")
    if event is not None and event.status in {EventStatus.RELEASED, EventStatus.CONFIRMED}:
        event_risks.append(f"{event.event_name} released — next session trades on reaction follow-through")

    drivers: List[str] = []
    if facts.trend != "unknown":
        drivers.append(f"trend: {facts.trend}")
    if facts.momentum != "unknown":
        drivers.append(f"momentum: {facts.momentum}")
    if facts.breadth != "unknown":
        drivers.append(f"breadth: {facts.breadth}")
    if facts.volatility != "unknown":
        drivers.append(f"volatility: {facts.volatility}")
    if transition_score is not None:
        drivers.append(
            f"bullish-transition score {transition_score:.0f}/100 "
            f"({regime.transition_stage}, {transition_delta:+.1f} 1d)" if transition_delta is not None
            else f"bullish-transition score {transition_score:.0f}/100 ({regime.transition_stage})"
        )
    if vol.vix_term_ratio is not None:
        state = "contango (calmer)" if vol.vix_term_ratio > 1 else "backwardation (stress)"
        drivers.append(f"VIX term structure {vol.vix_term_ratio:.2f} — {state}")
    if vol.vix is not None:
        drivers.append(f"VIX {vol.vix:.1f}")
    if structure.dist_from_20d_high is not None:
        drivers.append(f"SPY {structure.dist_from_20d_high:.1%} from 20d high")

    # --- bias ---
    risk_off_regimes = {"bear", "macro_risk_off", "distribution"}
    if regime.condition in risk_off_regimes or regime.regime.value in risk_off_regimes:
        bias = "defensive"
    elif deterioration < -0.15 or (facts.volatility or "").endswith("_rising"):
        bias = "cautious"
    elif trend_score > 0.2 and deterioration >= -0.05:
        bias = "constructive"
    elif trend_score > 0 or transition_improving:
        bias = "neutral"
    else:
        bias = "cautious"
    if pending_event and bias in {"constructive", "neutral"}:
        bias = "cautious"

    # --- scenarios ---
    recovering = (transition_score is not None and transition_score >= 50) or transition_improving
    above_key_ma = trend.above_sma20 is True or trend.above_sma50 is True

    if bias == "defensive":
        base = _scenario(
            "defensive_positioning", "base_case",
            "Regime evidence is risk-off; the base case is continued pressure or choppy weakness "
            "rather than a clean recovery.",
            ["further breadth deterioration", "VIX continuing to rise",
             "price failing to reclaim key moving averages"],
            ["a strong reversal reclaiming the 20d area with expanding breadth",
             "VIX term structure returning to contango"],
        )
        alt = _scenario(
            "oversold_bounce", "alternative",
            "If selling is stretched, an oversold bounce is plausible — treat it as a bounce, "
            "not a regime change, until confirmed.",
            ["higher low forms intraday", "down-volume dries up", "VIX stops rising"],
            ["bounce fails at the first moving-average test"],
        )
    elif recovering and above_key_ma:
        base = _scenario(
            "recovery_continuation", "base_case",
            "Transition evidence is improving while price holds key averages; the base case is a "
            "continuation attempt of the recovery leg.",
            ["price holds above the 20d average into the close",
             "breadth keeps improving", "VIX stable or falling"],
            ["reversal below the 20d average", "VIX spike",
             "negative overnight catalyst"],
        )
        alt = _scenario(
            "choppy_consolidation", "alternative",
            "Recovery evidence exists but confirmation is incomplete; sideways digestion is "
            "plausible while the market waits for the next signal.",
            ["range-bound session", "mixed breadth", "quiet volatility"],
            ["break of the recovery low", "surprise macro catalyst"],
        )
    elif bias == "constructive":
        base = _scenario(
            "bull_continuation", "base_case",
            "Trend, momentum, and breadth lean constructive; the base case is continuation of the "
            "prevailing trend.",
            ["higher high / higher low structure intact",
             "leadership sectors hold", "VIX stable"],
            ["failed breakout at the 20d high", "breadth divergence",
             "hot macro data or hawkish surprise"],
        )
        alt = _scenario(
            "pullback_within_uptrend", "alternative",
            "Trend is constructive but short-term extension makes a shallow pullback plausible — "
            "orderly, not regime-breaking, while key averages hold.",
            ["price tests the 20d average and holds", "down-day volume stays light"],
            ["break below the 50d average on expanding down-volume"],
        )
    elif bias == "cautious":
        base = _scenario(
            "choppy_or_lower", "base_case",
            "Evidence is deteriorating or mixed; the base case is choppy, lower-quality trading "
            "with elevated reversal risk.",
            ["failed rallies", "weak breadth", "VIX firm or rising"],
            ["broad-based strength reclaiming key averages",
             "VIX term structure normalizing"],
        )
        alt = _scenario(
            "stabilization_attempt", "alternative",
            "If selling pressure stalls, a stabilization attempt is possible — it needs "
            "confirmation before it is actionable.",
            ["higher low forms", "declines stop expanding", "VIX rolls over"],
            ["another leg down through recent lows"],
        )
    else:
        base = _scenario(
            "choppy_consolidation", "base_case",
            "Evidence is balanced; the base case is a directionless, range-bound session "
            "dominated by positioning rather than trend.",
            ["narrow range", "mixed sector performance", "muted volatility"],
            ["breakout or breakdown with volume confirmation",
             "unexpected macro catalyst"],
        )
        alt = _scenario(
            "trend_resolution", "alternative",
            "A compressed market can resolve in either direction; watch the range edges and "
            "breadth for the first real signal.",
            ["range break with breadth confirmation", "sector leadership broadens"],
            ["false breakout that reverses intraday"],
        )

    if pending_event:
        base = _scenario(
            "event_driven", "base_case",
            f"A scheduled high-severity event ({event.event_name}) dominates the next session; "
            "positioning into the release matters more than today's tape.",
            ["pre-event drift stays contained", "event outcome matches expectations"],
            ["surprise versus expectations", "hawkish/dovish surprise",
             "gap that skips key levels"],
        )
        base.confirmations = ["outcome in line with expectations", "post-release trend holds"]
        alt = _scenario(
            base.label, "alternative",
            "If the event passes without surprise, the pre-event bias reasserts itself.",
            ["muted reaction", "VIX crush after the release"],
            ["surprise outcome repricing the market"],
        )

    tail = None
    if vol.vix is not None and vol.vix >= 20 or (vol.vix_term_ratio is not None and vol.vix_term_ratio < 1.0):
        tail = _scenario(
            "volatility_shock", "tail_risk",
            "Volatility is already elevated or the term structure is stressed; a further VIX spike "
            "is a live tail risk even when it is not the base case.",
            ["VIX accelerates", "breadth collapses", "credit/macro stress headlines"],
            ["VIX mean-reverts", "term structure returns to contango"],
        )
    elif trend.above_sma50 is False and trend_score < 0:
        tail = _scenario(
            "capitulation_extension", "tail_risk",
            "Trend is below key averages; a capitulation extension is the tail risk to respect.",
            ["accelerating declines", "new lows expand"],
            ["sharp reversal reclaiming the 20d average"],
        )

    # --- confidence (capped at medium) ---
    agreement = sum([
        trend_score > 0.2,
        facts.momentum in {"strong", "recovering"},
        facts.breadth in {"strong", "improving", "neutral"},
        not pending_event,
    ])
    confidence = "medium" if agreement >= 3 else "low"
    if pending_event or bias == "defensive":
        confidence = "low"

    # --- watch levels ---
    watch = {
        "spy_price": trend.spy_price,
        "sma20": trend.sma20,
        "sma50": trend.sma50,
        "sma200": trend.sma200,
        "dist_from_20d_high": structure.dist_from_20d_high,
        "dist_from_20d_low": structure.dist_from_20d_low,
        "vix": vol.vix,
        "vix_term_ratio": vol.vix_term_ratio,
        "pct_above_sma50": breadth.pct_above_sma50,
    }

    permissions = regime.market_permissions
    multiplier = permissions.size_multiplier if permissions else 0.0
    sizing = (
        "normal" if multiplier >= 0.75 else
        "reduced" if multiplier >= 0.4 else
        "minimal" if multiplier > 0 else "blocked"
    )

    return NextSessionOutlook(
        as_of=snap.as_of,
        bias=bias,
        confidence=confidence,
        base_case=base,
        alternative=alt,
        tail_risk=tail,
        watch_levels={k: v for k, v in watch.items() if v is not None},
        event_risks=event_risks,
        drivers=drivers,
        sizing_guidance=sizing,
    )
