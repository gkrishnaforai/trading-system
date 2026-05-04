from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


@dataclass(frozen=True)
class MethodWeight:
    method_key: str
    weight: float


class CategoryRouter:
    def __init__(self, category_router_path: str, category_methods_path: str):
        self._router_cfg = yaml.safe_load(Path(category_router_path).read_text())
        self._methods_cfg = yaml.safe_load(Path(category_methods_path).read_text())

    def _contains(self, text: str, needle: str) -> bool:
        return needle.lower() in (text or "").lower()

    def category_for(
        self,
        symbol: Optional[str],
        sector: Optional[str],
        industry: Optional[str],
        company_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> str:
        ctx = {
            "symbol": symbol or "",
            "sector": sector or "",
            "industry": industry or "",
            "company_name": company_name or "",
            "description": description or "",
        }
        rules = (self._router_cfg or {}).get("rules") or []
        default_category = (self._router_cfg or {}).get("default_category") or "value"

        for rule in rules:
            category = rule.get("category")
            when = rule.get("when") or {}
            any_terms = when.get("any") or []
            all_terms = when.get("all") or []

            def _match_term(t: Dict[str, Any]) -> bool:
                if not isinstance(t, dict):
                    return False

                if "any" in t:
                    group_terms = t.get("any") or []
                    return any(_match_term(gt) for gt in group_terms)
                if "all" in t:
                    group_terms = t.get("all") or []
                    return all(_match_term(gt) for gt in group_terms)

                field = t.get("field")
                needle = t.get("contains")
                if not field or needle is None:
                    return False
                return self._contains(str(ctx.get(field) or ""), str(needle))

            any_ok = True
            if any_terms:
                any_ok = any(_match_term(t) for t in any_terms)
            all_ok = True
            if all_terms:
                all_ok = all(_match_term(t) for t in all_terms)

            if category and any_ok and all_ok:
                return str(category)

        return str(default_category)

    def methods_for_category(self, category: str) -> List[MethodWeight]:
        categories = (self._methods_cfg or {}).get("categories") or {}
        default_methods = (self._methods_cfg or {}).get("default_methods") or []

        cat_cfg = categories.get(category) or {}
        methods = cat_cfg.get("methods")
        if not methods:
            methods = default_methods

        out: List[MethodWeight] = []
        for m in methods or []:
            method_key = m.get("method_key")
            weight = m.get("weight")
            if not method_key:
                continue
            try:
                w = float(weight) if weight is not None else 1.0
            except Exception:
                w = 1.0
            out.append(MethodWeight(method_key=str(method_key), weight=w))

        return out

    def route(
        self,
        symbol: Optional[str],
        sector: Optional[str],
        industry: Optional[str],
        company_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Tuple[str, List[MethodWeight]]:
        category = self.category_for(symbol, sector, industry, company_name=company_name, description=description)
        return category, self.methods_for_category(category)
