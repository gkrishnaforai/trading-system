"""Sector configuration loader + business-model classification.

The engine is sector-agnostic — healthcare knowledge lives entirely
in sectors/healthcare.yaml. Adding a sector = a new yaml file.

Classification is deterministic keyword matching on the company's
industry/profile text via the model's `industry_hints`. Unmatched
names get 'unclassified' — a real bucket with its own KPI list, not
a forced fit.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

_SECTORS_DIR = Path(__file__).parent / "sectors"


@lru_cache(maxsize=8)
def load(sector: str = "healthcare") -> dict[str, Any]:
    p = _SECTORS_DIR / f"{sector}.yaml"
    spec = yaml.safe_load(p.read_text())
    spec["_version"] = spec.get("version", 0)
    return spec


def classify_model(sym: str, sector: str = "healthcare",
                   row: Optional[dict] = None) -> str:
    """Industry-keyword match → business model. The model gates the
    KPI framework and weight overrides — a drug developer is never
    scored on device economics. `row` (industry/sector/company_name)
    is injectable for tests and callers that already have it."""
    cfg = load(sector)
    if row is None:
        from app.database import db
        try:
            rows = db.execute_query(
                "SELECT industry, sector, company_name FROM stocks"
                " WHERE symbol=:s", {"s": sym.upper()})
        except Exception as exc:
            logger.debug("classify_model %s: %s", sym, exc)
            return "unclassified"
        if not rows:
            return "unclassified"
        row = rows[0]
    r = row
    hay = " ".join(str(r.get(k) or "") for k in
                   ("industry", "sector", "company_name")).lower()
    for model, m in (cfg.get("business_models") or {}).items():
        if any(h in hay for h in (m.get("industry_hints") or [])):
            return model
    return "unclassified"


def model_cfg(model: str, sector: str = "healthcare") -> dict:
    cfg = load(sector)
    return cfg.get("business_models", {}).get(
        model, cfg.get("unclassified", {}))
