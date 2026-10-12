"""Manual-only portfolio review orchestration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.market_data import MarketDataService
from app.portfolio import DecisionHistoryWriter, PortfolioSnapshotProvider
from app.portfolio.contracts import DecisionAction, DecisionSnapshot
from app.risk.models import RiskAssessment
from app.swing_opportunity import build_swing_opportunity_graph
from app.market_regime import build_market_regime_graph
from app.swing_opportunity.models import SwingOpportunity
from app.trade_decision.models import TradeDecision
from app.market_events import resolve_current_market_event

from .models import PortfolioReviewRun, PositionReview
from .policy import assign_position_action


async def run_portfolio_review(
    portfolio_id: str,
    *,
    service: Optional[MarketDataService] = None,
    account_equity: float | None = None,
    settled_cash: float | None = None,
    unsettled_cash: float | None = None,
    buying_power: float | None = None,
    portfolio_heat: float | None = None,
    persist: bool = False,
    max_concurrency: int = 3,
) -> PortfolioReviewRun:
    """Review every current position; never creates orders or executes trades."""
    provider = PortfolioSnapshotProvider()
    # A portfolio review must refresh current position prices before creating
    # a new snapshot. Historical snapshots remain immutable/read-only.
    refreshed_count, _ = provider.refresh_prices(portfolio_id)
    snapshot = provider.load(
        portfolio_id,
        account_equity=account_equity,
        settled_cash=settled_cash,
        unsettled_cash=unsettled_cash,
        buying_power=buying_power,
        portfolio_heat=portfolio_heat,
    )
    svc = service or MarketDataService()
    market_graph_result = await build_market_regime_graph(
        service=svc, use_llm=False
    ).ainvoke({})
    if market_graph_result.get("error"):
        raise RuntimeError(market_graph_result["error"])
    shared_market_context = {
        "snapshot": market_graph_result["snapshot"],
        "facts": market_graph_result["facts"],
        "regime": market_graph_result["regime"],
        "transition": market_graph_result.get("transition", {}),
        "market_event": market_graph_result.get("market_event"),
        "event_reaction": market_graph_result.get("event_reaction"),
    }
    run_event = resolve_current_market_event(snapshot.as_of)
    run_event_payload = shared_market_context.get("market_event") or (
        run_event.model_dump(mode="json") if run_event else None)
    semaphore = asyncio.Semaphore(max_concurrency)
    symbol_graph = build_swing_opportunity_graph(service=svc, use_llm=False)

    async def review(position) -> PositionReview:
        async with semaphore:
            graph_input = {"symbol": position.symbol}
            if run_event_payload:
                graph_input["market_event"] = run_event_payload
            graph_input["shared_market_context"] = shared_market_context
            final = await symbol_graph.ainvoke(graph_input)
            if final.get("error"):
                return PositionReview(
                    symbol=position.symbol,
                    quantity=position.quantity,
                    current_price=position.current_price,
                    action="REVIEW",
                    confidence=0.9,
                    reasons=[f"symbol analysis failed: {final['error']}"],
                    data_quality="error",
                )
            opportunity = SwingOpportunity.model_validate(final["opportunity"])
            risk = RiskAssessment.model_validate(final["risk"])
            decision = TradeDecision.model_validate(final["decision"])
            return assign_position_action(
                opportunity, decision, risk,
                quantity=position.quantity,
                current_price=position.current_price,
                position=position,
                reconciliation_safe=snapshot.reconciliation_status == "RECONCILED",
                account_equity=snapshot.account_equity,
            )

    reviews = await asyncio.gather(*(review(position) for position in snapshot.positions))
    run = PortfolioReviewRun(
        run_id=str(uuid4()),
        portfolio_id=portfolio_id,
        as_of=snapshot.as_of.isoformat(),
        position_count=len(reviews),
        actions=list(reviews),
        persisted=False,
        manual_only=True,
        no_orders_created=True,
        shared_market_context_reused=True,
        max_concurrency=max_concurrency,
        reasons=(snapshot.missing_fields[:10] +
                 ([f"event context: {run_event.event_type.value} / {run_event.status.value}"] if run_event else []) +
                 [f"refreshed current prices for {refreshed_count} positions",
                  "manual review only; no orders or broker calls"]),
    )

    if persist:
        writer = DecisionHistoryWriter()
        writer.write_snapshot(snapshot)
        for review_item in reviews:
            writer.write_decision(DecisionSnapshot(
                decision_id=str(uuid4()),
                symbol=review_item.symbol,
                portfolio_id=portfolio_id,
                action=DecisionAction(review_item.action.value),
                decision_confidence=review_item.confidence,
                strategy_environment="swing",
                setup_type=review_item.setup_type,
                risk_status=review_item.risk_status,
                reasons=review_item.reasons,
                rules_version="portfolio-review-v1",
                created_at=datetime.now(timezone.utc),
            ))
        run.persisted = True
    return run
