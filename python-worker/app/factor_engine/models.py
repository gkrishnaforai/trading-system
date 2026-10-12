from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class FactorSnapshot:
    factor_id: str
    symbol: str
    as_of_date: date
    value: Any
    confidence: int
    source: str
    source_timestamp: Optional[datetime] = None
    metadata: Optional[Mapping[str, Any]] = None
