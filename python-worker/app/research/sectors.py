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
    is injectable for tests and callers that already have it.
    A curated `symbol_map` entry wins over keyword matching — the
    module is too structural to leave to industry text."""
    cfg = load(sector)
    mapped = (cfg.get("symbol_map") or {}).get(sym.upper())
    if mapped:
        return mapped
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


def _all_sector_files() -> list[str]:
    return [p.stem for p in _SECTORS_DIR.glob("*.yaml")]


def universe(sector: str = "healthcare") -> list[str]:
    """The symbol set a sector researches. `symbols:` in yaml is
    explicit; `sector_match:` resolves via stocks.sector LIKE.
    Fail-closed to [] on DB errors."""
    cfg = load(sector)
    u = cfg.get("universe") or {}
    if u.get("symbols"):
        return sorted({str(s).upper() for s in u["symbols"]})
    match = str(u.get("sector_match") or sector)
    from app.database import db
    try:
        return sorted(r["symbol"] for r in db.execute_query(
            "SELECT symbol FROM stocks"
            " WHERE LOWER(COALESCE(sector,'')) LIKE :p",
            {"p": f"%{match.lower()}%"}))
    except Exception as exc:
        logger.debug("universe %s: %s", sector, exc)
        return []


def all_universes() -> dict[str, list[str]]:
    """Every configured sector → its symbol list."""
    return {s: universe(s) for s in _all_sector_files()}


def sector_for_symbol(sym: str, row: Optional[dict] = None) -> str:
    """Route a symbol to its sector module. Explicit yaml `symbols:`
    membership wins; otherwise stocks.sector text vs each yaml's
    sector_match. Default 'healthcare' preserves prior callers."""
    sym = sym.upper()
    explicit = []
    matched = []
    for s in _all_sector_files():
        cfg = load(s)
        u = cfg.get("universe") or {}
        if u.get("symbols"):
            if sym in {str(x).upper() for x in u["symbols"]}:
                explicit.append(s)
        else:
            matched.append((s, u.get("sector_match") or s))
    if explicit:
        return explicit[0]
    if matched:
        if row is None:
            from app.database import db
            try:
                rows = db.execute_query(
                    "SELECT sector FROM stocks WHERE symbol=:s",
                    {"s": sym})
                row = rows[0] if rows else {}
            except Exception:
                row = {}
        sec = str((row or {}).get("sector") or "").lower()
        for s, m in matched:
            if m and str(m).lower() in sec:
                return s
    return "healthcare"
