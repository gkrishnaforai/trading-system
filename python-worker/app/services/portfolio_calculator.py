"""
Portfolio Calculator Service
Calculates and updates all portfolio and holding metrics
Industry Standard: Comprehensive portfolio analytics
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, date
import json

from app.database import db
from app.data_sources import get_data_source
from app.services.base import BaseService
from app.exceptions import DatabaseError, ValidationError
from app.utils.exception_handler import handle_database_errors


class PortfolioCalculatorService(BaseService):
    """
    Calculates and updates portfolio and holding metrics
    
    Responsibilities:
    - Update current prices for holdings
    - Calculate P&L (unrealized/realized)
    - Calculate portfolio allocation
    - Update sector/industry data
    - Calculate portfolio performance metrics
    
    SOLID: Single Responsibility - only calculates portfolio metrics
    """
    
    def __init__(self):
        """Initialize portfolio calculator service"""
        super().__init__()
        self.data_source = get_data_source()

    def _upsert_portfolio_position(
        self,
        *,
        portfolio_id: str,
        stock_id: str,
        quantity: float,
        avg_price: float,
        current_price: Optional[float],
    ) -> None:
        current_value = (quantity * current_price) if (current_price is not None) else None
        cost_basis = quantity * avg_price
        unrealized_gain_loss = (current_value - cost_basis) if current_value is not None else None
        unrealized_gain_loss_percent = (
            (unrealized_gain_loss / cost_basis * 100) if (unrealized_gain_loss is not None and cost_basis > 0) else None
        )

        db.execute_update(
            """
            INSERT INTO portfolio_positions
            (
                portfolio_id,
                stock_id,
                quantity,
                avg_price,
                current_price,
                current_value,
                unrealized_gain_loss,
                unrealized_gain_loss_percent,
                last_valued_at,
                updated_at
            )
            VALUES
            (
                :portfolio_id,
                :stock_id,
                :quantity,
                :avg_price,
                :current_price,
                :current_value,
                :unrealized_gain_loss,
                :unrealized_gain_loss_percent,
                CASE WHEN :current_price IS NULL THEN NULL ELSE NOW() END,
                NOW()
            )
            ON CONFLICT (portfolio_id, stock_id)
            DO UPDATE SET
                quantity = EXCLUDED.quantity,
                avg_price = EXCLUDED.avg_price,
                current_price = EXCLUDED.current_price,
                current_value = EXCLUDED.current_value,
                unrealized_gain_loss = EXCLUDED.unrealized_gain_loss,
                unrealized_gain_loss_percent = EXCLUDED.unrealized_gain_loss_percent,
                last_valued_at = EXCLUDED.last_valued_at,
                updated_at = NOW()
            """,
            {
                "portfolio_id": portfolio_id,
                "stock_id": stock_id,
                "quantity": quantity,
                "avg_price": avg_price,
                "current_price": current_price,
                "current_value": current_value,
                "unrealized_gain_loss": unrealized_gain_loss,
                "unrealized_gain_loss_percent": unrealized_gain_loss_percent,
            },
        )
    
    def update_holding_metrics(self, holding_id: str) -> bool:
        """
        Update all metrics for a single holding
        
        Args:
            holding_id: Holding ID to update
        
        Returns:
            True if successful
        """
        try:
            row = db.execute_query(
                """
                SELECT
                    pp.id AS holding_id,
                    pp.portfolio_id,
                    s.symbol,
                    pp.quantity,
                    pp.avg_price,
                    s.id AS stock_id
                FROM portfolio_positions pp
                JOIN stocks s
                  ON pp.stock_id = s.id
                WHERE pp.id = :holding_id
                """,
                {"holding_id": holding_id},
            )

            if not row:
                raise ValidationError(f"Holding {holding_id} not found")

            holding = row[0]
            symbol = holding.get("symbol")
            stock_id = holding.get("stock_id")
            portfolio_id = holding.get("portfolio_id")
            if not symbol or not stock_id or not portfolio_id:
                raise ValidationError(f"Holding {holding_id} missing required fields")

            price_result = self.data_source.fetch_current_price(symbol)
            current_price: Optional[float] = None
            if isinstance(price_result, dict):
                current_price = price_result.get("price")
            elif isinstance(price_result, (int, float)):
                current_price = float(price_result)

            if current_price is None:
                self.log_warning(
                    f"Could not fetch current price for {symbol}",
                    context={"symbol": symbol, "holding_id": holding_id},
                )
                return False

            self._upsert_portfolio_position(
                portfolio_id=str(portfolio_id),
                stock_id=str(stock_id),
                quantity=float(holding.get("quantity") or 0),
                avg_price=float(holding.get("avg_price") or 0),
                current_price=float(current_price),
            )

            self.log_info(
                f"✅ Updated metrics for holding {holding_id} ({symbol})",
                context={"holding_id": holding_id, "symbol": symbol},
            )
            return True
            
        except Exception as e:
            self.log_error(
                f"Error updating holding metrics for {holding_id}",
                e,
                context={"holding_id": holding_id},
            )
            raise DatabaseError(f"Failed to update holding metrics: {str(e)}") from e
    
    def update_portfolio_holdings(self, portfolio_id: str) -> int:
        """
        Update all holdings in a portfolio
        
        Args:
            portfolio_id: Portfolio ID
        
        Returns:
            Number of holdings updated
        """
        rows = db.execute_query(
            """
            SELECT
                pp.id AS holding_id,
                s.symbol,
                pp.quantity,
                pp.avg_price,
                pp.stock_id
            FROM portfolio_positions pp
            JOIN stocks s
              ON pp.stock_id = s.id
            WHERE pp.portfolio_id = :portfolio_id
            """,
            {"portfolio_id": portfolio_id},
        )
        
        updated_count = 0
        for row in rows:
            symbol = row.get("symbol")
            stock_id = row.get("stock_id")
            try:
                if not symbol or not stock_id:
                    continue

                current_price: Optional[float] = None
                try:
                    price_result = self.data_source.fetch_current_price(symbol)
                    if isinstance(price_result, dict):
                        current_price = price_result.get("price")
                    elif isinstance(price_result, (int, float)):
                        current_price = float(price_result)
                except Exception as price_error:
                    self.log_warning(
                        f"Could not fetch current price for {symbol}",
                        context={"symbol": symbol, "portfolio_id": portfolio_id, "error": str(price_error)},
                    )

                self._upsert_portfolio_position(
                    portfolio_id=portfolio_id,
                    stock_id=str(stock_id),
                    quantity=float(row.get("quantity") or 0),
                    avg_price=float(row.get("avg_price") or 0),
                    current_price=float(current_price) if current_price is not None else None,
                )
                updated_count += 1
            except Exception as e:
                self.log_error(
                    f"Error updating portfolio position for {symbol}",
                    e,
                    context={"portfolio_id": portfolio_id, "symbol": symbol, "stock_id": str(stock_id) if stock_id else None},
                )
                # Continue with other symbols
        
        return updated_count
    
    def calculate_portfolio_performance(self, portfolio_id: str, snapshot_date: date = None) -> Dict[str, Any]:
        """
        Calculate portfolio performance snapshot
        
        Args:
            portfolio_id: Portfolio ID
            snapshot_date: Date for snapshot (default: today)
        
        Returns:
            Performance metrics dictionary
        """
        if snapshot_date is None:
            snapshot_date = date.today()
        
        try:
            positions = db.execute_query(
                """
                SELECT
                    pp.current_value,
                    pp.quantity,
                    pp.avg_price,
                    s.symbol
                FROM portfolio_positions pp
                JOIN stocks s
                  ON pp.stock_id = s.id
                WHERE pp.portfolio_id = :portfolio_id
                """,
                {"portfolio_id": portfolio_id},
            )
            
            if not positions:
                return {
                    "total_value": 0,
                    "cost_basis": 0,
                    "total_gain_loss": 0,
                    "total_gain_loss_percent": 0,
                    "total_stocks": 0
                }
            
            # Calculate totals
            total_value = sum(p.get("current_value") or 0 for p in positions)
            cost_basis = sum((p.get("quantity") or 0) * (p.get("avg_price") or 0) for p in positions)
            total_gain_loss = total_value - cost_basis
            total_gain_loss_percent = (total_gain_loss / cost_basis * 100) if cost_basis > 0 else 0
            
            # Calculate sector allocation
            sector_allocation = {}
            for position in positions:
                sector_allocation["Unknown"] = sector_allocation.get("Unknown", 0) + float(position.get("current_value") or 0)
            
            # Get top holdings
            holdings_sorted = sorted(positions, key=lambda p: p.get("current_value") or 0, reverse=True)
            top_holdings = [
                {
                    "symbol": p.get("symbol"),
                    "value": p.get("current_value") or 0,
                    "allocation": 0
                }
                for p in holdings_sorted[:10]
            ]
            
            # Save snapshot
            db.execute_update(
                """
                INSERT INTO portfolio_snapshots
                (
                    portfolio_id,
                    snapshot_date,
                    total_value,
                    invested_value,
                    cash_balance,
                    created_at
                )
                VALUES
                (
                    :portfolio_id,
                    :snapshot_date,
                    :total_value,
                    :invested_value,
                    0,
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT (portfolio_id, snapshot_date)
                DO UPDATE SET
                    total_value = EXCLUDED.total_value,
                    invested_value = EXCLUDED.invested_value
                """,
                {
                    "portfolio_id": portfolio_id,
                    "snapshot_date": snapshot_date,
                    "total_value": total_value,
                    "invested_value": cost_basis,
                },
            )
            
            return {
                "total_value": total_value,
                "cost_basis": cost_basis,
                "total_gain_loss": total_gain_loss,
                "total_gain_loss_percent": total_gain_loss_percent,
                "total_stocks": len(positions),
                "sector_allocation": sector_allocation,
                "top_holdings": top_holdings
            }
            
        except Exception as e:
            self.log_error("Error calculating portfolio performance", e, context={'portfolio_id': portfolio_id})
            raise DatabaseError(f"Failed to calculate portfolio performance: {str(e)}", details={'portfolio_id': portfolio_id}) from e
    
    def _get_portfolio_total_value(self, portfolio_id: str) -> float:
        """Get total portfolio value"""
        result = db.execute_query(
            """
            SELECT COALESCE(SUM(current_value), 0) AS total
            FROM portfolio_positions
            WHERE portfolio_id = :portfolio_id
            """,
            {"portfolio_id": portfolio_id},
        )
        return float(result[0]["total"]) if result else 0.0
    
    def _get_market_cap_category(self, market_cap: float) -> Optional[str]:
        """Determine market cap category"""
        if not market_cap or market_cap == 0:
            return None
        
        # Market cap in billions
        market_cap_b = market_cap / 1_000_000_000
        
        if market_cap_b >= 200:
            return 'mega'
        elif market_cap_b >= 10:
            return 'large'
        elif market_cap_b >= 2:
            return 'mid'
        elif market_cap_b >= 0.3:
            return 'small'
        else:
            return 'micro'

