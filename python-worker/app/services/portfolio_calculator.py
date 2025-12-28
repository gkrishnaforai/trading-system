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
    
    def update_holding_metrics(self, holding_id: str) -> bool:
        """
        Update all metrics for a single holding
        
        Args:
            holding_id: Holding ID to update
        
        Returns:
            True if successful
        """
        try:
            # Get holding
            query = """
                SELECT h.*, p.user_id
                FROM holdings h
                JOIN portfolios p ON h.portfolio_id = p.portfolio_id
                WHERE h.holding_id = :holding_id
            """
            holdings = db.execute_query(query, {"holding_id": holding_id})
            
            if not holdings:
                raise ValidationError(f"Holding {holding_id} not found")
            
            holding = holdings[0]
            symbol = holding['stock_symbol']
            
            # Fetch current price
            current_price = self.data_source.fetch_current_price(symbol)
            if current_price is None:
                self.log_warning(f"Could not fetch current price for {symbol}", context={'symbol': symbol})
                return False
            
            # Fetch fundamentals for sector/industry/dividend
            fundamentals = self.data_source.fetch_fundamentals(symbol)
            
            # Calculate metrics
            quantity = holding['quantity']
            avg_entry_price = holding['avg_entry_price']
            
            current_value = quantity * current_price
            cost_basis = quantity * avg_entry_price
            unrealized_gain_loss = current_value - cost_basis
            unrealized_gain_loss_percent = (unrealized_gain_loss / cost_basis * 100) if cost_basis > 0 else 0
            
            # Extract sector/industry from fundamentals
            sector = fundamentals.get('sector') or fundamentals.get('industry')
            industry = fundamentals.get('industry')
            market_cap = fundamentals.get('marketCap', 0)
            dividend_yield = fundamentals.get('dividendYield', 0)
            
            # Determine market cap category
            market_cap_category = self._get_market_cap_category(market_cap)
            
            # Get portfolio total value for allocation calculation
            portfolio_total = self._get_portfolio_total_value(holding['portfolio_id'])
            allocation_percent = (current_value / portfolio_total * 100) if portfolio_total > 0 else 0
            
            # Update holding
            update_query = """
                UPDATE holdings SET
                    current_price = :current_price,
                    current_value = :current_value,
                    cost_basis = :cost_basis,
                    unrealized_gain_loss = :unrealized_gain_loss,
                    unrealized_gain_loss_percent = :unrealized_gain_loss_percent,
                    sector = :sector,
                    industry = :industry,
                    market_cap_category = :market_cap_category,
                    dividend_yield = :dividend_yield,
                    allocation_percent = :allocation_percent,
                    last_updated_price = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE holding_id = :holding_id
            """
            
            db.execute_update(update_query, {
                "holding_id": holding_id,
                "current_price": current_price,
                "current_value": current_value,
                "cost_basis": cost_basis,
                "unrealized_gain_loss": unrealized_gain_loss,
                "unrealized_gain_loss_percent": unrealized_gain_loss_percent,
                "sector": sector,
                "industry": industry,
                "market_cap_category": market_cap_category,
                "dividend_yield": dividend_yield * 100 if dividend_yield else None,  # Convert to percentage
                "allocation_percent": allocation_percent
            })
            
            self.log_info(f"✅ Updated metrics for holding {holding_id} ({symbol})", 
                         context={'holding_id': holding_id, 'symbol': symbol})
            return True
            
        except Exception as e:
            self.log_error(f"Error updating holding metrics for {holding_id}", e, 
                          context={'holding_id': holding_id, 'symbol': symbol})
            raise DatabaseError(f"Failed to update holding metrics: {str(e)}") from e
    
    def update_portfolio_holdings(self, portfolio_id: str) -> int:
        """
        Update all holdings in a portfolio
        
        Args:
            portfolio_id: Portfolio ID
        
        Returns:
            Number of holdings updated
        """
        # Get all holdings
        query = "SELECT holding_id FROM holdings WHERE portfolio_id = :portfolio_id AND is_closed = 0"
        holdings = db.execute_query(query, {"portfolio_id": portfolio_id})
        
        updated_count = 0
        for holding in holdings:
            try:
                if self.update_holding_metrics(holding['holding_id']):
                    updated_count += 1
            except Exception as e:
                self.log_error(f"Error updating holding {holding['holding_id']}", e, 
                              context={'holding_id': holding['holding_id'], 'symbol': holding.get('stock_symbol')})
                # Continue with other holdings (fail-fast per holding, not all)
        
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
            # Get all holdings
            query = """
                SELECT * FROM holdings 
                WHERE portfolio_id = :portfolio_id AND is_closed = 0
            """
            holdings = db.execute_query(query, {"portfolio_id": portfolio_id})
            
            if not holdings:
                return {
                    "total_value": 0,
                    "cost_basis": 0,
                    "total_gain_loss": 0,
                    "total_gain_loss_percent": 0,
                    "total_stocks": 0
                }
            
            # Calculate totals
            total_value = sum(h.get('current_value') or 0 for h in holdings)
            cost_basis = sum(h.get('cost_basis') or (h['quantity'] * h['avg_entry_price']) for h in holdings)
            total_gain_loss = total_value - cost_basis
            total_gain_loss_percent = (total_gain_loss / cost_basis * 100) if cost_basis > 0 else 0
            
            # Calculate sector allocation
            sector_allocation = {}
            for holding in holdings:
                sector = holding.get('sector') or 'Unknown'
                value = holding.get('current_value') or (holding['quantity'] * holding.get('current_price', 0))
                sector_allocation[sector] = sector_allocation.get(sector, 0) + value
            
            # Get top holdings
            holdings_sorted = sorted(
                holdings,
                key=lambda h: h.get('current_value') or 0,
                reverse=True
            )
            top_holdings = [
                {
                    "symbol": h['stock_symbol'],
                    "value": h.get('current_value') or 0,
                    "allocation": h.get('allocation_percent') or 0
                }
                for h in holdings_sorted[:10]
            ]
            
            # Save snapshot
            query = """
                INSERT OR REPLACE INTO portfolio_performance
                (portfolio_id, snapshot_date, total_value, cost_basis, total_gain_loss, 
                 total_gain_loss_percent, invested_amount, sector_allocation, top_holdings)
                VALUES (:portfolio_id, :snapshot_date, :total_value, :cost_basis, :total_gain_loss,
                        :total_gain_loss_percent, :invested_amount, :sector_allocation, :top_holdings)
            """
            
            db.execute_update(query, {
                "portfolio_id": portfolio_id,
                "snapshot_date": snapshot_date.isoformat(),
                "total_value": total_value,
                "cost_basis": cost_basis,
                "total_gain_loss": total_gain_loss,
                "total_gain_loss_percent": total_gain_loss_percent,
                "invested_amount": cost_basis,
                "sector_allocation": json.dumps(sector_allocation),
                "top_holdings": json.dumps(top_holdings)
            })
            
            return {
                "total_value": total_value,
                "cost_basis": cost_basis,
                "total_gain_loss": total_gain_loss,
                "total_gain_loss_percent": total_gain_loss_percent,
                "total_stocks": len(holdings),
                "sector_allocation": sector_allocation,
                "top_holdings": top_holdings
            }
            
        except Exception as e:
            self.log_error("Error calculating portfolio performance", e, context={'portfolio_id': portfolio_id})
            raise DatabaseError(f"Failed to calculate portfolio performance: {str(e)}", details={'portfolio_id': portfolio_id}) from e
    
    def _get_portfolio_total_value(self, portfolio_id: str) -> float:
        """Get total portfolio value"""
        query = """
            SELECT COALESCE(SUM(current_value), 0) as total
            FROM holdings
            WHERE portfolio_id = :portfolio_id AND is_closed = 0
        """
        result = db.execute_query(query, {"portfolio_id": portfolio_id})
        return result[0]['total'] if result else 0.0
    
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

