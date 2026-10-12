"""Market regime agent — the agent layer: "what does it mean?"

Hybrid model:
  1. rules compute the deterministic composite (facts -> regime)
  2. LLM sees facts + scores + rules' call, writes the interpretation
     and MAY override the regime label with justification
  3. a rules-vs-LLM disagreement is logged as a signal

analyze_regime(snapshot, facts) -> MarketRegime
MarketRegimeAgent adapts it to BaseAgent/AgentManager; the LangGraph
node in graph.py calls the same function.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from litellm import completion
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False

from app.config import settings
from app.agents.base import AgentCapability, AgentResult, BaseAgent
from app.market_data import MarketDataService

from .facts import derive_confirmations, derive_facts
from .permissions import derive_permissions
from .models import (
    DimensionFacts, MarketRegime, MarketSnapshot, RegimeLabel,
)
from .state import build_market_snapshot

logger = logging.getLogger(__name__)

# regime label -> (direction, condition)
_DIRECTION_CONDITION = {
    RegimeLabel.BULL_LOW_VOL: ("bullish", "trend"),
    RegimeLabel.BULL_HIGH_VOL: ("bullish", "trend"),
    RegimeLabel.BULLISH_CORRECTION: ("bullish", "correction"),
    RegimeLabel.DISTRIBUTION_RISK: ("bullish", "distribution_risk"),
    RegimeLabel.DISTRIBUTION: ("bullish", "distribution"),
    RegimeLabel.MACRO_RISK_OFF: ("neutral", "risk_off"),
    RegimeLabel.BEAR: ("bearish", "bear"),
    RegimeLabel.TRANSITION: ("neutral", "transition"),
}

# base transition probabilities per regime — tilted by deterioration_score.
# Deliberately deterministic: same facts -> same probabilities, so
# evals stay meaningful until we calibrate against realized outcomes.
_TRANSITION_BASE = {
    RegimeLabel.BULL_LOW_VOL: {
        "bullish_continuation": 0.70, "sideways": 0.15,
        "correction_deepens": 0.10, "bearish_transition": 0.05},
    RegimeLabel.BULL_HIGH_VOL: {
        "bullish_continuation": 0.50, "correction_deepens": 0.25,
        "sideways": 0.15, "bearish_transition": 0.10},
    RegimeLabel.BULLISH_CORRECTION: {
        "bullish_continuation": 0.50, "correction_deepens": 0.30,
        "bearish_transition": 0.15, "sideways": 0.05},
    RegimeLabel.DISTRIBUTION_RISK: {
        "correction_deepens": 0.35, "bullish_continuation": 0.30,
        "bearish_transition": 0.25, "sideways": 0.10},
    RegimeLabel.DISTRIBUTION: {
        "correction_deepens": 0.30, "bearish_transition": 0.35,
        "bullish_continuation": 0.20, "sideways": 0.15},
    RegimeLabel.MACRO_RISK_OFF: {
        "correction_deepens": 0.30, "bearish_transition": 0.30,
        "bullish_continuation": 0.30, "sideways": 0.10},
    RegimeLabel.BEAR: {
        "bearish_continuation": 0.55, "base_building": 0.20,
        "capitulation": 0.15, "recovery": 0.10},
    RegimeLabel.TRANSITION: {
        "bullish_continuation": 0.30, "sideways": 0.30,
        "correction_deepens": 0.20, "bearish_transition": 0.20},
}

_BEAR_OUTCOMES = ("correction_deepens", "bearish_transition",
                  "bearish_continuation", "capitulation")
_BULL_OUTCOMES = ("bullish_continuation", "recovery")

SYSTEM_PROMPT = """You are a market regime interpreter for a trading system.

You are given:
  1. deterministic FACTS per dimension (labels + scores) — trust them
  2. the deterministic RULES regime call
  3. raw snapshot numbers and a short history table

Your job is INTERPRETATION. In 2-4 short paragraphs: what is the regime,
what is driving it, and what is changing.

You may disagree with the rules call. If you override it, set "regime" to
your label and explain why in "override_justification". If you agree,
return the same label and leave override_justification null.

Valid regime labels:
  bull_low_vol, bull_high_vol, bullish_correction, distribution_risk,
  distribution, macro_risk_off, bear, transition

Note: distribution_risk = internals weakening but NOT confirmed (needs
down-volume dominance, new-low acceleration, or support failure to
become distribution). Prefer distribution_risk unless confirmation
evidence is present.

Your "confidence" means confidence in the CURRENT-state classification —
it is not a forecast probability. Transition probabilities are computed
deterministically and are not yours to set.

Respond with ONLY a JSON object:
{
  "regime": "<label>",
  "secondary_regime": "<label or null>",
  "confidence": <0.0-1.0>,
  "risk_level": "low|medium|high",
  "interpretation": "<2-4 short paragraphs>",
  "override_justification": "<why you disagree with rules, or null>",
  "key_drivers": ["<driver>", "..."],
  "strategies_preferred": ["<strategy>", "..."],
  "strategies_avoid": ["<strategy>", "..."]
}"""


def _transition_probs(regime: RegimeLabel, det_score: Optional[float]
                      ) -> Dict[str, float]:
    """Deterministic transition distribution; deterioration tilts it."""
    probs = dict(_TRANSITION_BASE.get(
        regime, _TRANSITION_BASE[RegimeLabel.TRANSITION]))
    if det_score is not None and det_score < -0.3:
        # deteriorating composite -> shift mass toward the bearish tail
        shift = min(0.15, -det_score * 0.2)
        bear_keys = [k for k in probs if k in _BEAR_OUTCOMES]
        bull_keys = [k for k in probs if k in _BULL_OUTCOMES]
        per_bear = shift / max(1, len(bear_keys))
        per_bull = shift / max(1, len(bull_keys))
        for k in bear_keys:
            probs[k] = round(probs[k] + per_bear, 3)
        for k in bull_keys:
            probs[k] = round(max(0.02, probs[k] - per_bull), 3)
    return probs


def analyze_regime(
    snapshot: MarketSnapshot,
    facts: Optional[DimensionFacts] = None,
    model: str = "gpt-4o-mini",
    use_llm: bool = True,
) -> MarketRegime:
    """Classify the regime. Rules composite first; LLM may override."""
    facts = facts or derive_facts(snapshot)
    rules = _compose_rules(snapshot, facts)

    llm_ok = (use_llm and LITELLM_AVAILABLE and (
        settings.openai_api_key or settings.anthropic_api_key
        or getattr(settings, "litellm_proxy_url", None)))
    if not llm_ok:
        return rules

    try:
        llm = _analyze_with_llm(snapshot, facts, rules, model)
    except Exception as e:
        logger.warning("LLM regime analysis failed (%s); using rules", e)
        return rules

    if llm.regime != rules.regime:
        logger.warning(
            "LLM overrode rules regime: %s -> %s (%s)",
            rules.regime.value, llm.regime.value, llm.override_justification)
        llm.regime_overridden = True
        llm.rules_regime = rules.regime
    else:
        llm.rules_regime = rules.regime
    # deterministic spine always wins for these fields; probs recomputed
    # for the FINAL regime label if the LLM overrode the rules call
    llm.transition_probabilities = _transition_probs(
        llm.regime, rules.deterioration_score)
    llm.trend_score = rules.trend_score
    llm.deterioration_score = rules.deterioration_score
    llm.change_components = rules.change_components
    llm.confirmation_signals = rules.confirmation_signals
    # permissions recomputed for the FINAL label if the LLM overrode rules
    llm.market_permissions = derive_permissions(
        llm.regime, facts, snapshot, llm.confirmation_signals)
    llm.direction, llm.condition = _DIRECTION_CONDITION[llm.regime]
    llm.snapshot = snapshot
    return llm


def _f(v: Optional[float], fmt: str = "{:.2f}") -> str:
    return fmt.format(v) if isinstance(v, (int, float)) else "n/a"


def _prompt(snapshot: MarketSnapshot, facts: DimensionFacts,
            rules: MarketRegime) -> str:
    t, m, b, v, p, s = (snapshot.trend, snapshot.momentum, snapshot.breadth,
                        snapshot.volatility, snapshot.participation,
                        snapshot.structure)
    macro_lines = "\n".join(
        f"    {i.name}: {_f(i.value)} ({i.chg1d:+.1%} 1d, {i.chg5d:+.1%} 5d)"
        for i in snapshot.macro.instruments.values()
        if i.value is not None and i.chg1d is not None
        and i.chg5d is not None
    ) or "    unavailable"
    history_lines = "\n".join(
        f"    {h.offset_days:>3}d ago: SPY={_f(h.spy)} RSI={_f(h.rsi, '{:.1f}')} "
        f"breadth50={h.breadth_pct50}% VIX={_f(h.vix, '{:.1f}')} 10Y={_f(h.us10y)}"
        for h in snapshot.history
    )
    sector_lines = ", ".join(
        f"{x.symbol} {x.ret5:+.1%}" for x in p.sectors if x.ret5 is not None)
    scores = ", ".join(f"{k} {v:+.2f}" for k, v in facts.scores.items())

    return f"""
    Deterministic facts + scores:
      trend={facts.trend} momentum={facts.momentum} breadth={facts.breadth}
      volatility={facts.volatility} participation={facts.participation}
      macro={facts.macro} structure={facts.structure}
      scores: {scores}
      trend_score: {_f(facts.trend_score)}  deterioration_score: {_f(facts.deterioration_score)}
      drivers: {', '.join(facts.drivers) or 'none'}

    RULES composite call: {rules.regime.value} (direction={rules.direction},
    condition={rules.condition}, risk={rules.risk_level})

    Snapshot:
      SPY {t.spy_price} | EMA20 {_f(t.ema20)} SMA20 {_f(t.sma20)} SMA50 {_f(t.sma50)} SMA200 {_f(t.sma200)}
      distances: SMA50 {t.dist_sma50:+.2%} SMA200 {t.dist_sma200:+.2%}
      slopes (%/day): SMA20 {_f(t.sma20_slope)} SMA50 {_f(t.sma50_slope)} SMA200 {_f(t.sma200_slope)}
      RSI14 {_f(m.rsi14, '{:.1f}')} (5d ago {_f(m.rsi_5d_ago, '{:.1f}')}, chg {_f(m.rsi_5d_change, '{:+.1f}')})
      MACD hist {_f(m.macd_hist)} | ROC5 {_f(m.roc5)} ROC20 {_f(m.roc20)}
      returns: 1d {_f(m.ret1)} 5d {_f(m.ret5)} 20d {_f(m.ret20)}
      breadth({b.universe_size} names): >SMA20 {b.pct_above_sma20}% >SMA50 {b.pct_above_sma50}% >SMA200 {b.pct_above_sma200}%
        A/D {b.advances}/{b.declines} NH/NL {b.new_highs}/{b.new_lows} upVol {b.up_volume_ratio}
        chg 1d {b.breadth_chg_1d} 5d {b.breadth_chg_5d} 20d {b.breadth_chg_20d}
      VIX {_f(v.vix, '{:.1f}')} (5d chg {_f(v.vix_chg_5d)}, 20d pctile {_f(v.vix_pctile_20d)}, term {_f(v.vix_term_ratio)})
      ATR% {_f(v.atr_pct)} | realized vol 5d {_f(v.rvol5)} 20d {_f(v.rvol20)}
      structure: SPY hh={s.spy_higher_high} hl={s.spy_higher_low} | dist 20dH {s.dist_from_20d_high} 52wH {s.dist_from_52w_high}
      sectors 5d: {sector_lines}
      rel strength vs SPY (5d): {p.rel_strength_5d}
      macro:
{macro_lines}

    History:
{history_lines}
    """


def _analyze_with_llm(
    snapshot: MarketSnapshot, facts: DimensionFacts,
    rules: MarketRegime, model: str,
) -> MarketRegime:
    api_key = None
    if model.startswith(("claude", "anthropic")):
        api_key = settings.anthropic_api_key
    elif not model.startswith(("ollama", "local")):
        api_key = settings.openai_api_key

    t0 = time.monotonic()
    response = completion(
        model=model,
        api_key=api_key,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _prompt(snapshot, facts, rules)},
        ],
        temperature=0.2,
        max_tokens=900,
        response_format={"type": "json_object"},
    )
    latency_ms = (time.monotonic() - t0) * 1000

    data = json.loads(response.choices[0].message.content)
    data["source"] = "llm"
    data["dimensions"] = {
        k: v for k, v in facts.model_dump().items()
        if k in ("trend", "momentum", "breadth", "volatility",
                 "participation", "macro", "structure")
    }
    regime = MarketRegime.model_validate(data)
    logger.info("LLM regime: %s (%.0f%% conf) in %.0fms",
                regime.regime, regime.confidence * 100, latency_ms)
    return regime


def _compose_rules(
    snapshot: MarketSnapshot, facts: DimensionFacts
) -> MarketRegime:
    """Deterministic composition — facts -> multi-label regime."""
    dims = {k: getattr(facts, k) for k in
            ("trend", "momentum", "breadth", "volatility",
             "participation", "macro", "structure")}
    secondary = None
    preferred: List[str] = []
    avoid: List[str] = []

    if facts.trend == "bearish":
        regime, risk, conf = RegimeLabel.BEAR, "high", 0.7
        if facts.macro in ("risk_off", "mildly_risk_off"):
            secondary = RegimeLabel.MACRO_RISK_OFF
        preferred = ["defensive sectors", "cash", "short-duration risk"]
        avoid = ["breakout longs", "high-beta growth"]
    elif facts.macro == "risk_off" and facts.momentum in ("weak", "weakening"):
        regime, risk, conf = RegimeLabel.MACRO_RISK_OFF, "high", 0.6
        secondary = RegimeLabel.BULLISH_CORRECTION
        avoid = ["aggressive longs", "leverage"]
    elif facts.trend == "bullish_weakening" and facts.structure == "under_pressure":
        # distribution vs distribution_risk: confirmed only with hard
        # evidence — collapsing breadth, down-volume dominance, new lows
        # outpacing new highs, or price already below SMA50.
        b = snapshot.breadth
        confirmed = (
            facts.breadth == "deteriorating"
            or (b.up_volume_ratio is not None and b.up_volume_ratio < 0.45)
            or (b.new_lows > b.new_highs > 0)
            or snapshot.trend.above_sma50 is False
        )
        if confirmed:
            regime, risk, conf = RegimeLabel.DISTRIBUTION, "medium", 0.6
            secondary = RegimeLabel.BULLISH_CORRECTION
            preferred = ["profit-taking on strength", "hedging",
                         "quality over beta"]
            avoid = ["chasing highs", "dip-buying before breadth stabilizes"]
        else:
            regime, risk, conf = RegimeLabel.DISTRIBUTION_RISK, "medium", 0.6
            secondary = RegimeLabel.BULLISH_CORRECTION
            preferred = ["profit-taking on strength", "quality over beta",
                         "watch confirmation signals"]
            avoid = ["chasing highs", "aggressive adds before confirmation"]
    elif facts.trend in ("bullish", "bullish_weakening") and (
        facts.breadth in ("weak", "weakening", "deteriorating")
        or facts.momentum == "weakening"
    ):
        regime, risk, conf = RegimeLabel.BULLISH_CORRECTION, "medium", 0.65
        if facts.breadth == "deteriorating":
            secondary = RegimeLabel.DISTRIBUTION
        preferred = ["buy high-quality setups on pullbacks",
                     "favor relative-strength leaders",
                     "wait for higher-low confirmation",
                     "reduce position size"]
        avoid = ["chasing extended stocks", "aggressive leverage",
                 "buying falling knives", "assuming every dip is a buy"]
    elif facts.trend == "bullish" and (
            "elevated" in facts.volatility or "high" in facts.volatility):
        regime, risk, conf = RegimeLabel.BULL_HIGH_VOL, "medium", 0.6
        preferred = ["reduced size", "wider stops"]
        avoid = ["tight stops", "mean reversion shorts"]
    elif facts.trend == "bullish" and facts.breadth in (
            "strong", "improving", "neutral"):
        regime, risk, conf = RegimeLabel.BULL_LOW_VOL, "low", 0.7
        preferred = ["trend following", "momentum longs"]
        avoid = ["counter-trend shorts"]
    elif facts.trend == "bullish":
        regime, risk, conf = RegimeLabel.BULL_HIGH_VOL, "medium", 0.55
        preferred = ["trend following with caution"]
    else:
        regime, risk, conf = RegimeLabel.TRANSITION, "medium", 0.4
        preferred = ["wait for confirmation", "small size"]
        avoid = ["conviction positions"]

    direction, condition = _DIRECTION_CONDITION[regime]
    confirmations = derive_confirmations(snapshot)
    return MarketRegime(
        regime=regime,
        secondary_regime=secondary,
        direction=direction,
        condition=condition,
        dimensions=dims,
        confidence=conf,
        risk_level=risk,
        trend_score=facts.trend_score,
        deterioration_score=facts.deterioration_score,
        change_components=facts.scores,
        transition_probabilities=_transition_probs(
            regime, facts.deterioration_score),
        confirmation_signals=confirmations,
        market_permissions=derive_permissions(
            regime, facts, snapshot, confirmations),
        rules_regime=regime,
        interpretation="; ".join(facts.drivers) or "no strong drivers",
        key_drivers=facts.drivers,
        strategies_preferred=preferred,
        strategies_avoid=avoid,
        source="rules",
        snapshot=snapshot,
    )


class MarketRegimeAgent(BaseAgent):
    """Regime classifier agent — pluggable into AgentManager."""

    def __init__(self, service: Optional[MarketDataService] = None,
                 model: str = "gpt-4o-mini", use_llm: bool = True,
                 include_breadth: bool = True):
        self.service = service or MarketDataService()
        self.model = model
        self.use_llm = use_llm
        self.include_breadth = include_breadth

    def get_name(self) -> str:
        return "market_regime"

    def get_capabilities(self) -> List[AgentCapability]:
        return [AgentCapability.RISK_ASSESSMENT, AgentCapability.RESEARCH]

    def can_handle(self, task: str, context: Dict[str, Any]) -> bool:
        return task in {"analyze_regime", "market_status"}

    def is_available(self) -> bool:
        return bool(self.service.providers)

    def execute(self, task: str, context: Dict[str, Any], **kwargs) -> AgentResult:
        import asyncio
        from .graph import build_market_regime_graph
        try:
            graph = build_market_regime_graph(
                self.service, model=self.model, use_llm=self.use_llm,
                include_breadth=context.get("breadth", self.include_breadth),
            )
            final = asyncio.run(graph.ainvoke({}))
            if final.get("error") or not final.get("regime"):
                return AgentResult(
                    success=False, result={},
                    error=final.get("error", "no regime produced"),
                )
            regime = MarketRegime.model_validate(final["regime"])
            snap = regime.snapshot
            return AgentResult(
                success=True,
                result=regime.model_dump(mode="json"),
                metadata={
                    "provider": snap.provider if snap else None,
                    "as_of": snap.as_of.isoformat() if snap and snap.as_of else None,
                    "source": regime.source,
                    "regime_overridden": regime.regime_overridden,
                    "rules_regime": regime.rules_regime.value
                    if regime.rules_regime else None,
                    "coverage": snap.coverage if snap else {},
                    "provider_attempts": [
                        {"provider": a.provider, "capability": a.capability,
                         "ok": a.ok, "error": a.error_type}
                        for a in self.service.attempts
                    ],
                },
            )
        except Exception as e:
            logger.error("market_regime agent failed: %s", e, exc_info=True)
            return AgentResult(success=False, result={}, error=str(e))
