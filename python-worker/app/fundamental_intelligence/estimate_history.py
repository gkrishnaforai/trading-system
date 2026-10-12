"""Shared estimate-snapshot persistence and momentum resolution.

Point-in-time estimate snapshots accumulate over days; revision momentum is
only computable once the same fiscal period has snapshots ≥14 days apart.
Both the fundamental-intelligence graph and the swing graph record snapshots
here so history matures regardless of which workflow ran.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterable, Optional

from app.market_data.models import FinancialEstimate

from .momentum import (
    FundamentalEstimateSnapshot,
    FundamentalMomentumAssessment,
    assess_fundamental_momentum,
)
from .momentum_store import FundamentalMomentumStore
from .store import FundamentalEstimateStore

logger = logging.getLogger(__name__)


def record_estimate_snapshots(
    symbol: str,
    estimates: Iterable[FinancialEstimate],
    *,
    store: Optional[FundamentalEstimateStore] = None,
) -> list[FundamentalEstimateSnapshot]:
    """Persist point-in-time snapshots for usable provider estimates."""
    store = store or FundamentalEstimateStore()
    rows: list[FundamentalEstimateSnapshot] = []
    for estimate in estimates:
        if not estimate.forecast_date or estimate.fiscal_year is None:
            continue
        snapshot = FundamentalEstimateSnapshot(
            symbol=symbol.upper(),
            as_of=date.today(),
            fiscal_period=estimate.fiscal_period,
            fiscal_year=estimate.fiscal_year,
            eps_estimate=estimate.eps_avg,
            revenue_estimate=estimate.revenue_avg,
            analyst_count=estimate.analyst_count_eps or estimate.analyst_count_revenue,
            provider=estimate.provider,
            source_timestamp=date.today(),
        )
        try:
            store.save(snapshot)
            rows.append(snapshot)
        except Exception as exc:
            logger.warning("estimate snapshot save failed for %s: %s", symbol, exc)
    return rows


def compute_symbol_momentum(
    symbol: str,
    estimate_rows: Optional[list[FundamentalEstimateSnapshot]] = None,
    *,
    estimate_store: Optional[FundamentalEstimateStore] = None,
    momentum_store: Optional[FundamentalMomentumStore] = None,
) -> Optional[FundamentalMomentumAssessment]:
    """Best available momentum: fresh computation, else latest persisted row."""
    estimate_store = estimate_store or FundamentalEstimateStore()
    momentum_store = momentum_store or FundamentalMomentumStore()
    try:
        momentum = momentum_store.latest(symbol)
    except Exception:
        momentum = None
    if not estimate_rows:
        return momentum
    candidates = []
    for row in estimate_rows:
        try:
            history = estimate_store.history(symbol, row.fiscal_period, row.fiscal_year)
            candidates.append(assess_fundamental_momentum(symbol, history + [row]))
        except Exception as exc:
            logger.warning("momentum assessment failed for %s: %s", symbol, exc)
    if candidates:
        momentum = max(candidates, key=lambda item: (item.coverage, item.score or -1))
    if momentum is not None:
        try:
            momentum_store.save(momentum, as_of_date=date.today().isoformat())
        except Exception as exc:
            logger.warning("momentum save failed for %s: %s", symbol, exc)
    return momentum
