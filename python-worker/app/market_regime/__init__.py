"""Market regime agent layer — sits above app.market_data.

Layer mapping:
  provider layer  -> app.market_data.providers (how do I get data)
  data layer      -> app.market_data.models    (what does the data look like)
  quant layer     -> app.market_data.indicators + state.py (what do the numbers say)
  facts           -> facts.py                  (deterministic labels)
  agent layer     -> agent.py                  (what does it mean)
  orchestration   -> graph.py                  (what should happen next)
"""
from .models import (
    BreadthState, DimensionFacts, MacroState, MarketRegime, MarketSnapshot,
    MarketState, MomentumState, ParticipationState, RegimeLabel,
    StructureState, TrendState, VolatilityState,
)
from .state import build_market_snapshot, build_market_state
from .facts import derive_facts
from .agent import MarketRegimeAgent, analyze_regime
from .report import format_regime


def build_market_regime_graph(*args, **kwargs):
    """Lazy graph import prevents package-level orchestration cycles."""
    from .graph import build_market_regime_graph as _build
    return _build(*args, **kwargs)


__all__ = [
    "MarketState",
    "MarketSnapshot",
    "MarketRegime",
    "RegimeLabel",
    "DimensionFacts",
    "TrendState",
    "MomentumState",
    "BreadthState",
    "VolatilityState",
    "ParticipationState",
    "MacroState",
    "StructureState",
    "build_market_state",
    "build_market_snapshot",
    "derive_facts",
    "MarketRegimeAgent",
    "analyze_regime",
    "build_market_regime_graph",
    "format_regime",
]
