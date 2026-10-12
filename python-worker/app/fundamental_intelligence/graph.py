"""LangGraph workflow for one-symbol fundamental intelligence."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.market_data import MarketDataService
from app.market_data.models import FinancialEstimate

from .engine import assess_fundamentals
from .estimate_history import compute_symbol_momentum, record_estimate_snapshots

logger = logging.getLogger(__name__)


class FundamentalGraphState(TypedDict, total=False):
    symbol: str
    fundamentals: dict
    profile: dict
    quote: dict
    estimates: list
    assessment: dict
    error: str


def build_fundamental_intelligence_graph(
    service: Optional[MarketDataService] = None,
):
    svc = service or MarketDataService()

    async def fetch(state: FundamentalGraphState) -> dict:
        try:
            fundamentals, profile, quote, estimates = await asyncio.gather(
                svc.get_fundamentals(state["symbol"].upper()),
                svc.get_profile(state["symbol"].upper()),
                svc.get_quote(state["symbol"].upper()),
                svc.get_financial_estimates(state["symbol"].upper(), period="annual", limit=10),
            )
            return {
                "fundamentals": fundamentals.model_dump(mode="json") if fundamentals else {},
                "profile": profile.model_dump(mode="json") if profile else {},
                "quote": quote.model_dump(mode="json") if quote else {},
                "estimates": [item.model_dump(mode="json") for item in estimates],
            }
        except Exception as exc:
            logger.error("fundamental fetch failed: %s", exc)
            return {"error": str(exc)}

    async def assess(state: FundamentalGraphState) -> dict:
        if state.get("error"):
            return {}
        try:
            from app.market_data.models import CompanyProfile, FundamentalsSnapshot, Quote
            fundamentals = FundamentalsSnapshot.model_validate(state["fundamentals"]) if state.get("fundamentals") else None
            profile = CompanyProfile.model_validate(state["profile"]) if state.get("profile") else None
            quote = Quote.model_validate(state["quote"]) if state.get("quote") else None
            symbol = state["symbol"].upper()
            estimates = [
                FinancialEstimate.model_validate(item)
                for item in state.get("estimates", [])
            ]
            estimate_rows = record_estimate_snapshots(symbol, estimates)
            momentum = compute_symbol_momentum(symbol, estimate_rows)
            assessment = assess_fundamentals(
                symbol, fundamentals, profile=profile, quote=quote, momentum=momentum)
            assessment_data = assessment.model_dump(mode="json")
            assessment_data["forward_estimates"] = [
                item.model_dump(mode="json") for item in estimate_rows
            ]
            return {"assessment": assessment_data}
        except Exception as exc:
            logger.error("fundamental assessment failed: %s", exc)
            return {"error": str(exc)}

    graph = StateGraph(FundamentalGraphState)
    graph.add_node("fetch_fundamentals", fetch)
    graph.add_node("assess_fundamentals", assess)
    graph.add_edge(START, "fetch_fundamentals")
    graph.add_edge("fetch_fundamentals", "assess_fundamentals")
    graph.add_edge("assess_fundamentals", END)
    return graph.compile()
