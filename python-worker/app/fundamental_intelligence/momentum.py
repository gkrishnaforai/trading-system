"""Deterministic fundamental-expectation momentum."""
from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from pydantic import BaseModel, Field


class FundamentalEstimateSnapshot(BaseModel):
    symbol: str
    as_of: date
    fiscal_period: str
    fiscal_year: int
    eps_estimate: Optional[float] = None
    revenue_estimate: Optional[float] = None
    eps_growth_estimate: Optional[float] = None
    revenue_growth_estimate: Optional[float] = None
    analyst_count: Optional[int] = Field(default=None, ge=0)
    analysts_up: Optional[int] = Field(default=None, ge=0)
    analysts_down: Optional[int] = Field(default=None, ge=0)
    analysts_unchanged: Optional[int] = Field(default=None, ge=0)
    guidance_direction: str = "UNKNOWN"
    provider: str
    source_timestamp: Optional[date] = None


class FundamentalMomentumAssessment(BaseModel):
    symbol: str
    score: Optional[float] = Field(default=None, ge=0, le=100)
    label: str = "UNAVAILABLE"
    eps_revision_14d: Optional[float] = None
    eps_revision_30d: Optional[float] = None
    revenue_revision_30d: Optional[float] = None
    growth_acceleration: Optional[float] = None
    revision_breadth: Optional[float] = None
    net_revision_breadth: Optional[float] = None
    estimate_dispersion: Optional[float] = None
    guidance_direction: str = "UNKNOWN"
    coverage: float = Field(default=0, ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    source: str = "deterministic"
    rules_version: str = "fundamental-momentum-v1"


def _revision(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous)


def _assess_fundamental_momentum(
    symbol: str,
    snapshots: Iterable[FundamentalEstimateSnapshot],
) -> FundamentalMomentumAssessment:
    rows = sorted(
        [row for row in snapshots if row.symbol.upper() == symbol.upper()],
        key=lambda row: row.as_of,
    )
    if len(rows) < 2:
        return FundamentalMomentumAssessment(
            symbol=symbol.upper(),
            reasons=["at least two point-in-time estimate snapshots are required"],
        )

    latest = rows[-1]
    previous_14 = next((row for row in reversed(rows[:-1]) if (latest.as_of - row.as_of).days >= 14), None)
    previous_30 = next((row for row in reversed(rows[:-1]) if (latest.as_of - row.as_of).days >= 30), None)
    eps14 = _revision(latest.eps_estimate, previous_14.eps_estimate if previous_14 else None)
    eps30 = _revision(latest.eps_estimate, previous_30.eps_estimate if previous_30 else None)
    rev30 = _revision(latest.revenue_estimate, previous_30.revenue_estimate if previous_30 else None)
    growth_accel = _revision(latest.eps_growth_estimate, previous_30.eps_growth_estimate if previous_30 else None)

    breadth = None
    net_breadth = None
    if latest.analyst_count and (latest.analysts_up is not None or latest.analysts_down is not None):
        up = latest.analysts_up or 0
        down = latest.analysts_down or 0
        breadth = up / latest.analyst_count
        net_breadth = (up - down) / latest.analyst_count

    revision_parts = [value for value in [eps14, eps30, rev30, growth_accel] if value is not None]
    score_parts = revision_parts + ([net_breadth] if net_breadth is not None else [])
    score = None
    if score_parts:
        raw = sum(max(-1.0, min(1.0, value * 5)) for value in score_parts) / len(score_parts)
        score = round(max(0.0, min(100.0, 50 + raw * 50)), 1)
    label = "UNAVAILABLE" if score is None else (
        "STRONG" if score >= 70 else "IMPROVING" if score >= 55 else
        "DETERIORATING" if score < 45 else "NEUTRAL"
    )
    reasons = []
    if eps14 is not None:
        reasons.append(f"EPS estimate revision 14d: {eps14:+.1%}")
    if rev30 is not None:
        reasons.append(f"revenue estimate revision 30d: {rev30:+.1%}")
    if net_breadth is not None:
        reasons.append(f"net analyst revision breadth: {net_breadth:+.1%}")
    if not reasons:
        reasons.append("estimate revision history is incomplete")
    return FundamentalMomentumAssessment(
        symbol=symbol.upper(), score=score, label=label,
        eps_revision_14d=eps14, eps_revision_30d=eps30,
        revenue_revision_30d=rev30, growth_acceleration=growth_accel,
        revision_breadth=breadth, net_revision_breadth=net_breadth,
        guidance_direction=latest.guidance_direction,
        coverage=len(score_parts) / 5,
        reasons=reasons,
    )


def assess_fundamental_momentum(
    symbol: str,
    snapshots: Iterable[FundamentalEstimateSnapshot],
) -> FundamentalMomentumAssessment:
    from .tracing import observe_fundamental_momentum
    rows = list(snapshots)
    with observe_fundamental_momentum(
        symbol=symbol,
        metadata={"snapshot_count": len(rows), "rules_version": "fundamental-momentum-v1"},
    ):
        return _assess_fundamental_momentum(symbol, rows)
