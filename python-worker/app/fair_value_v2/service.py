from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import os
import uuid

from app.fair_value_v2.runner import FairValueRunner
from app.fair_value_v2.feature_store.postgres_point_in_time import PostgresPointInTimeFeatureStore
from app.fair_value_v2.methods.registry import MethodRegistry
from app.fair_value_v2.schemas import FairValueV2Result, FeatureRow, MethodResult


_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
ENABLE_FAIR_VALUE_V2 = os.getenv("ENABLE_FAIR_VALUE_V2", "false").strip().lower() in _TRUE_VALUES


class FairValueV2Service:
    def __init__(self):
        base_dir = os.path.dirname(__file__)
        definitions_dir = os.path.join(base_dir, "methods", "definitions")
        self.registry = MethodRegistry.load_from_dir(definitions_dir)
        self.feature_store = PostgresPointInTimeFeatureStore()
        self.runner = FairValueRunner()

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def calculate(self, symbol: str, as_of_ts: Optional[datetime] = None) -> FairValueV2Result:
        return self.runner.run(symbol=symbol, as_of_ts=as_of_ts)

    def calculate_method(self, method_key: str, symbol: str, as_of_ts: Optional[datetime] = None) -> FairValueV2Result:
        ts = as_of_ts or self._now_utc()
        run_id = str(uuid.uuid4())

        # Validate method exists early for a clearer error surface in API callers.
        _ = self.registry.get(method_key)

        mr, features_hash = self.runner._run_method(method_key, symbol=symbol, as_of_ts=ts)
        return FairValueV2Result(
            run_id=run_id,
            symbol=symbol,
            as_of_ts=ts,
            fair_value=mr.fair_price,
            scenario_fair_values=(mr.metrics or {}).get("scenario_fair_values") or {},
            regime=f"method:{mr.method_key}",
            method_results=[mr],
            features_hash=features_hash,
        )

    def calculate_pb_bank(self, symbol: str, as_of_ts: Optional[datetime] = None) -> FairValueV2Result:
        ts = as_of_ts or self._now_utc()
        run_id = str(uuid.uuid4())
        mr, features_hash = self.runner._run_method("pb_bank", symbol=symbol, as_of_ts=ts)
        return FairValueV2Result(
            run_id=run_id,
            symbol=symbol,
            as_of_ts=ts,
            fair_value=mr.fair_price,
            scenario_fair_values=(mr.metrics or {}).get("scenario_fair_values") or {},
            regime="financials",
            method_results=[mr],
            features_hash=features_hash,
        )
