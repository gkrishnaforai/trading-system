from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ScreenerConfig:
    id: str
    label: str
    weights: Dict[str, float]
    thresholds: Optional[Dict[str, Any]] = None
    universe_filters: Optional[Dict[str, Any]] = None


SCREENER_CONFIGS: List[ScreenerConfig] = [
    ScreenerConfig(
        id="2x_6_12m",
        label="2× in 6–12 Months",
        weights={"investment": 0.35, "entry": 0.45, "catalyst": 0.20},
    ),
    ScreenerConfig(
        id="compounders_2030",
        label="2030 Compounders",
        weights={"investment": 0.70, "entry": 0.10, "catalyst": 0.20},
    ),
    ScreenerConfig(
        id="spec_10x",
        label="10× Speculative",
        weights={"investment": 0.40, "entry": 0.25, "catalyst": 0.35},
    ),
    ScreenerConfig(
        id="buffett_ai",
        label="Buffett AI",
        weights={"investment": 0.85, "entry": 0.05, "catalyst": 0.10},
    ),
    ScreenerConfig(
        id="underappreciated_ai",
        label="Underappreciated AI",
        weights={"investment": 0.45, "entry": 0.25, "catalyst": 0.30},
    ),
]


def list_screener_configs() -> List[Dict[str, Any]]:
    return [
        {
            "id": c.id,
            "label": c.label,
            "weights": dict(c.weights),
            "thresholds": dict(c.thresholds) if c.thresholds else None,
            "universe_filters": dict(c.universe_filters) if c.universe_filters else None,
        }
        for c in SCREENER_CONFIGS
    ]
