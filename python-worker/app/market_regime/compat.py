"""Temporary compatibility adapter for legacy synchronous consumers.

This module does not implement market-regime logic. It delegates to the
canonical app.market_regime graph and only maps the result into the legacy
signal-engine context shape while those consumers are migrated.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from enum import Enum
from typing import Any, Dict

from app.signal_engines.base import MarketContext, MarketRegime as SignalMarketRegime

from .agent import analyze_regime
from .facts import derive_facts
from .state import build_market_snapshot
from app.market_data import MarketDataService


class LegacyMarketRegime(str, Enum):
    """Temporary names-only compatibility enum; no detection logic."""
    STRONG_BULL = "strong_bull"
    MILD_BULL = "mild_bull"
    SIDEWAYS = "sideways"
    MILD_BEAR = "mild_bear"
    STRONG_BEAR = "strong_bear"


@dataclass
class CanonicalRegimeData:
    regime: LegacyMarketRegime
    confidence: float
    updated_at: datetime
    canonical_label: str
    permissions: Dict[str, Any]


def _legacy_regime(direction: str, condition: str) -> LegacyMarketRegime:
    if direction == "bearish":
        return LegacyMarketRegime.MILD_BEAR
    if condition in {"risk_off", "distribution"}:
        return LegacyMarketRegime.SIDEWAYS
    if direction == "bullish":
        return LegacyMarketRegime.MILD_BULL
    return LegacyMarketRegime.SIDEWAYS


def _signal_context_regime(direction: str, condition: str) -> SignalMarketRegime:
    if direction == "bearish":
        return SignalMarketRegime.BEAR
    if condition in {"risk_off", "distribution"}:
        return SignalMarketRegime.HIGH_VOL_CHOP
    if direction == "bullish":
        return SignalMarketRegime.BULL
    return SignalMarketRegime.NO_TRADE


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "Synchronous market-regime compatibility adapter cannot run inside "
        "an active event loop; use build_market_regime_graph directly.")


class CanonicalMarketRegimeService:
    """Legacy-shaped facade backed by the canonical regime implementation."""

    def __init__(self, service: MarketDataService | None = None):
        self.service = service or MarketDataService()

    def detect_market_regime(self) -> CanonicalRegimeData:
        snapshot = _run(build_market_snapshot(self.service))
        facts = derive_facts(snapshot)
        regime = analyze_regime(snapshot, facts, use_llm=False)
        permissions = regime.market_permissions.model_dump() if regime.market_permissions else {}
        return CanonicalRegimeData(
            regime=_legacy_regime(regime.direction, regime.condition),
            confidence=regime.confidence,
            updated_at=regime.snapshot.as_of if regime.snapshot and regime.snapshot.as_of else datetime.utcnow(),
            canonical_label=regime.regime.value,
            permissions=permissions,
        )


def get_legacy_market_context() -> MarketContext:
    """Build the old context shape from canonical regime facts."""
    snapshot = _run(build_market_snapshot(MarketDataService()))
    facts = derive_facts(snapshot)
    regime = analyze_regime(snapshot, facts, use_llm=False)
    return MarketContext(
        regime=_signal_context_regime(regime.direction, regime.condition),
        regime_confidence=regime.confidence,
        vix=snapshot.volatility.vix or 20.0,
        nasdaq_trend="bullish" if snapshot.structure.qqq_above_sma50 else "neutral",
        sector_rotation={},
        breadth=(snapshot.breadth.pct_above_sma50 or 0.0) / 100.0,
        yield_curve_spread=0.0,
        timestamp=datetime.utcnow(),
    )
