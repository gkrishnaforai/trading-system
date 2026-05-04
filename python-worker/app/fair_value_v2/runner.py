from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.fair_value_v2.blender import WeightedBlender
from app.fair_value_v2.dsl.evaluator import DslError, evaluate_scenarios
from app.fair_value_v2.feature_resolver import FeatureResolver
from app.fair_value_v2.feature_store.postgres_point_in_time import PostgresPointInTimeFeatureStore
from app.fair_value_v2.methods.registry import MethodRegistry
from app.fair_value_v2.regime_router import RegimeRouter
from app.fair_value_v2.router import CategoryRouter
from app.fair_value_v2.schemas import FairValueV2Result, FeatureRow, MethodResult


@dataclass(frozen=True)
class RunContext:
    symbol: str
    as_of_ts: datetime
    category: Optional[str]


class FairValueRunner:
    def __init__(self):
        base_dir = os.path.dirname(__file__)
        definitions_dir = os.path.join(base_dir, "methods", "definitions")
        methods_dir = os.path.join(base_dir, "methods")
        self.registry = MethodRegistry.load_from_dir(definitions_dir)
        self.feature_store = PostgresPointInTimeFeatureStore()
        self.feature_resolver = FeatureResolver(
            feature_store=self.feature_store,
            features_yaml_path=os.path.join(methods_dir, "features.yaml"),
        )
        self.router = CategoryRouter(
            category_router_path=os.path.join(methods_dir, "category_router.yaml"),
            category_methods_path=os.path.join(methods_dir, "category_methods.yaml"),
        )
        self.regime_router = RegimeRouter(
            regime_router_path=os.path.join(methods_dir, "regime_router.yaml"),
            regime_methods_path=os.path.join(methods_dir, "regime_methods.yaml"),
        )
        self.blender = WeightedBlender()

        # Scalars used only for regime selection. Keep this list small and stable.
        self._regime_selection_scalars = [
            "eps_ttm",
            "eps_forward",
            "market_cap",
            "revenue_growth_ttm",
            "forward_growth_pct_1y",
            "operating_margin_ttm",
        ]

    def _required_scalar_issues(
        self,
        required_scalars: List[str],
        features: FeatureRow,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        missing: List[Dict[str, Any]] = []
        non_canonical: List[Dict[str, Any]] = []

        scalars = features.scalars or {}
        sources = features.sources or {}
        quality = features.quality or {}

        for name in required_scalars:
            v = scalars.get(name)
            if v is None:
                missing.append(
                    {
                        "feature": name,
                        "reason": "missing_required_feature",
                        "details": {"quality": {k: vv for k, vv in quality.items() if k.startswith(f"{name}.")}},
                    }
                )
                continue

            src = sources.get(name)
            if src and str(src).startswith("derived:"):
                non_canonical.append(
                    {
                        "feature": name,
                        "reason": "non_canonical_source",
                        "source": src,
                        "details": {"quality": {k: vv for k, vv in quality.items() if k.startswith(f"{name}.")}},
                    }
                )
                continue

            # Coalesce is treated as fallback in strict mode if a selection happened.
            # FeatureResolver stores coalesce debugging under the feature's quality namespace.
            selected = quality.get(f"{name}.selected")
            if selected is not None and selected != 0:
                non_canonical.append(
                    {
                        "feature": name,
                        "reason": "coalesce_fallback_selected",
                        "selected_index": selected,
                        "source": src,
                        "details": {"quality": {k: vv for k, vv in quality.items() if k.startswith(f"{name}.")}},
                    }
                )

        return missing, non_canonical

    def _hash_features(self, features: FeatureRow) -> str:
        payload = {
            "symbol": features.symbol,
            "as_of_ts": features.as_of_ts.isoformat(),
            "scalars": features.scalars,
            "sources": features.sources,
            "quality": features.quality,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _get_features_for_requires(self, symbol: str, as_of_ts: datetime, required_scalars: Any) -> FeatureRow:
        scalars, sources, quality = self.feature_resolver.resolve_scalars(symbol, as_of_ts, required_scalars)
        return FeatureRow(
            symbol=symbol,
            as_of_ts=as_of_ts,
            scalars=scalars,
            series={},
            sources=sources,
            quality=quality,
        )

    def _run_method(self, method_key: str, symbol: str, as_of_ts: datetime) -> Tuple[MethodResult, str]:
        definition = self.registry.get(method_key)
        required_scalars = (definition.requires or {}).get("scalars") or []
        optional_scalars = (definition.requires or {}).get("optional_scalars") or []
        all_scalars = list(dict.fromkeys(list(required_scalars) + list(optional_scalars)))
        features = self._get_features_for_requires(symbol, as_of_ts, all_scalars)
        features_hash = self._hash_features(features)
        try:
            (features.quality or {}).update({"features_hash": features_hash})
        except Exception:
            pass

        inputs_used = {k: features.scalars.get(k) for k in (definition.requires.get("scalars") or [])}
        for k in optional_scalars:
            inputs_used[f"optional.{k}"] = features.scalars.get(k)
        params = dict(definition.params or {})

        strict = os.getenv("FAIR_VALUE_V2_STRICT", "0").strip().lower() in {"1", "true", "yes", "y", "on"}
        missing, non_canonical = self._required_scalar_issues(required_scalars=list(required_scalars), features=features)
        non_canonical_issues = non_canonical if strict else []
        if missing or non_canonical_issues:
            reason_details: Dict[str, Any] = {
                "symbol": symbol,
                "as_of_ts": as_of_ts.isoformat(),
                "missing_required_features": missing,
                "non_canonical_features": non_canonical_issues,
                "features": {
                    "scalars": features.scalars,
                    "sources": features.sources,
                    "quality": features.quality,
                },
            }
            mr = MethodResult(
                method_key=definition.method_key,
                version=definition.version,
                enabled=True,
                status="missing_data",
                fair_price=None,
                inputs_used={**inputs_used, **{f"param.{k}": v for k, v in params.items()}},
                metrics={},
                reason_code="strict_missing_or_fallback" if strict else "missing_required_features",
                reason_details=reason_details,
            )
            return mr, features_hash

        debug = os.getenv("FAIR_VALUE_V2_DEBUG", "0").strip().lower() in {"1", "true", "yes", "y", "on"}
        try:
            scenarios, metrics = evaluate_scenarios(
                definition.formula,
                scalars=features.scalars,
                params=params,
                debug=debug,
            )
            base_fair_price = scenarios.get("base")
            status = "ok" if base_fair_price and base_fair_price > 0 else "missing_data"
            mr = MethodResult(
                method_key=definition.method_key,
                version=definition.version,
                enabled=True,
                status=status,
                fair_price=base_fair_price,
                inputs_used={**inputs_used, **{f"param.{k}": v for k, v in params.items()}},
                metrics={**(metrics or {}), "scenario_fair_values": scenarios},
            )
        except DslError as e:
            missing_codes = {"missing_data", "missing", "invalid_number", "invalid_ast"}
            status = "missing_data" if e.code in missing_codes else "invalid_assumption"
            mr = MethodResult(
                method_key=definition.method_key,
                version=definition.version,
                enabled=True,
                status=status,
                fair_price=None,
                inputs_used={**inputs_used, **{f"param.{k}": v for k, v in params.items()}},
                metrics={},
                reason_code=e.code,
                reason_details={
                    **(e.details or {}),
                    "symbol": symbol,
                    "as_of_ts": as_of_ts.isoformat(),
                    "features": {
                        "scalars": features.scalars,
                        "sources": features.sources,
                        "quality": features.quality,
                    },
                },
            )
        except Exception as e:
            mr = MethodResult(
                method_key=definition.method_key,
                version=definition.version,
                enabled=True,
                status="error",
                fair_price=None,
                inputs_used={**inputs_used, **{f"param.{k}": v for k, v in params.items()}},
                metrics={},
                reason_code="error",
                reason_details={
                    "error": str(e),
                    "symbol": symbol,
                    "as_of_ts": as_of_ts.isoformat(),
                },
            )

        return mr, features_hash

    def run(self, symbol: str, as_of_ts: Optional[datetime] = None) -> FairValueV2Result:
        ts = as_of_ts or datetime.now(timezone.utc)
        run_id = str(uuid.uuid4())

        warnings: List[Dict[str, Any]] = []

        sector, industry = self.feature_store.get_company_classification(symbol)
        company_name, description = self.feature_store.get_company_profile_text(symbol)

        override_category, override_reason = self.feature_store.get_category_override(symbol)
        if override_category:
            category = str(override_category)
            method_weights = self.router.methods_for_category(category)
            warnings.append(
                {
                    "level": "info",
                    "scope": "routing",
                    "reason": "category_override_applied",
                    "details": {
                        "symbol": symbol,
                        "category": category,
                        "reason": override_reason,
                    },
                }
            )
        else:
            category, method_weights = self.router.route(symbol, sector, industry, company_name=company_name, description=description)

        # Determine regime using a small, explicit scalar set.
        regime_features = self._get_features_for_requires(symbol, ts, self._regime_selection_scalars)
        regime, regime_method_weights = self.regime_router.route(
            category=category,
            sector=sector,
            industry=industry,
            scalars=regime_features.scalars or {},
        )

        # Use regime-selected methods when present; otherwise, keep category methods.
        selected_method_weights = regime_method_weights or method_weights

        method_results: List[MethodResult] = []
        blend_inputs: List[Tuple[MethodResult, float]] = []
        features_hashes: List[str] = []
        for mw in selected_method_weights:
            mr, fh = self._run_method(mw.method_key, symbol, ts)
            method_results.append(mr)
            features_hashes.append(fh)
            blend_inputs.append((mr, mw.weight))

            if mr.status != "ok":
                warnings.append(
                    {
                        "level": "warning",
                        "scope": "method",
                        "method_key": mr.method_key,
                        "status": mr.status,
                        "reason_code": mr.reason_code,
                        "reason_details": mr.reason_details,
                    }
                )

        blend = self.blender.blend(blend_inputs)
        combined_hash = hashlib.sha256("|".join(sorted(set(features_hashes))).encode("utf-8")).hexdigest() if features_hashes else None

        # Strict-only policy: if nothing succeeded, do not emit a fair value.
        any_ok = any((mr.status == "ok" and mr.fair_price is not None) for mr in method_results)
        if not any_ok:
            warnings.append(
                {
                    "level": "warning",
                    "scope": "run",
                    "reason": "no_fair_value_computed",
                    "details": {
                        "symbol": symbol,
                        "as_of_ts": ts.isoformat(),
                        "category": category,
                    },
                }
            )

        return FairValueV2Result(
            run_id=run_id,
            symbol=symbol,
            as_of_ts=ts,
            fair_value=blend.fair_value if any_ok else None,
            scenario_fair_values=blend.scenario_fair_values if any_ok else {},
            regime=f"{category}:{regime}",
            method_results=method_results,
            features_hash=combined_hash,
            warnings=warnings,
        )
