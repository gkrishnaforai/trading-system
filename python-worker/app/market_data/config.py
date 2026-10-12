"""
Routing configuration: which providers to try, in what order, per capability.

Default order comes from existing settings (primary_data_provider /
fallback_data_provider). Per-capability overrides can be supplied via the
MARKET_DATA_ROUTES env var as JSON, e.g.:

    MARKET_DATA_ROUTES='{
      "ohlcv":  {"providers": ["fmp", "yahoo", "polygon"], "fallback_on_empty": true},
      "quote":  {"providers": ["polygon", "fmp"],          "fallback_on_empty": false}
    }'

Provider name aliases: "yahoo" -> "yahoo_finance", "polygon" -> "massive".
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List

from app.config import settings
from app.observability.logging import get_logger

from .base import CAPABILITIES

logger = get_logger("market_data_config")

_ALIASES = {
    "yahoo": "yahoo_finance",
    "yf": "yahoo_finance",
    "polygon": "massive",
    "polygon_io": "massive",
}

_KNOWN_PROVIDERS = ("fmp", "yahoo_finance", "massive")


@dataclass
class RouteConfig:
    """Routing rule for one capability."""

    providers: List[str] = field(default_factory=list)
    fallback_on_empty: bool = True


def _normalize_name(name: str) -> str:
    name = (name or "").strip().lower()
    return _ALIASES.get(name, name)


def _default_order() -> List[str]:
    """Primary first, configured fallback second, then everything else."""
    order: List[str] = []
    for raw in (
        getattr(settings, "primary_data_provider", None),
        getattr(settings, "fallback_data_provider", None),
        *_KNOWN_PROVIDERS,
    ):
        name = _normalize_name(raw or "")
        if name and name in _KNOWN_PROVIDERS and name not in order:
            order.append(name)
    return order


def default_routes() -> Dict[str, RouteConfig]:
    order = _default_order()
    routes = {cap: RouteConfig(providers=list(order)) for cap in CAPABILITIES}

    # Capabilities only FMP offers in this codebase — no fallback possible.
    for cap in ("analyst_grades", "price_target"):
        routes[cap] = RouteConfig(
            providers=[p for p in order if p == "fmp"] or ["fmp"],
            fallback_on_empty=False,
        )
    return routes


def load_routes() -> Dict[str, RouteConfig]:
    """Default routes + MARKET_DATA_ROUTES env override."""
    routes = default_routes()
    raw = (os.getenv("MARKET_DATA_ROUTES") or "").strip()
    if not raw:
        return routes

    try:
        overrides = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"MARKET_DATA_ROUTES is not valid JSON, ignoring: {e}")
        return routes

    if not isinstance(overrides, dict):
        logger.warning("MARKET_DATA_ROUTES must be a JSON object, ignoring")
        return routes

    for cap, cfg in overrides.items():
        cap = str(cap).strip()
        if cap not in CAPABILITIES:
            logger.warning(f"MARKET_DATA_ROUTES: unknown capability '{cap}', skipping")
            continue
        if not isinstance(cfg, dict):
            continue
        providers = [
            n for n in (_normalize_name(p) for p in cfg.get("providers", []))
            if n in _KNOWN_PROVIDERS
        ]
        routes[cap] = RouteConfig(
            providers=providers or routes[cap].providers,
            fallback_on_empty=bool(
                cfg.get("fallback_on_empty", routes[cap].fallback_on_empty)
            ),
        )
    return routes
