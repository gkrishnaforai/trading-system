from dataclasses import dataclass
from datetime import date
from typing import Optional

@dataclass(frozen=True)
class DailyBarUpsertRow:
    stock_symbol: str
    trade_date: date
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    adj_close: Optional[float]
    volume: Optional[int]
    source: Optional[str]
