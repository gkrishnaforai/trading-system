"""
Data-quality validation — sits between providers and the indicator engine.

    Provider -> normalize_bars -> validate_bars -> quant layer

`validate_bars` never raises on bad data; it returns a report so callers can
decide (reject, warn-and-continue, quarantine). Use strict=True on
MarketDataService.get_market_data to raise DataQualityError instead.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .models import OHLCVBar
from .policy import DAILY_INTERVALS


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class DataQualityIssue(BaseModel):
    code: str
    severity: IssueSeverity
    message: str
    detail: Dict[str, Any] = Field(default_factory=dict)


class DataQualityReport(BaseModel):
    symbol: str
    provider: str
    interval: str
    bar_count: int
    issues: List[DataQualityIssue] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == IssueSeverity.ERROR for i in self.issues)

    @property
    def errors(self) -> List[DataQualityIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.ERROR]

    @property
    def warnings(self) -> List[DataQualityIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.WARNING]


def validate_bars(
    bars: List[OHLCVBar],
    *,
    symbol: str = "",
    provider: str = "",
    interval: str = "1d",
    min_bars: int = 1,
    max_gap_days: int = 4,
    max_jump_pct: float = 0.5,
    stale_after_days: Optional[int] = None,
) -> DataQualityReport:
    """Validate a canonical bar series.

    Args:
        min_bars: minimum required bar count (e.g. 200 before computing SMA200)
        max_gap_days: flag calendar gaps larger than this (daily bars)
        max_jump_pct: flag |return| larger than this (possible unadjusted split)
        stale_after_days: flag last bar older than this (None disables)
    """
    issues: List[DataQualityIssue] = []

    def _report() -> DataQualityReport:
        return DataQualityReport(
            symbol=symbol or (bars[0].symbol if bars else ""),
            provider=provider or (bars[0].provider if bars else ""),
            interval=interval,
            bar_count=len(bars),
            issues=issues,
        )

    if not bars:
        issues.append(
            DataQualityIssue(
                code="no_bars",
                severity=IssueSeverity.ERROR,
                message="empty bar series",
            )
        )
        return _report()

    if len(bars) < min_bars:
        issues.append(
            DataQualityIssue(
                code="insufficient_bars",
                severity=IssueSeverity.ERROR,
                message=f"{len(bars)} bars < required {min_bars}",
                detail={"bar_count": len(bars), "min_bars": min_bars},
            )
        )

    # --- OHLC invariants + volume ---
    bad_ohlc: List[str] = []
    bad_volume: List[str] = []
    bad_price: List[str] = []
    for b in bars:
        ts = b.timestamp.isoformat()
        o, h, l, c = b.open, b.high, b.low, b.close
        if not (h >= l and h >= o and h >= c and l <= o and l <= c):
            bad_ohlc.append(ts)
        if b.volume is not None and b.volume < 0:
            bad_volume.append(ts)
        if any(v is None or v != v or v <= 0 for v in (o, h, l, c)):
            bad_price.append(ts)

    if bad_price:
        issues.append(DataQualityIssue(
            code="invalid_price",
            severity=IssueSeverity.ERROR,
            message=f"{len(bad_price)} bars with missing/non-positive prices",
            detail={"timestamps": bad_price[:10]},
        ))
    if bad_ohlc:
        issues.append(DataQualityIssue(
            code="ohlc_invariant",
            severity=IssueSeverity.ERROR,
            message=f"{len(bad_ohlc)} bars violate high>=open/close>=low",
            detail={"timestamps": bad_ohlc[:10]},
        ))
    if bad_volume:
        issues.append(DataQualityIssue(
            code="negative_volume",
            severity=IssueSeverity.ERROR,
            message=f"{len(bad_volume)} bars with negative volume",
            detail={"timestamps": bad_volume[:10]},
        ))

    # --- duplicates (normalize_bars dedupes, so this detects pre-normalized input) ---
    seen = set()
    dupes = []
    for b in bars:
        if b.timestamp in seen:
            dupes.append(b.timestamp.isoformat())
        seen.add(b.timestamp)
    if dupes:
        issues.append(DataQualityIssue(
            code="duplicate_timestamps",
            severity=IssueSeverity.ERROR,
            message=f"{len(dupes)} duplicate bar timestamps",
            detail={"timestamps": dupes[:10]},
        ))

    # --- gaps (daily bars only; holidays make this heuristic) ---
    if interval in DAILY_INTERVALS:
        gaps = []
        for prev, cur in zip(bars, bars[1:]):
            gap = (cur.timestamp.date() - prev.timestamp.date()).days
            if gap > max_gap_days:
                gaps.append({
                    "from": prev.timestamp.date().isoformat(),
                    "to": cur.timestamp.date().isoformat(),
                    "days": gap,
                })
        if gaps:
            issues.append(DataQualityIssue(
                code="date_gaps",
                severity=IssueSeverity.WARNING,
                message=f"{len(gaps)} gap(s) > {max_gap_days} calendar days",
                detail={"gaps": gaps[:10]},
            ))

    # --- price jumps (uses adj_close when available to avoid split false-positives) ---
    jumps = []
    for prev, cur in zip(bars, bars[1:]):
        p0 = prev.adj_close or prev.close
        p1 = cur.adj_close or cur.close
        if p0 and p1 and p0 > 0:
            ret = abs(p1 / p0 - 1)
            if ret > max_jump_pct:
                jumps.append({
                    "at": cur.timestamp.isoformat(),
                    "return_pct": round(ret * 100, 2),
                })
    if jumps:
        issues.append(DataQualityIssue(
            code="price_jumps",
            severity=IssueSeverity.WARNING,
            message=f"{len(jumps)} bar(s) moved > {max_jump_pct:.0%} (possible unadjusted split or bad print)",
            detail={"jumps": jumps[:10]},
        ))

    # --- zero volume (common for indices; warning only) ---
    zero_vol = sum(1 for b in bars if b.volume == 0)
    if zero_vol:
        issues.append(DataQualityIssue(
            code="zero_volume",
            severity=IssueSeverity.WARNING,
            message=f"{zero_vol} bars with zero volume",
            detail={"count": zero_vol},
        ))

    # --- staleness ---
    if stale_after_days is not None:
        last_ts = bars[-1].timestamp
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - last_ts).days
        if age_days > stale_after_days:
            issues.append(DataQualityIssue(
                code="stale_data",
                severity=IssueSeverity.WARNING,
                message=f"last bar is {age_days} days old (> {stale_after_days})",
                detail={"last_bar": last_ts.isoformat(), "age_days": age_days},
            ))

    return _report()
