"""Adapters from existing portfolio API/database row shapes to canonical contracts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from .contracts import DataFreshness, PositionState, PositionStatus, PortfolioSnapshot


def _float(row: dict[str, Any], *names: str) -> Optional[float]:
    for name in names:
        value = row.get(name)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _timestamp(row: dict[str, Any], *names: str) -> Optional[datetime]:
    for name in names:
        value = row.get(name)
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if value:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def position_from_api_row(
    row: dict[str, Any],
    *,
    portfolio_id: str,
    source: str = "portfolio_api",
) -> tuple[PositionState, bool]:
    """Map v1/v2 holdings or portfolio_positions response fields."""
    symbol = str(row.get("symbol") or row.get("stock_symbol") or "").upper()
    quantity = _float(row, "quantity", "shares_held") or 0.0
    current_price = _float(row, "current_price")
    current_value = _float(row, "current_value", "market_value")
    price_as_of = _timestamp(row, "price_as_of", "current_price_as_of", "updated_at")
    missing = current_price is None or current_value is None
    return PositionState(
        position_id=str(row.get("id") or row.get("holding_id") or f"{portfolio_id}:{symbol}"),
        portfolio_id=portfolio_id,
        symbol=symbol,
        asset_type=str(row.get("asset_type") or "stock"),
        side=str(row.get("side") or "LONG").upper(),
        quantity=quantity,
        average_entry_price=_float(row, "avg_price", "average_cost", "avg_entry_price"),
        current_price=current_price,
        current_value=current_value,
        unrealized_pnl=_float(row, "unrealized_gain_loss", "unrealized_pnl"),
        unrealized_pnl_pct=_float(row, "unrealized_gain_loss_percent", "unrealized_pnl_pct"),
        sector=row.get("sector"),
        industry=row.get("industry"),
        stop_price=_float(row, "stop_price", "stop_loss"),
        target_price=_float(row, "target_price", "take_profit"),
        opened_at=_timestamp(row, "opened_at", "created_at"),
        as_of=_timestamp(row, "as_of", "updated_at"),
        price_as_of=price_as_of,
        status=PositionStatus.OPEN if quantity > 0 else PositionStatus.CLOSED,
        source=source,
    ), missing


def portfolio_snapshot_from_api_rows(
    portfolio_id: str,
    rows: Iterable[dict[str, Any]],
    *,
    account_equity: Optional[float] = None,
    settled_cash: Optional[float] = None,
    source: str = "portfolio_api",
    as_of: Optional[datetime] = None,
) -> PortfolioSnapshot:
    """Create a conservative snapshot; missing cash/equity stays missing."""
    positions = []
    missing_fields: list[str] = []
    for row in rows:
        position, missing_price = position_from_api_row(
            row, portfolio_id=portfolio_id, source=source)
        positions.append(position)
        if missing_price:
            missing_fields.append(f"{position.symbol}:current_price_or_value")

    invested = sum(p.current_value or 0.0 for p in positions)
    equity = account_equity
    if equity is None and settled_cash is not None:
        equity = settled_cash + invested
        missing_fields.append("account_equity_derived")
    if settled_cash is None:
        missing_fields.append("settled_cash")

    symbol_exposure = {
        p.symbol: ((p.current_value or 0.0) / equity if equity else 0.0)
        for p in positions
    }
    sector_exposure: dict[str, float] = {}
    for position in positions:
        if position.sector:
            sector_exposure[position.sector] = sector_exposure.get(position.sector, 0.0) + symbol_exposure.get(position.symbol, 0.0)
        else:
            missing_fields.append(f"{position.symbol}:sector")

    return PortfolioSnapshot(
        portfolio_id=portfolio_id,
        as_of=as_of or datetime.now(timezone.utc),
        account_equity=equity,
        settled_cash=settled_cash,
        invested_value=invested,
        positions=positions,
        symbol_exposure=symbol_exposure,
        sector_exposure=sector_exposure,
        price_freshness=DataFreshness.ACCEPTABLE if not missing_fields else DataFreshness.UNKNOWN,
        reconciliation_status="UNRECONCILED",
        missing_fields=list(dict.fromkeys(missing_fields)),
        source=source,
    )
