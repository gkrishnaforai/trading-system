from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


@dataclass(frozen=True)
class MethodWeight:
    method_key: str
    weight: float


class RegimeRouter:
    def __init__(self, regime_router_path: str, regime_methods_path: str):
        self._router_cfg = yaml.safe_load(Path(regime_router_path).read_text())
        self._methods_cfg = yaml.safe_load(Path(regime_methods_path).read_text())

    def _contains(self, text: str, needle: str) -> bool:
        return needle.lower() in (text or "").lower()

    def _eval_term(self, ctx: Dict[str, Any], term: Dict[str, Any]) -> bool:
        field = term.get("field")
        if not field:
            return False

        if "contains" in term:
            needle = term.get("contains")
            return self._contains(str(ctx.get(field) or ""), str(needle or ""))

        v = ctx.get(field)
        if "eq" in term:
            return str(v) == str(term.get("eq"))
        if "lte" in term:
            try:
                return float(v) <= float(term.get("lte"))
            except Exception:
                return False
        if "gte" in term:
            try:
                return float(v) >= float(term.get("gte"))
            except Exception:
                return False

        return False

    def regime_for(
        self,
        *,
        category: Optional[str],
        sector: Optional[str],
        industry: Optional[str],
        scalars: Dict[str, Any],
    ) -> str:
        ctx: Dict[str, Any] = {
            "category": category or "",
            "sector": sector or "",
            "industry": industry or "",
            "always": "true",
            **(scalars or {}),
        }

        rules = (self._router_cfg or {}).get("rules") or []
        default_regime = (self._router_cfg or {}).get("default_regime") or "standard"

        for rule in rules:
            name = rule.get("name")
            when = rule.get("when") or {}
            any_terms = when.get("any") or []
            all_terms = when.get("all") or []

            any_ok = True
            if any_terms:
                any_ok = any(self._eval_term(ctx, t) for t in any_terms)
            all_ok = True
            if all_terms:
                all_ok = all(self._eval_term(ctx, t) for t in all_terms)

            if name and any_ok and all_ok:
                return str(name)

        return str(default_regime)

    def methods_for(self, *, category: str, regime: str) -> List[MethodWeight]:
        selections = (self._methods_cfg or {}).get("selections") or {}
        default_category = (self._methods_cfg or {}).get("default_category") or "value"
        default_regime = (self._methods_cfg or {}).get("default_regime") or "standard"
        fallback_chain = (self._methods_cfg or {}).get("fallback_chain") or []

        def _get(c: str, r: str) -> Optional[List[Dict[str, Any]]]:
            c_cfg = selections.get(c) or {}
            r_cfg = c_cfg.get(r) or {}
            return r_cfg.get("methods")

        methods = _get(category, regime)
        if not methods:
            for item in fallback_chain:
                c = str(item.get("category") or "")
                r = str(item.get("regime") or "")
                c = c.replace("{category}", category).replace("{default_category}", default_category)
                r = r.replace("{regime}", regime).replace("{default_regime}", default_regime)
                methods = _get(c, r)
                if methods:
                    break

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
        *,
        category: str,
        sector: Optional[str],
        industry: Optional[str],
        scalars: Dict[str, Any],
    ) -> Tuple[str, List[MethodWeight]]:
        regime = self.regime_for(category=category, sector=sector, industry=industry, scalars=scalars)
        return regime, self.methods_for(category=category, regime=regime)
