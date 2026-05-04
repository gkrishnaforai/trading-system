from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class FeatureRow(BaseModel):
    symbol: str
    as_of_ts: datetime
    scalars: Dict[str, Any] = Field(default_factory=dict)
    series: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    sources: Dict[str, str] = Field(default_factory=dict)
    quality: Dict[str, Any] = Field(default_factory=dict)


class MethodDefinition(BaseModel):
    method_key: str
    version: int
    category: str
    requires: Dict[str, List[str]] = Field(default_factory=dict)
    params: Dict[str, Any] = Field(default_factory=dict)
    formula: Dict[str, Any]
    validations: List[Dict[str, Any]] = Field(default_factory=list)


MethodStatus = Literal["ok", "missing_data", "invalid_assumption", "disabled", "error"]


class MethodResult(BaseModel):
    method_key: str
    version: int
    enabled: bool
    status: MethodStatus
    fair_price: Optional[float] = None
    inputs_used: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    reason_code: Optional[str] = None
    reason_details: Optional[Dict[str, Any]] = None


class FairValueV2Result(BaseModel):
    run_id: str
    symbol: str
    as_of_ts: datetime
    fair_value: Optional[float] = None
    scenario_fair_values: Dict[str, Optional[float]] = Field(default_factory=dict)
    regime: Optional[str] = None
    method_results: List[MethodResult] = Field(default_factory=list)
    features_hash: Optional[str] = None
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    model_version: str = "fair_value_v2"
