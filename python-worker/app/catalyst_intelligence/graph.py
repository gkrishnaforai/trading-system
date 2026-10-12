"""LangGraph wrapper for catalyst intelligence."""
from __future__ import annotations

import asyncio
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.market_data import MarketDataService
from .engine import assess_catalyst


class CatalystGraphState(TypedDict, total=False):
    symbol: str
    catalyst: dict
    error: str


def build_catalyst_graph(service: Optional[MarketDataService] = None):
    svc = service or MarketDataService()

    async def fetch_and_assess(state: CatalystGraphState) -> dict:
        try:
            symbol = state["symbol"].upper()
            earnings, news = await asyncio.gather(
                svc.get_earnings(symbol), svc.get_news(symbol, limit=10)
            )
            return {"catalyst": assess_catalyst(symbol, earnings, news).model_dump(mode="json")}
        except Exception as exc:
            return {"error": str(exc)}

    graph = StateGraph(CatalystGraphState)
    graph.add_node("catalyst_intelligence", fetch_and_assess)
    graph.add_edge(START, "catalyst_intelligence")
    graph.add_edge("catalyst_intelligence", END)
    return graph.compile()
