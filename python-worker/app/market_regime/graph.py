"""LangGraph orchestration — "what should happen next".

    fetch_market_state -> derive_facts -> analyze_regime -> END

Facts are a separate node: deterministic labels are computed once and
passed to the interpreter — the same facts feed the rules fallback, so
LLM and rules can never disagree about what the numbers say.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.market_data import MarketDataService

from .agent import analyze_regime
from .facts import derive_facts
from .models import MarketSnapshot
from .state import build_market_snapshot
from app.strategy_environment import derive_strategy_environments
from app.market_events import MarketEvent, EventReaction, apply_event_policy, resolve_current_market_event
from .transition import derive_bullish_transition
from .transition_store import MarketTransitionStore
from .defensive import derive_defensive_transition
from .defensive_store import DefensiveTransitionStore
from .context_store import MarketContextStore
from .outlook import derive_next_session_outlook

logger = logging.getLogger(__name__)


class RegimeGraphState(TypedDict, total=False):
    snapshot: dict    # MarketSnapshot.model_dump(mode="json")
    facts: dict       # DimensionFacts.model_dump()
    regime: dict      # MarketRegime.model_dump(mode="json")
    transition: dict
    strategy_environments: dict
    event_aware_strategy_environments: dict
    market_event: dict
    event_reaction: dict
    next_session_outlook: dict
    context_cached: bool
    error: str


def build_market_regime_graph(
    service: Optional[MarketDataService] = None,
    model: str = "gpt-4o-mini",
    use_llm: bool = True,
    include_breadth: bool = True,
    force_refresh: bool = False,
):
    """Compile the market-regime graph bound to a data service."""
    svc = service or MarketDataService()

    async def fetch_market_state(state: RegimeGraphState) -> dict:
        try:
            cached = (None if force_refresh else
                      MarketContextStore().latest(date.today(), "swing"))
            if cached:
                return {
                    "snapshot": cached["snapshot"],
                    "facts": cached["facts"],
                    "regime": cached["regime"],
                    "transition": cached.get("transition", {}),
                    "strategy_environments": cached.get("strategy_environments", {}).get("base", cached.get("strategy_environments", {})),
                    "event_aware_strategy_environments": cached.get("strategy_environments", {}).get("event_aware", {}),
                    "market_event": cached.get("event_context"),
                    "event_reaction": cached.get("event_reaction"),
                    "context_cached": True,
                }
            snap = await build_market_snapshot(
                svc, include_breadth=include_breadth)
            return {"snapshot": snap.model_dump(mode="json"), "context_cached": False}
        except Exception as e:
            logger.error("fetch_market_state failed: %s", e)
            return {"error": str(e)}

    async def facts_node(state: RegimeGraphState) -> dict:
        if state.get("error"):
            return {}
        try:
            snap = MarketSnapshot.model_validate(state["snapshot"])
            return {"facts": derive_facts(snap).model_dump()}
        except Exception as e:
            logger.error("derive_facts failed: %s", e)
            return {"error": str(e)}

    async def analyze(state: RegimeGraphState) -> dict:
        if state.get("error"):
            return {}
        try:
            from .models import DimensionFacts
            snap = MarketSnapshot.model_validate(state["snapshot"])
            facts = DimensionFacts.model_validate(state["facts"])
            regime = analyze_regime(snap, facts, model=model, use_llm=use_llm)
            return {"regime": regime.model_dump(mode="json")}
        except Exception as e:
            logger.error("analyze_regime failed: %s", e)
            return {"error": str(e)}

    async def transition_node(state: RegimeGraphState) -> dict:
        if state.get("error"):
            return {}
        try:
            snap = MarketSnapshot.model_validate(state["snapshot"])
            from .models import DimensionFacts, MarketRegime
            facts = DimensionFacts.model_validate(state["facts"])
            transition_store = MarketTransitionStore()
            history = transition_store.history_for(snap.as_of) if snap.as_of else []
            assessment = derive_bullish_transition(snap, facts, history)
            if snap.as_of:
                transition_store.save(snap.as_of, assessment)
            # bearish twin — same facts, inverted composite, streak-
            # gated state machine. capitulation_score is an INPUT here;
            # crash_alpha never reads defensive_state (no cycle).
            defensive_store = DefensiveTransitionStore()
            d_daily = defensive_store.daily(snap.as_of) if snap.as_of else []
            d_last = d_daily[0]["stage"] if d_daily else None
            try:
                from app.options.crash_alpha import capitulation_score
                _cap = capitulation_score()
                cap = (_cap or {}).get("score")
            except Exception:
                cap = None
            d_assess = derive_defensive_transition(
                snap, facts,
                defensive_store.history_for(snap.as_of) if snap.as_of
                else [],
                daily=d_daily, last_stage=d_last,
                capitulation_score=cap,
                bull_stage=assessment.stage)
            if snap.as_of:
                defensive_store.save(snap.as_of, d_assess)
            regime = MarketRegime.model_validate(state["regime"])
            regime_data = regime.model_dump(mode="json")
            regime_data.update({
                "bullish_transition_score": assessment.score,
                "transition_stage": assessment.stage,
                "dip_buying_environment": assessment.dip_buying_environment,
                "transition_delta_1d": assessment.delta_1d,
                "transition_delta_5d": assessment.delta_5d,
                "transition_delta_20d": assessment.delta_20d,
                "transition_components": assessment.components,
                "defensive_state": d_assess.stage,
                "defensive_score": d_assess.score,
                "defensive_delta_1d": d_assess.delta_1d,
                "defensive_streak": d_assess.streak,
                "defensive_emergency": d_assess.emergency,
                "defensive_components": d_assess.components,
            })
            permissions = regime_data.get("market_permissions")
            if permissions:
                permissions["dip_buying"] = assessment.dip_buying_environment != "DISABLED"
                permissions["size_multiplier"] = min(
                    float(permissions.get("size_multiplier", 0.0)),
                    assessment.size_multiplier,
                )
                permissions.setdefault("notes", []).append(
                    f"bullish transition {assessment.score:.0f}/100 ({assessment.stage})")
            return {
                "transition": assessment.model_dump(mode="json"),
                "regime": regime_data,
            }
        except Exception as e:
            logger.error("transition assessment failed: %s", e)
            return {"error": str(e)}

    async def strategy_environment(state: RegimeGraphState) -> dict:
        if state.get("error"):
            return {}
        try:
            snap = MarketSnapshot.model_validate(state["snapshot"])
            from .models import DimensionFacts, MarketRegime
            facts = DimensionFacts.model_validate(state["facts"])
            regime = MarketRegime.model_validate(state["regime"])
            environments = derive_strategy_environments(regime, facts, snap)
            event = (
                MarketEvent.model_validate(state["market_event"])
                if state.get("market_event") else resolve_current_market_event()
            )
            reaction = EventReaction.model_validate(state["event_reaction"]) if state.get("event_reaction") else None
            base_environments = {
                horizon.value: environment.model_dump(mode="json")
                for horizon, environment in environments.items()
            }
            event_aware = {
                horizon.value: apply_event_policy(environment, event, reaction).model_dump(mode="json")
                for horizon, environment in environments.items()
            }
            event_payload = event.model_dump(mode="json") if event else None
            reaction_payload = reaction.model_dump(mode="json") if reaction else None
            MarketContextStore().save(
                # run date — one row per calendar day so same-day reruns
                # hit the fetch cache instead of overwriting the prior
                # session's row. as_of keeps the data-vintage timestamp
                # (e.g. a 4 AM pre-market run is keyed to today but
                # describes data through yesterday's close).
                session_date=date.today(),
                as_of=snap.as_of,
                horizon="swing",
                snapshot=snap.model_dump(mode="json"),
                facts=facts.model_dump(mode="json"),
                regime=regime.model_dump(mode="json"),
                transition=state.get("transition", {}),
                strategy_environments={"base": base_environments, "event_aware": event_aware},
                event_context=event_payload,
                event_reaction=reaction_payload,
                provider_routes={capability: svc.chain_for(capability) for capability in ("ohlcv", "quote")},
            )
            return {
                "strategy_environments": base_environments,
                "event_aware_strategy_environments": event_aware,
                "market_event": event_payload,
                "event_reaction": reaction_payload,
            }
        except Exception as e:
            logger.error("strategy_environment failed: %s", e)
            return {"error": str(e)}

    async def next_session_outlook_node(state: RegimeGraphState) -> dict:
        if state.get("error"):
            return {}
        try:
            snap = MarketSnapshot.model_validate(state["snapshot"])
            from .models import DimensionFacts, MarketRegime
            facts = DimensionFacts.model_validate(state["facts"])
            regime = MarketRegime.model_validate(state["regime"])
            event = (
                MarketEvent.model_validate(state["market_event"])
                if state.get("market_event") else resolve_current_market_event()
            )
            outlook = derive_next_session_outlook(snap, facts, regime, event)
            return {"next_session_outlook": outlook.model_dump(mode="json")}
        except Exception as e:
            logger.error("next-session outlook failed: %s", e)
            return {}

    graph = StateGraph(RegimeGraphState)
    graph.add_node("fetch_market_state", fetch_market_state)
    graph.add_node("derive_facts", facts_node)
    graph.add_node("analyze_regime", analyze)
    graph.add_node("transition_assessment", transition_node)
    graph.add_node("strategy_environment", strategy_environment)
    graph.add_node("next_session_outlook", next_session_outlook_node)
    graph.add_edge(START, "fetch_market_state")

    def route_market_context(state: RegimeGraphState) -> str:
        return "cached" if state.get("context_cached") else "fresh"

    graph.add_conditional_edges(
        "fetch_market_state", route_market_context,
        {"cached": "next_session_outlook", "fresh": "derive_facts"},
    )
    graph.add_edge("derive_facts", "analyze_regime")
    graph.add_edge("analyze_regime", "transition_assessment")
    graph.add_edge("transition_assessment", "strategy_environment")
    graph.add_edge("strategy_environment", "next_session_outlook")
    graph.add_edge("next_session_outlook", END)
    return graph.compile()
