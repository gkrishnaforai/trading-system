"""
Canonical market-data policy.

Providers disagree on subtle semantics (adjusted vs raw close, bar timestamps
in exchange tz vs UTC). Every adapter converts its native format into this
policy, and `normalize_bars` enforces the mechanical parts post-fetch.

Policy:
  - `close` is the raw (unadjusted) close; `adj_close` carries split+dividend
    adjustments when the provider offers it (None otherwise — never guessed)
  - intraday timestamps are normalized to timezone-aware UTC
  - daily+ bars carry the exchange trading date (UTC-midnight anchored)
  - regular session only — no pre/post-market bars
  - volume is exchange-reported
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

from .models import OHLCVBar

DAILY_INTERVALS = {"1d", "1day", "day", "1w", "1wk", "week", "1mo", "month"}


@dataclass(frozen=True)
class PricePolicy:
    adjusted_close_separate: bool = True  # close = raw; adj_close = adjusted
    bar_timezone: str = "UTC"
    daily_bar_anchor: str = "trading_date"
    session: str = "regular"
    volume: str = "exchange_reported"
    currency: str = "USD"


CANONICAL_PRICE_POLICY = PricePolicy()


def _normalize_ts(ts: datetime, interval: str) -> datetime:
    """Enforce the timestamp policy for one bar."""
    if ts is None:
        return ts
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc)
    if interval in DAILY_INTERVALS:
        # Daily bars represent a trading date, not a moment in time.
        return datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def normalize_bars(bars: List[OHLCVBar], interval: str = "1d") -> List[OHLCVBar]:
    """Enforce canonical policy on bars from any provider:
    - timestamps -> policy tz/anchor
    - sort ascending, dedupe on timestamp (last write wins)
    """
    out: dict[datetime, OHLCVBar] = {}
    for bar in bars:
        if bar.timestamp is None:
            continue
        bar = bar.model_copy(update={"timestamp": _normalize_ts(bar.timestamp, interval)})
        out[bar.timestamp] = bar
    return sorted(out.values(), key=lambda b: b.timestamp)
