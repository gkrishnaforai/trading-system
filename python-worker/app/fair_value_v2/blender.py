from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.fair_value_v2.schemas import MethodResult


@dataclass(frozen=True)
class BlendResult:
    fair_value: Optional[float]
    scenario_fair_values: Dict[str, Optional[float]]


# Scenario probability weights — the headline `expected_fair_value` is
# the probability-weighted blend, not just the base case (Damodar-style
# scenario EV). Weights are deliberately static per run; calibration
# against realized returns can adjust them later via env override.
SCENARIO_PROBS: Dict[str, float] = json.loads(
    os.getenv("FV_SCENARIO_PROBS",
              '{"bear": 0.25, "base": 0.50, "bull": 0.20, "explosive": 0.05}'))
SCENARIO_ORDER = ("bear", "base", "bull", "explosive")


def expected_fair_value(scen: Dict[str, Any]) -> Optional[float]:
    """Σ p·FV over the scenarios that resolved — weights renormalize."""
    num = den = 0.0
    for k, p in SCENARIO_PROBS.items():
        v = scen.get(k)
        if v is None:
            continue
        num += p * float(v)
        den += p
    return num / den if den else None


def enforce_scenario_order(
        scen: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """bear ≤ base ≤ bull ≤ explosive — clamp violations and flag them.
    The per-method unclamped values stay in method_results for audit."""
    out = dict(scen or {})
    flags: List[str] = []
    prev_k = None
    for k in SCENARIO_ORDER:
        v = out.get(k)
        if v is None:
            continue
        if prev_k is not None and float(v) < float(out[prev_k]):
            flags.append(f"ordering_violation:{k}<{prev_k}")
            out[k] = float(out[prev_k])
            v = out[k]
        prev_k = k
    return out, flags


class WeightedBlender:
    def __init__(self, max_family_share: float = 0.55) -> None:
        # correlated methods of one family (pe_*, peg_*, ev_*, dcf_*)
        # may not exceed this share of total blend weight — a family
        # cluster echoing the same assumption can't dominate the answer
        self._max_family_share = max_family_share

    @staticmethod
    def _family(method_key: Optional[str]) -> str:
        return (method_key or "").split("_")[0] or "unknown"

    def cap_family_weights(
        self, pairs: List[Tuple[MethodResult, float]]) -> None:
        fam_w: Dict[str, float] = {}
        total = 0.0
        for mr, w in pairs:
            fam = self._family(getattr(mr, "method_key", None))
            fam_w[fam] = fam_w.get(fam, 0.0) + w
            total += w
        if total <= 0 or len(fam_w) <= 1:
            return
        for i, (mr, w) in enumerate(pairs):
            fam = self._family(getattr(mr, "method_key", None))
            fw = fam_w[fam]
            cap = self._max_family_share * total
            if fw > cap:
                pairs[i] = (mr, w * cap / fw)

    def blend(self, method_results: List[Tuple[MethodResult, float]]) -> BlendResult:
        total_w = 0.0
        base_sum = 0.0
        eligible: List[Tuple[MethodResult, float, float, Dict[str, Optional[float]]]] = []
        scenario_keys: set[str] = set()

        working: List[Tuple[MethodResult, float]] = []
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
            working.append((mr, weight))
        self.cap_family_weights(working)

        for mr, weight in working:
            try:
                fv = float(mr.fair_price)
            except Exception:
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
