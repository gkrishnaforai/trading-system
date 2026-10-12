"""LangGraph workflow for one-symbol swing opportunity analysis."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.market_data import MarketDataService
from app.market_regime.agent import analyze_regime
from app.market_regime.facts import derive_facts
from app.market_regime.models import DimensionFacts, MarketRegime, MarketSnapshot
from app.market_regime.state import build_market_snapshot
from app.strategy_environment import StrategyHorizon, derive_strategy_environments
from app.risk import PortfolioConstraints, assess_risk
from app.accumulation import build_accumulation_plan
from app.position_management import manage_position
from app.fundamental_intelligence.engine import assess_fundamentals
from app.fundamental_intelligence.estimate_history import (
    compute_symbol_momentum,
    record_estimate_snapshots,
)
from app.fundamental_intelligence.momentum_store import FundamentalMomentumStore
from app.fundamental_intelligence.fair_value_bridge import resolve_fair_value_band
from app.trade_decision import decide_trade
from app.trading_intent import TradingIntent, validate_horizon_support
from app.portfolio import AllocationResult, PortfolioSnapshot, allocate_portfolio
from app.orders import create_order_plan
from app.market_events import MarketEvent, EventReaction, apply_event_policy, resolve_current_market_event
from app.catalyst_intelligence.engine import assess_catalyst
from app.market_regime.transition import derive_bullish_transition
from app.market_regime.transition_store import MarketTransitionStore

from .engine import analyze_stock, detect_setup
from .models import SwingOpportunity

logger = logging.getLogger(__name__)

_SECTOR_ETFS = {
    "Technology": "XLK", "Information Technology": "XLK",
    "Financial Services": "XLF", "Financials": "XLF",
    "Energy": "XLE", "Healthcare": "XLV", "Health Care": "XLV",
    "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP",
    "Industrials": "XLI", "Utilities": "XLU", "Real Estate": "XLRE",
    "Basic Materials": "XLB", "Communication Services": "XLC",
}


class SwingOpportunityState(TypedDict, total=False):
    symbol: str
    market_snapshot: dict
    market_facts: dict
    market_regime: dict
    transition: dict
    swing_environment: dict
    event_aware_swing_environment: dict
    market_event: dict
    event_reaction: dict
    shared_market_context: dict
    symbol_data: dict
    stock: dict
    fundamentals: dict
    catalyst: dict
    setup: dict
    opportunity: dict
    risk_constraints: dict
    risk: dict
    decision: dict
    accumulation_plan: dict
    position_management: dict
    current_position: float
    current_weight: float
    target_weight: float
    trading_intent: dict
    portfolio: dict
    allocation: dict
    order_plan: dict
    error: str


def build_swing_opportunity_graph(
    service: Optional[MarketDataService] = None,
    *,
    model: str = "gpt-4o-mini",
    use_llm: bool = False,
):
    """Compile the deterministic swing opportunity graph."""
    svc = service or MarketDataService()

    async def market_node(state: SwingOpportunityState) -> dict:
        try:
            shared = state.get("shared_market_context")
            if shared:
                from app.market_events.models import EventReaction, MarketEvent
                from app.market_regime.models import DimensionFacts, MarketRegime, MarketSnapshot
                snapshot = MarketSnapshot.model_validate(shared["snapshot"])
                facts = DimensionFacts.model_validate(shared["facts"])
                regime_data = dict(shared["regime"])
                regime = MarketRegime.model_validate(regime_data)
                environments = derive_strategy_environments(regime, facts, snapshot)
                transition_data = shared.get("transition", {})
                event_payload = state.get("market_event") or shared.get("market_event")
                reaction_payload = state.get("event_reaction") or shared.get("event_reaction")
                event = MarketEvent.model_validate(event_payload) if event_payload else None
                reaction = EventReaction.model_validate(reaction_payload) if reaction_payload else None
                base_environment = environments[StrategyHorizon.SWING]
                event_environment = apply_event_policy(base_environment, event, reaction)
                return {
                    "market_snapshot": snapshot.model_dump(mode="json"),
                    "market_facts": facts.model_dump(),
                    "market_regime": regime_data,
                    "transition": transition_data,
                    "swing_environment": base_environment.model_dump(mode="json"),
                    "event_aware_swing_environment": event_environment.model_dump(mode="json"),
                    "market_event": event.model_dump(mode="json") if event else None,
                    "event_reaction": reaction.model_dump(mode="json") if reaction else None,
                }

            snapshot = await build_market_snapshot(svc)
            facts = derive_facts(snapshot)
            regime = analyze_regime(snapshot, facts, model=model, use_llm=use_llm)
            environments = derive_strategy_environments(regime, facts, snapshot)
            transition_store = MarketTransitionStore()
            history = transition_store.history_for(snapshot.as_of) if snapshot.as_of else []
            transition = derive_bullish_transition(snapshot, facts, history)
            if snapshot.as_of:
                transition_store.save(snapshot.as_of, transition)
            regime_data = regime.model_dump(mode="json")
            regime_data.update({
                "bullish_transition_score": transition.score,
                "transition_stage": transition.stage,
                "dip_buying_environment": transition.dip_buying_environment,
                "transition_delta_1d": transition.delta_1d,
                "transition_delta_5d": transition.delta_5d,
                "transition_delta_20d": transition.delta_20d,
                "transition_components": transition.components,
            })
            permissions = regime_data.get("market_permissions")
            if permissions:
                permissions["dip_buying"] = transition.dip_buying_environment != "DISABLED"
                permissions["size_multiplier"] = min(
                    float(permissions.get("size_multiplier", 0.0)),
                    transition.size_multiplier,
                )
                permissions.setdefault("notes", []).append(
                    f"bullish transition {transition.score:.0f}/100 ({transition.stage})")
            event = (
                MarketEvent.model_validate(state["market_event"])
                if state.get("market_event") else resolve_current_market_event()
            )
            reaction = EventReaction.model_validate(state["event_reaction"]) if state.get("event_reaction") else None
            base_environment = environments[StrategyHorizon.SWING]
            event_environment = apply_event_policy(base_environment, event, reaction)
            return {
                "market_snapshot": snapshot.model_dump(mode="json"),
                "market_facts": facts.model_dump(),
                "market_regime": regime_data,
                "transition": transition.model_dump(mode="json"),
                "swing_environment": base_environment.model_dump(mode="json"),
                "event_aware_swing_environment": event_environment.model_dump(mode="json"),
                "market_event": event.model_dump(mode="json") if event else None,
                "event_reaction": reaction.model_dump(mode="json") if reaction else None,
            }
        except Exception as exc:
            logger.error("swing market node failed: %s", exc)
            return {"error": str(exc)}

    async def symbol_data_node(state: SwingOpportunityState) -> dict:
        """Fetch shared read-only inputs once for parallel analysis branches."""
        if state.get("error"):
            return {}
        try:
            symbol = state["symbol"].upper()
            profile, bars, spy_bars, fundamentals, quote, earnings, news, estimates = await asyncio.gather(
                svc.get_profile(symbol),
                svc.get_ohlcv(symbol, period="1y"),
                svc.get_ohlcv("SPY", period="1y", prefer=["fmp", "yahoo_finance"]),
                svc.get_fundamentals(symbol),
                svc.get_quote(symbol),
                svc.get_earnings(symbol),
                svc.get_news(symbol, limit=10),
                svc.get_financial_estimates(symbol, period="annual", limit=10),
            )
            sector = profile.sector if profile else None
            sector_symbol = _SECTOR_ETFS.get(sector or "")
            sector_bars = (
                await svc.get_ohlcv(sector_symbol, period="1y", prefer=["yahoo_finance"])
                if sector_symbol else []
            )
            return {"symbol_data": {
                "symbol": symbol,
                "profile": profile.model_dump(mode="json") if profile else {},
                "bars": bars,
                "spy_bars": spy_bars,
                "sector_bars": sector_bars,
                "fundamentals": fundamentals.model_dump(mode="json") if fundamentals else {},
                "quote": quote.model_dump(mode="json") if quote else {},
                "earnings": [item.model_dump(mode="json") for item in earnings],
                "news": [item.model_dump(mode="json") for item in news],
                "estimates": [item.model_dump(mode="json") for item in estimates],
                "sector": sector,
                "sector_symbol": sector_symbol,
            }}
        except Exception as exc:
            logger.error("swing symbol data node failed: %s", exc)
            return {"error": str(exc)}

    async def technical_node(state: SwingOpportunityState) -> dict:
        if state.get("error"):
            return {}
        try:
            data = state["symbol_data"]
            stock = analyze_stock(
                data["symbol"], data["bars"], data["spy_bars"], data["sector_bars"],
                sector=data["sector"], sector_symbol=data["sector_symbol"],
            )
            return {"stock": stock.model_dump(mode="json")}
        except Exception as exc:
            logger.error("swing technical node failed: %s", exc)
            return {"error": str(exc)}

    async def fundamental_node(state: SwingOpportunityState) -> dict:
        if state.get("error"):
            return {}
        try:
            from app.market_data.models import CompanyProfile, FinancialEstimate, FundamentalsSnapshot, Quote
            data = state["symbol_data"]
            fundamentals = FundamentalsSnapshot.model_validate(data["fundamentals"]) if data["fundamentals"] else None
            profile = CompanyProfile.model_validate(data["profile"]) if data["profile"] else None
            quote = Quote.model_validate(data["quote"]) if data["quote"] else None
            try:
                estimates = [
                    FinancialEstimate.model_validate(item)
                    for item in data.get("estimates", [])
                ]
                estimate_rows = record_estimate_snapshots(data["symbol"], estimates)
                momentum = compute_symbol_momentum(data["symbol"], estimate_rows)
            except Exception:
                try:
                    momentum = FundamentalMomentumStore().latest(data["symbol"].upper())
                except Exception:
                    momentum = None
            try:
                fair_value_band = await asyncio.to_thread(
                    resolve_fair_value_band, data["symbol"])
            except Exception:
                fair_value_band = None
            assessment = assess_fundamentals(
                data["symbol"], fundamentals, profile=profile, quote=quote,
                momentum=momentum, fair_value_band=fair_value_band)
            return {"fundamentals": assessment.model_dump(mode="json")}
        except Exception as exc:
            logger.error("swing fundamental node failed: %s", exc)
            return {"error": str(exc)}

    async def catalyst_node(state: SwingOpportunityState) -> dict:
        if state.get("error"):
            return {}
        try:
            data = state["symbol_data"]
            from app.market_data.models import EarningsEvent, NewsItem
            earnings = [EarningsEvent.model_validate(item) for item in data.get("earnings", [])]
            news = [NewsItem.model_validate(item) for item in data.get("news", [])]
            from app.market_data import indicators
            price_change_1d = indicators.returns(data.get("bars", []), 1)
            volume_ratio = indicators.volume_ratio(data.get("bars", []), 20)
            catalyst = assess_catalyst(
                data["symbol"], earnings, news,
                price_change_1d=price_change_1d,
                volume_ratio=volume_ratio,
            )
            return {"catalyst": catalyst.model_dump(mode="json")}
        except Exception as exc:
            logger.error("swing catalyst node failed: %s", exc)
            return {"error": str(exc)}

    async def setup_node(state: SwingOpportunityState) -> dict:
        if state.get("error"):
            return {}
        try:
            regime = MarketRegime.model_validate(state["market_regime"])
            from app.strategy_environment.models import StrategyEnvironment
            environment = StrategyEnvironment.model_validate(state["swing_environment"])
            event_policy = "NORMAL"
            event_new_entries_allowed = True
            if state.get("event_aware_swing_environment"):
                from app.market_events import EventAwareStrategyEnvironment
                event_environment = EventAwareStrategyEnvironment.model_validate(
                    state["event_aware_swing_environment"])
                environment = StrategyEnvironment.model_validate({
                    **environment.model_dump(mode="json"),
                    "quality": event_environment.quality,
                    "score": event_environment.score,
                    "confidence": event_environment.confidence,
                    "long_permission": event_environment.long_permission,
                    "short_permission": event_environment.short_permission,
                    "breakout_permission": event_environment.breakout_permission,
                    "pullback_permission": event_environment.pullback_permission,
                    "size_multiplier": event_environment.size_multiplier,
                    "pacing": event_environment.pacing,
                    "reasons": event_environment.reasons,
                    "data_sufficient": event_environment.data_sufficient,
                })
                event_policy = event_environment.event_policy
                event_new_entries_allowed = event_environment.new_entries_allowed
            from .models import StockAnalysis
            stock = StockAnalysis.model_validate(state["stock"])
            setup = detect_setup(stock, regime, environment)
            quality = setup.quality.value
            next_step = "RISK_ASSESSMENT" if quality in {"high", "medium"} else "WAIT"
            if not stock.data_quality.sufficient:
                next_step, quality = "UNAVAILABLE", "unavailable"
            fundamental_data = state.get("fundamentals", {})
            catalyst_data = state.get("catalyst", {})
            transition_data = state.get("transition", {})
            catalyst_policy = catalyst_data.get("new_entry_policy", "NORMAL")
            market_permissions = regime.market_permissions
            market_entry_permission = (
                "NORMAL" if market_permissions and market_permissions.normal_long else
                "SELECTIVE" if market_permissions and market_permissions.selective_long else
                "BLOCKED" if market_permissions else "UNKNOWN"
            )
            if catalyst_policy in {"RESTRICTED", "LIMITED"}:
                event_new_entries_allowed = False
                event_policy = f"CATALYST_{catalyst_policy}"
            cross_layer_reasons = list(setup.reasons)
            if fundamental_data.get("data_quality") in {"insufficient", "partial"}:
                cross_layer_reasons.append("fundamental coverage is incomplete")
            if catalyst_data.get("new_entry_policy") in {"RESTRICTED", "LIMITED"}:
                cross_layer_reasons.append("earnings/news catalyst policy restricts new entries")
            quality_score = fundamental_data.get("quality_score")
            business_quality = (
                "EXCEPTIONAL" if quality_score is not None and quality_score >= 85 else
                "HIGH" if quality_score is not None and quality_score >= 70 else
                "MEDIUM" if quality_score is not None and quality_score >= 50 else
                "UNKNOWN"
            )
            thesis_status = "INTACT" if business_quality in {"EXCEPTIONAL", "HIGH"} else "UNKNOWN"
            setup_readiness = (
                "CONFIRMED" if quality == "high" else
                "DEVELOPING" if quality == "medium" else
                "NOT_READY"
            )
            entry_state = "READY" if setup_readiness == "CONFIRMED" and event_new_entries_allowed else "WAIT"
            opportunity = SwingOpportunity(
                symbol=state["symbol"].upper(),
                as_of=state.get("market_snapshot", {}).get("as_of"),
                market_regime=regime.direction,
                market_condition=regime.condition,
                swing_environment=environment.quality.value,
                swing_size_multiplier=environment.size_multiplier,
                stock=stock,
                fundamentals=fundamental_data,
                catalyst=catalyst_data,
                event_policy=event_policy,
                event_new_entries_allowed=event_new_entries_allowed,
                market_entry_permission=market_entry_permission,
                bullish_transition_score=transition_data.get("score"),
                transition_stage=transition_data.get("stage", "UNKNOWN"),
                dip_buying_environment=transition_data.get("dip_buying_environment", "UNKNOWN"),
                setup=setup,
                business_quality=business_quality,
                thesis_status=thesis_status,
                setup_readiness=setup_readiness,
                entry_state=entry_state,
                opportunity_quality=quality,
                opportunity_score=setup.score,
                next_step=next_step,
                reasons=cross_layer_reasons,
                provenance={"rules_version": "swing-opportunity-v1", "source": "deterministic"},
            )
            return {"setup": setup.model_dump(mode="json"), "opportunity": opportunity.model_dump(mode="json")}
        except Exception as exc:
            logger.error("swing setup node failed: %s", exc)
            return {"error": str(exc)}

    async def risk_node(state: SwingOpportunityState) -> dict:
        if state.get("error"):
            return {}
        try:
            from .models import SwingOpportunity
            opportunity = SwingOpportunity.model_validate(state["opportunity"])
            regime = MarketRegime.model_validate(state["market_regime"])
            constraints = PortfolioConstraints.model_validate(state.get("risk_constraints", {}))
            risk = assess_risk(opportunity, regime, constraints)
            return {"risk": risk.model_dump(mode="json")}
        except Exception as exc:
            logger.error("swing risk node failed: %s", exc)
            return {"error": str(exc)}

    async def allocation_node(state: SwingOpportunityState) -> dict:
        if state.get("error"):
            return {}
        try:
            if not state.get("trading_intent"):
                return {"allocation": {
                    "status": "insufficient_data",
                    "allowed": False,
                    "blocking_reasons": ["trading intent not supplied"],
                    "provenance": {"source": "deterministic"},
                }}
            intent = TradingIntent.model_validate(state["trading_intent"])
            horizon_reasons = validate_horizon_support(intent, daily_data_only=True)
            opportunity = SwingOpportunity.model_validate(state["opportunity"])
            from app.risk.models import RiskAssessment
            from app.trade_decision.models import TradeDecision
            risk = RiskAssessment.model_validate(state["risk"])
            decision = TradeDecision.model_validate(state["decision"])
            if horizon_reasons:
                return {"allocation": {
                    "status": "blocked", "allowed": False,
                    "blocking_reasons": horizon_reasons,
                    "provenance": {"rules_version": "portfolio-allocation-v1"},
                }}
            portfolio = PortfolioSnapshot.model_validate(state.get("portfolio", {
                "cash": intent.account_equity,
                "equity": intent.account_equity,
                "invested_value": 0,
            }))
            result = allocate_portfolio(
                intent, portfolio, decision, risk,
                price=opportunity.stock.technicals.price or 0,
                sector=opportunity.stock.sector,
            )
            return {"allocation": result.model_dump(mode="json")}
        except Exception as exc:
            logger.error("swing allocation node failed: %s", exc)
            return {"error": str(exc)}

    async def order_plan_node(state: SwingOpportunityState) -> dict:
        if state.get("error") or not state.get("trading_intent"):
            return {}
        try:
            intent = TradingIntent.model_validate(state["trading_intent"])
            allocation = AllocationResult.model_validate(state["allocation"])
            from app.trade_decision.models import TradeDecision
            from app.risk.models import RiskAssessment
            decision = TradeDecision.model_validate(state["decision"])
            risk = RiskAssessment.model_validate(state["risk"])
            if not allocation.allowed:
                return {}
            plan = create_order_plan(intent, decision, allocation, risk)
            return {"order_plan": plan.model_dump(mode="json")}
        except Exception as exc:
            logger.error("swing order-plan node failed: %s", exc)
            return {"error": str(exc)}

    graph = StateGraph(SwingOpportunityState)
    graph.add_node("market_context", market_node)
    graph.add_node("symbol_data", symbol_data_node)
    graph.add_node("technical_analysis", technical_node)
    graph.add_node("fundamental_analysis", fundamental_node)
    graph.add_node("catalyst_analysis", catalyst_node)
    graph.add_node("setup_detection", setup_node)
    async def decision_node(state: SwingOpportunityState) -> dict:
        if state.get("error"):
            return {}
        try:
            from .models import SwingOpportunity
            from app.risk.models import RiskAssessment
            opportunity = SwingOpportunity.model_validate(state["opportunity"])
            risk = RiskAssessment.model_validate(state["risk"])
            decision = decide_trade(opportunity, risk)
            return {"decision": decision.model_dump(mode="json")}
        except Exception as exc:
            logger.error("swing decision node failed: %s", exc)
            return {"error": str(exc)}

    async def accumulation_node(state: SwingOpportunityState) -> dict:
        if state.get("error"):
            return {}
        try:
            from app.risk.models import RiskAssessment
            from app.trade_decision.models import TradeDecision
            opportunity = SwingOpportunity.model_validate(state["opportunity"])
            risk = RiskAssessment.model_validate(state["risk"])
            decision = TradeDecision.model_validate(state["decision"])
            plan = build_accumulation_plan(
                opportunity, decision, risk,
                current_position=float(state.get("current_position", 0.0)),
                current_weight=state.get("current_weight"),
                target_weight=state.get("target_weight"),
            )
            opportunity_data = opportunity.model_dump(mode="json")
            opportunity_data["accumulation_plan"] = plan.model_dump(mode="json")
            return {
                "accumulation_plan": plan.model_dump(mode="json"),
                "opportunity": opportunity_data,
            }
        except Exception as exc:
            logger.error("swing accumulation plan failed: %s", exc)
            return {"error": str(exc)}

    graph.add_node("risk_assessment", risk_node)
    graph.add_node("trade_decision", decision_node)
    async def position_management_node(state: SwingOpportunityState) -> dict:
        if state.get("error"):
            return {}
        try:
            from app.risk.models import RiskAssessment
            from app.trade_decision.models import TradeDecision
            opportunity = SwingOpportunity.model_validate(state["opportunity"])
            risk = RiskAssessment.model_validate(state["risk"])
            decision = TradeDecision.model_validate(state["decision"])
            management = manage_position(
                opportunity, decision, risk,
                current_position=float(state.get("current_position", 0.0)),
                current_weight=state.get("current_weight"),
                target_weight=state.get("target_weight"),
                reconciliation_safe=bool(state.get("reconciliation_safe", True)),
            )
            opportunity_data = opportunity.model_dump(mode="json")
            opportunity_data["position_management"] = management.model_dump(mode="json")
            return {
                "position_management": management.model_dump(mode="json"),
                "opportunity": opportunity_data,
            }
        except Exception as exc:
            logger.error("swing position management failed: %s", exc)
            return {"error": str(exc)}

    graph.add_node("accumulation_plan", accumulation_node)
    graph.add_node("position_management", position_management_node)
    graph.add_node("portfolio_allocation", allocation_node)
    graph.add_node("order_planning", order_plan_node)
    graph.add_edge(START, "market_context")
    graph.add_edge("market_context", "symbol_data")
    graph.add_edge("symbol_data", "technical_analysis")
    graph.add_edge("symbol_data", "fundamental_analysis")
    graph.add_edge("symbol_data", "catalyst_analysis")
    graph.add_edge("technical_analysis", "setup_detection")
    graph.add_edge("fundamental_analysis", "setup_detection")
    graph.add_edge("catalyst_analysis", "setup_detection")
    graph.add_edge("setup_detection", "risk_assessment")
    graph.add_edge("risk_assessment", "trade_decision")
    graph.add_edge("trade_decision", "accumulation_plan")
    graph.add_edge("accumulation_plan", "position_management")
    graph.add_edge("position_management", "portfolio_allocation")
    graph.add_edge("portfolio_allocation", "order_planning")
    graph.add_edge("order_planning", END)
    return graph.compile()
