"""Read-only canonical PortfolioSnapshot provider."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional, Protocol

from app.database import db

from .adapters import portfolio_snapshot_from_api_rows
from .contracts import PortfolioSnapshot


class PortfolioRowSource(Protocol):
    def fetch_positions(self, portfolio_id: str) -> Iterable[dict[str, Any]]: ...


class DatabasePortfolioRowSource:
    """Read the current normalized portfolio_positions projection."""

    def fetch_positions(self, portfolio_id: str) -> list[dict[str, Any]]:
        return db.execute_query(
            """
            SELECT
                pp.id AS holding_id,
                pp.portfolio_id,
                s.symbol,
                pp.quantity,
                pp.avg_price,
                pp.current_price,
                pp.current_value,
                pp.unrealized_gain_loss,
                pp.unrealized_gain_loss_percent,
                pp.opened_at,
                pp.last_valued_at AS price_as_of,
                pp.updated_at,
                s.sector,
                s.industry,
                COALESCE(pp.metadata->>'asset_type', 'stock') AS asset_type,
                COALESCE(pp.metadata->>'side', 'LONG') AS side,
                pp.metadata->>'stop_price' AS stop_price,
                pp.metadata->>'target_price' AS target_price
            FROM portfolio_positions pp
            JOIN stocks s ON s.id = pp.stock_id
            WHERE pp.portfolio_id = :portfolio_id
            ORDER BY pp.updated_at DESC
            """,
            {"portfolio_id": portfolio_id},
        )


class PortfolioSnapshotProvider:
    """Build a canonical snapshot without starting portfolio analysis."""

    def __init__(
        self,
        row_source: Optional[PortfolioRowSource] = None,
        calculator_factory: Optional[Callable[[], Any]] = None,
    ):
        self.row_source = row_source or DatabasePortfolioRowSource()
        self.calculator_factory = calculator_factory

    def refresh_prices(self, portfolio_id: str) -> tuple[int, PortfolioSnapshot]:
        """Refresh cached holding prices, then read a new canonical snapshot."""
        if self.calculator_factory:
            calculator = self.calculator_factory()
        else:
            from app.services.portfolio_calculator import PortfolioCalculatorService
            calculator = PortfolioCalculatorService()
        updated = int(calculator.update_portfolio_holdings(portfolio_id))
        return updated, self.load(portfolio_id)

    @staticmethod
    def _latest_account_state(portfolio_id: str) -> dict:
        try:
            rows = db.execute_query(
                """
                SELECT account_equity, settled_cash, unsettled_cash, buying_power,
                       portfolio_heat, source, reconciliation_status, missing_fields, as_of
                FROM portfolio_account_states
                WHERE portfolio_id = :portfolio_id
                ORDER BY as_of DESC
                LIMIT 1
                """,
                {"portfolio_id": portfolio_id},
            )
        except Exception:
            return {}
        if not rows:
            return {}
        row = dict(rows[0])
        for field in ("account_equity", "settled_cash", "unsettled_cash",
                      "buying_power", "portfolio_heat"):
            if row.get(field) is not None:
                row[field] = float(row[field])
        return row

    def load(
        self,
        portfolio_id: str,
        *,
        account_equity: Optional[float] = None,
        settled_cash: Optional[float] = None,
        unsettled_cash: Optional[float] = None,
        buying_power: Optional[float] = None,
        portfolio_heat: Optional[float] = None,
        as_of: Optional[datetime] = None,
    ) -> PortfolioSnapshot:
        if not portfolio_id.strip():
            raise ValueError("portfolio_id is required")
        persisted = self._latest_account_state(portfolio_id)
        account_equity = account_equity if account_equity is not None else persisted.get("account_equity")
        settled_cash = settled_cash if settled_cash is not None else persisted.get("settled_cash")
        unsettled_cash = unsettled_cash if unsettled_cash is not None else persisted.get("unsettled_cash")
        buying_power = buying_power if buying_power is not None else persisted.get("buying_power")
        portfolio_heat = portfolio_heat if portfolio_heat is not None else persisted.get("portfolio_heat")

        rows = self.row_source.fetch_positions(portfolio_id)
        snapshot = portfolio_snapshot_from_api_rows(
            portfolio_id,
            rows,
            account_equity=account_equity,
            settled_cash=settled_cash,
            source="portfolio_positions",
            as_of=as_of or datetime.now(timezone.utc),
        )
        missing_account = [
            f"account_state:{field}" for field, value in {
                "account_equity": account_equity,
                "settled_cash": settled_cash,
                "buying_power": buying_power,
                "portfolio_heat": portfolio_heat,
            }.items() if value is None
        ]
        return snapshot.model_copy(update={
            "unsettled_cash": unsettled_cash,
            "buying_power": buying_power,
            "portfolio_heat": portfolio_heat,
            "reconciliation_status": "UNRECONCILED" if missing_account else "RECONCILED",
            "missing_fields": list(dict.fromkeys(snapshot.missing_fields + missing_account)),
        })

    def load_latest_persisted(self, portfolio_id: str) -> Optional[PortfolioSnapshot]:
        """Load the latest append-only snapshot and its position projection."""
        snapshot_rows = db.execute_query(
            """
            SELECT snapshot_id, portfolio_id, as_of, account_equity,
                   settled_cash, unsettled_cash, buying_power, invested_value,
                   portfolio_heat, price_freshness, reconciliation_status,
                   missing_fields, source
            FROM portfolio_agent_snapshots
            WHERE portfolio_id = :portfolio_id
            ORDER BY as_of DESC, created_at DESC
            LIMIT 1
            """,
            {"portfolio_id": portfolio_id},
        )
        if not snapshot_rows:
            return None
        row = snapshot_rows[0]
        position_rows = db.execute_query(
            """
            SELECT position_state_id AS holding_id, portfolio_id, symbol,
                   asset_type, side, quantity, average_entry_price AS avg_price,
                   current_price, current_value, unrealized_pnl AS unrealized_gain_loss,
                   unrealized_pnl_pct AS unrealized_gain_loss_percent,
                   sector, industry, stop_price, target_price, opened_at,
                   as_of, price_as_of, status, source
            FROM portfolio_agent_position_states
            WHERE snapshot_id = CAST(:snapshot_id AS uuid)
            ORDER BY symbol
            """,
            {"snapshot_id": str(row["snapshot_id"])},
        )
        snapshot = portfolio_snapshot_from_api_rows(
            portfolio_id,
            position_rows,
            account_equity=row.get("account_equity"),
            settled_cash=row.get("settled_cash"),
            source=row.get("source") or "portfolio_agent_snapshots",
            as_of=row.get("as_of"),
        )
        return snapshot.model_copy(update={
            "unsettled_cash": row.get("unsettled_cash"),
            "buying_power": row.get("buying_power"),
            "portfolio_heat": row.get("portfolio_heat"),
            "price_freshness": row.get("price_freshness") or snapshot.price_freshness,
            "reconciliation_status": row.get("reconciliation_status") or "UNKNOWN",
            "missing_fields": row.get("missing_fields") or snapshot.missing_fields,
        })

    @staticmethod
    def from_rows(
        portfolio_id: str,
        rows: Iterable[dict[str, Any]],
        **account_fields: Any,
    ) -> PortfolioSnapshot:
        """Pure adapter entry point for API/import/replay tests."""
        return portfolio_snapshot_from_api_rows(
            portfolio_id, rows, source="injected_rows", **account_fields)
