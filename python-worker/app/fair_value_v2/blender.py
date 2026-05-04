from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.fair_value_v2.schemas import MethodResult


@dataclass(frozen=True)
class BlendResult:
    fair_value: Optional[float]
    scenario_fair_values: Dict[str, Optional[float]]


class WeightedBlender:
    def blend(self, method_results: List[Tuple[MethodResult, float]]) -> BlendResult:
        total_w = 0.0
        base_sum = 0.0
        eligible: List[Tuple[MethodResult, float, float, Dict[str, Optional[float]]]] = []
        scenario_keys: set[str] = set()

        for mr, w in method_results:
            if not mr or not mr.enabled:
                continue
            if mr.status != "ok":
                continue
            if mr.fair_price is None:
                continue
            try:
                fv = float(mr.fair_price)
            except Exception:
                continue
            if fv <= 0:
                continue

            try:
                weight = float(w)
            except Exception:
                weight = 0.0
            if weight <= 0:
                continue

            total_w += weight
            base_sum += fv * weight

            scen = (mr.metrics or {}).get("scenario_fair_values") or {}
            scen_clean: Dict[str, Optional[float]] = {}
            for k, v in (scen or {}).items():
                if v is None:
                    scen_clean[str(k)] = None
                    continue
                try:
                    sv = float(v)
                except Exception:
                    scen_clean[str(k)] = None
                    continue
                scen_clean[str(k)] = sv
                scenario_keys.add(str(k))

            eligible.append((mr, weight, fv, scen_clean))

        fair_value = (base_sum / total_w) if total_w > 0 else None
        scenario_out: Dict[str, Optional[float]] = {}
        for k in sorted(scenario_keys):
            s_sum = 0.0
            s_w = 0.0
            for _mr, weight, _fv, scen in eligible:
                sv = scen.get(k)
                if sv is None:
                    continue
                s_sum += sv * weight
                s_w += weight
            scenario_out[k] = (s_sum / s_w) if s_w > 0 else None

        return BlendResult(fair_value=fair_value, scenario_fair_values=scenario_out)
