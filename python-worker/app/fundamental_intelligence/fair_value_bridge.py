"""Bridge from the fair-value engines into fundamental diagnostics.

Mirrors the effective fair value returned by /fair-value: when v2 is enabled
and produces a value, its blended value and scenario band win; otherwise the
v1 engine's blended value and DCF scenario band are used. Returns None when
neither engine has enough data — callers must treat absence honestly.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "on"}
ENABLE_FAIR_VALUE_V2 = os.getenv("ENABLE_FAIR_VALUE_V2", "false").strip().lower() in _TRUE_VALUES


def _v1_band(symbol: str) -> Optional[Dict[str, Any]]:
    try:
        from app.services.fair_value_service import FairValueService
        result = FairValueService().calculate_fair_value(symbol)
    except Exception as exc:
        logger.warning("v1 fair-value band unavailable for %s: %s", symbol, exc)
        return None
    if not result or not getattr(result, "fair_value", None):
        return None
    band: Dict[str, Any] = {
        "fair_value_base": float(result.fair_value),
        "source": "fair_value_engine_v1",
    }
    scenarios = (
        ((result.valuation_metrics or {}).get("dcf_simple") or {}).get("scenarios") or {}
    )
    bear = (scenarios.get("bear") or {}).get("fair_price")
    bull = (scenarios.get("bull") or {}).get("fair_price")
    if bear and float(bear) > 0:
        band["fair_value_bear"] = float(bear)
    if bull and float(bull) > 0:
        band["fair_value_bull"] = float(bull)
    return band


def _v2_band(symbol: str) -> Optional[Dict[str, Any]]:
    try:
        from app.fair_value_v2.resolver import FairValueV2Resolver
        v2, run_meta = FairValueV2Resolver().resolve(symbol)
    except Exception as exc:
        logger.warning("v2 fair-value band unavailable for %s: %s", symbol, exc)
        return None
    if not getattr(v2, "fair_value", None) or float(v2.fair_value) <= 0:
        return None
    band: Dict[str, Any] = {
        "fair_value_base": float(v2.fair_value),
        "source": run_meta.get("source") or getattr(v2, "model_version", None) or "fair_value_v2",
    }
    scenarios = getattr(v2, "scenario_fair_values", None) or {}
    for key, name in (("bear", "fair_value_bear"), ("bull", "fair_value_bull")):
        val = scenarios.get(key)
        if val and float(val) > 0:
            band[name] = float(val)
    regime = getattr(v2, "regime", None)
    if regime:
        band["v2_regime"] = regime
    if run_meta:
        band["run_reused"] = bool(run_meta.get("reused"))
        band["run_as_of"] = run_meta.get("run_as_of")
    return band


def resolve_fair_value_band(symbol: str) -> Optional[Dict[str, Any]]:
    """Effective fair value plus scenario band, matching the /fair-value response."""
    symbol = symbol.upper()
    if ENABLE_FAIR_VALUE_V2:
        band = _v2_band(symbol)
        if band:
            return band
    return _v1_band(symbol)
