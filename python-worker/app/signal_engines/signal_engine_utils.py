"""signal_engine_utils

Shared helpers for signal engines.

Why this module exists:
- Keep market-condition logic DRY (VIX/breadth/yield curve/NASDAQ trend + decay/chop risk)
- Avoid each engine re-implementing the same numeric hygiene (Decimal vs float) and
  "price injection" behavior.

Usage guideline:
- Engines should prefer calling these helpers instead of duplicating logic.
- Functions are intentionally small and composable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass(frozen=True)
class MarketConditionsMonitor:
    """A compact, UI-friendly view of market conditions.

    Notes:
    - `score` is a normalized 0..1 risk score (higher = worse conditions).
    - `status`/`color` are intended for dashboards (green/orange/red).
    - `drivers` should be short human-readable bullet points.
    """

    score: float
    status: str
    color: str
    drivers: List[str]
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "status": self.status,
            "color": self.color,
            "drivers": self.drivers,
            "metrics": self.metrics,
        }


class SignalEngineUtils:
    """Static helpers used across signal engines."""

    @staticmethod
    def to_float(value: Any) -> Optional[float]:
        """Best-effort conversion to float.

        This is mainly to normalize DB-returned numerics (e.g., Decimal) before
        performing arithmetic.
        """

        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def ensure_indicator_price(indicators: Optional[Dict[str, Any]], market_data: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """Ensure `indicators['price']` exists.

        Some indicator snapshots do not store a `price` field.
        For engines that do things like `atr / price`, we inject the latest close.

        Returns the (possibly mutated) indicators dict. If `indicators` is None,
        returns a new dict.
        """

        indicators = indicators or {}
        if indicators.get("price") is None:
            if market_data is not None and not market_data.empty and "close" in market_data.columns:
                indicators["price"] = float(market_data.iloc[-1]["close"])
        return indicators

    @staticmethod
    def compute_return(market_data: Optional[pd.DataFrame], *, days: int) -> Optional[float]:
        """Compute simple return over `days` using `close`.

        Returns:
        - Fractional return (e.g. 0.05 = +5%)
        - None if not computable
        """

        if market_data is None or market_data.empty:
            return None
        if "close" not in market_data.columns:
            return None

        closes = market_data["close"].astype(float).values
        if len(closes) <= days:
            return None

        start = float(closes[-(days + 1)])
        end = float(closes[-1])
        if start <= 0:
            return None
        return (end - start) / start

    @staticmethod
    def compute_market_conditions_monitor(
        *,
        market_context,
        market_data: Optional[pd.DataFrame] = None,
        indicators: Optional[Dict[str, Any]] = None,
    ) -> MarketConditionsMonitor:
        """Compute a standardized market-conditions monitor.

        What this tries to capture (high-level):
        - **Risk regime**: `market_context.regime`
        - **Volatility regime**: VIX
        - **Breadth / internal participation**: `% above 50d`
        - **Macro risk**: yield curve spread
        - **Trend backdrop**: NASDAQ trend
        - **Chop/decay proxies** (useful for leveraged instruments):
          - realized vol proxy (ATR% if available)
          - Bollinger squeeze proxy (`bb_width`)
          - low momentum combined with elevated VIX

        Output is designed to be displayed directly in UI as:
        - green/orange/red badge
        - short list of drivers
        """

        indicators = indicators or {}
        drivers: List[str] = []

        risk = 0.0  # 0..1 (higher is worse)

        # Base regime
        regime = getattr(market_context, "regime", None)
        if regime is not None:
            drivers.append(f"Regime: {regime.value if hasattr(regime, 'value') else str(regime)}")
            if getattr(regime, "value", str(regime)) == "NO_TRADE":
                risk += 0.9
            elif getattr(regime, "value", str(regime)) == "HIGH_VOL_CHOP":
                risk += 0.35
            elif getattr(regime, "value", str(regime)) == "BEAR":
                risk += 0.25

        # VIX
        vix = SignalEngineUtils.to_float(getattr(market_context, "vix", None))
        if vix is not None:
            if vix >= 40:
                risk += 0.55
                drivers.append(f"VIX very high ({vix:.1f})")
            elif vix >= 30:
                risk += 0.35
                drivers.append(f"VIX high ({vix:.1f})")
            elif vix >= 20:
                risk += 0.15
                drivers.append(f"VIX elevated ({vix:.1f})")
            elif vix < 15:
                risk -= 0.05
                drivers.append(f"VIX low ({vix:.1f})")

        # Breadth
        breadth = SignalEngineUtils.to_float(getattr(market_context, "breadth", None))
        if breadth is not None:
            if breadth < 0.2:
                risk += 0.5
                drivers.append(f"Breadth very weak ({breadth:.0%} above 50d)")
            elif breadth < 0.3:
                risk += 0.3
                drivers.append(f"Breadth weak ({breadth:.0%} above 50d)")
            elif breadth > 0.7:
                risk -= 0.05
                drivers.append(f"Breadth strong ({breadth:.0%} above 50d)")

        # Yield curve
        ycs = SignalEngineUtils.to_float(getattr(market_context, "yield_curve_spread", None))
        if ycs is not None:
            if ycs < -0.5:
                risk += 0.25
                drivers.append(f"Yield curve inverted ({ycs:.2f})")
            elif ycs < 0:
                risk += 0.15
                drivers.append(f"Yield curve slightly inverted ({ycs:.2f})")

        # NASDAQ trend
        nasdaq_trend = getattr(market_context, "nasdaq_trend", None)
        if nasdaq_trend == "bearish":
            risk += 0.15
            drivers.append("NASDAQ trend bearish")
        elif nasdaq_trend == "bullish":
            risk -= 0.05
            drivers.append("NASDAQ trend bullish")

        # ATR% (realized volatility proxy)
        atr = SignalEngineUtils.to_float(indicators.get("atr"))
        price = SignalEngineUtils.to_float(indicators.get("price"))
        atr_pct = None
        if atr is not None and price is not None and price > 0:
            atr_pct = float(atr) / float(price)
            if atr_pct >= 0.04:
                risk += 0.25
                drivers.append(f"Realized vol high (ATR%={atr_pct*100:.1f}%)")
            elif atr_pct >= 0.03:
                risk += 0.15
                drivers.append(f"Realized vol elevated (ATR%={atr_pct*100:.1f}%)")

        # BB width squeeze proxy
        bb_width = SignalEngineUtils.to_float(indicators.get("bb_width"))
        if bb_width is not None and bb_width < 0.008:
            risk += 0.15
            drivers.append("Bollinger squeeze (chop/whipsaw risk)")

        # Low momentum + elevated VIX (chop/decay)
        momentum_5d = SignalEngineUtils.compute_return(market_data, days=5)
        if momentum_5d is not None and vix is not None:
            if abs(momentum_5d) < 0.01 and vix >= 20:
                risk += 0.2
                drivers.append(f"Low momentum in elevated VIX (5d={momentum_5d*100:.1f}%)")

        # Clamp risk score
        risk = max(0.0, min(1.0, float(risk)))

        if risk <= 0.25:
            status, color = "GREEN", "green"
        elif risk <= 0.55:
            status, color = "ORANGE", "orange"
        else:
            status, color = "RED", "red"

        metrics = {
            "regime": getattr(regime, "value", str(regime)) if regime is not None else None,
            "vix": vix,
            "breadth": breadth,
            "yield_curve_spread": ycs,
            "nasdaq_trend": nasdaq_trend,
            "atr_pct": atr_pct,
            "bb_width": bb_width,
            "momentum_5d": momentum_5d,
        }

        return MarketConditionsMonitor(score=risk, status=status, color=color, drivers=drivers, metrics=metrics)
