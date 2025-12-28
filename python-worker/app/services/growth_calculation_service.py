"""
Growth Calculation Service
Calculates YoY growth metrics from financial statements
Industry Standard: Financial analyst growth calculations
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, date

from app.database import db
from app.services.base import BaseService
from app.exceptions import DatabaseError, ValidationError
from app.utils.exception_handler import handle_database_errors

logger = logging.getLogger(__name__)


class GrowthCalculationService(BaseService):
    """
    Service for calculating growth metrics from financial statements
    
    Calculates:
    - Revenue growth (YoY)
    - EPS growth (YoY)
    - Earnings growth (YoY)
    - Updates enhanced_fundamentals table with growth metrics
    """
    
    def __init__(self):
        """Initialize growth calculation service"""
        super().__init__()
    
    @handle_database_errors
    def calculate_growth_metrics(self, symbol: str, force: bool = False) -> Dict[str, Any]:
        """
        Calculate growth metrics from income statements
        
        Args:
            symbol: Stock symbol
            force: Force recalculation even if data exists
        
        Returns:
            Dict with growth metrics
        """
        try:
            # Fetch income statements ordered by period_end (most recent first)
            income_statements = db.execute_query(
                """
                SELECT period_end, fiscal_year, fiscal_quarter, timeframe,
                       revenues, total_revenue, net_income, net_income_per_share,
                       weighted_average_shares_outstanding
                FROM income_statements
                WHERE stock_symbol = :stock_symbol
                ORDER BY period_end DESC, fiscal_year DESC, fiscal_quarter DESC
                LIMIT 20
                """,
                {'stock_symbol': symbol}
            )
            
            if not income_statements or len(income_statements) < 2:
                logger.warning(f"Insufficient income statements for {symbol}: need at least 2 periods, have {len(income_statements) if income_statements else 0}")
                return {
                    'success': False,
                    'symbol': symbol,
                    'error': 'Insufficient data',
                    'metrics': {}
                }
            
            # Calculate growth metrics
            metrics = {}
            
            # Get latest period
            latest = income_statements[0]
            latest_revenue = latest.get('revenues') or latest.get('total_revenue')
            latest_net_income = latest.get('net_income')
            latest_eps = latest.get('net_income_per_share')
            latest_period_end = latest.get('period_end')
            latest_fiscal_year = latest.get('fiscal_year')
            
            # Find comparable period from previous year
            # For quarterly: compare Q1 2024 vs Q1 2023
            # For annual: compare FY 2023 vs FY 2022
            previous_year_period = None
            if latest.get('timeframe') == 'quarterly':
                # Find same quarter from previous year
                target_quarter = latest.get('fiscal_quarter')
                target_year = latest_fiscal_year - 1
                for stmt in income_statements[1:]:
                    if (stmt.get('fiscal_year') == target_year and 
                        stmt.get('fiscal_quarter') == target_quarter and
                        stmt.get('timeframe') == 'quarterly'):
                        previous_year_period = stmt
                        break
            else:
                # Annual: find previous year
                target_year = latest_fiscal_year - 1
                for stmt in income_statements[1:]:
                    if (stmt.get('fiscal_year') == target_year and
                        stmt.get('timeframe') == 'annual'):
                        previous_year_period = stmt
                        break
            
            # Calculate revenue growth
            if latest_revenue and previous_year_period:
                prev_revenue = previous_year_period.get('revenues') or previous_year_period.get('total_revenue')
                if prev_revenue and prev_revenue > 0:
                    revenue_growth = ((latest_revenue - prev_revenue) / prev_revenue) * 100
                    metrics['revenue_growth'] = round(revenue_growth, 2)
            
            # Calculate earnings growth
            if latest_net_income and previous_year_period:
                prev_net_income = previous_year_period.get('net_income')
                if prev_net_income and prev_net_income != 0:
                    earnings_growth = ((latest_net_income - prev_net_income) / abs(prev_net_income)) * 100
                    metrics['earnings_growth'] = round(earnings_growth, 2)
            
            # Calculate EPS growth
            if latest_eps and previous_year_period:
                prev_eps = previous_year_period.get('net_income_per_share')
                if prev_eps and prev_eps != 0:
                    eps_growth = ((latest_eps - prev_eps) / abs(prev_eps)) * 100
                    metrics['eps_growth'] = round(eps_growth, 2)
            
            # Update enhanced_fundamentals table
            if metrics:
                # Get or create enhanced_fundamentals record
                existing = db.execute_query(
                    """
                    SELECT id, as_of_date FROM enhanced_fundamentals
                    WHERE stock_symbol = :stock_symbol
                    ORDER BY as_of_date DESC
                    LIMIT 1
                    """,
                    {'stock_symbol': symbol}
                )
                
                if existing and existing[0]:
                    # Update existing record
                    db.execute_update(
                        """
                        UPDATE enhanced_fundamentals
                        SET revenue_growth = :revenue_growth,
                            earnings_growth = :earnings_growth,
                            eps_growth = :eps_growth,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE stock_symbol = :stock_symbol AND as_of_date = :as_of_date
                        """,
                        {
                            'revenue_growth': metrics.get('revenue_growth'),
                            'earnings_growth': metrics.get('earnings_growth'),
                            'eps_growth': metrics.get('eps_growth'),
                            'stock_symbol': symbol,
                            'as_of_date': existing[0]['as_of_date']
                        }
                    )
                    logger.info(f"✅ Updated growth metrics for {symbol}")
                else:
                    # Create new record if doesn't exist
                    db.execute_update(
                        """
                        INSERT INTO enhanced_fundamentals
                        (stock_symbol, as_of_date, revenue_growth, earnings_growth, eps_growth)
                        VALUES (:stock_symbol, :as_of_date, :revenue_growth, :earnings_growth, :eps_growth)
                        """,
                        {
                            'stock_symbol': symbol,
                            'as_of_date': latest_period_end,
                            'revenue_growth': metrics.get('revenue_growth'),
                            'earnings_growth': metrics.get('earnings_growth'),
                            'eps_growth': metrics.get('eps_growth')
                        }
                    )
                    logger.info(f"✅ Created growth metrics for {symbol}")
            
            return {
                'success': True,
                'symbol': symbol,
                'metrics': metrics,
                'period': {
                    'latest': latest_period_end,
                    'previous': previous_year_period.get('period_end') if previous_year_period else None
                }
            }
            
        except Exception as e:
            self.log_error(f"Error calculating growth metrics for {symbol}", e)
            raise DatabaseError(f"Failed to calculate growth metrics for {symbol}: {str(e)}") from e
    
    @handle_database_errors
    def calculate_all_symbols(self, symbols: List[str], force: bool = False) -> Dict[str, Any]:
        """
        Calculate growth metrics for multiple symbols
        
        Args:
            symbols: List of stock symbols
            force: Force recalculation
        
        Returns:
            Dict with results for each symbol
        """
        results = {}
        succeeded = 0
        failed = 0
        
        for symbol in symbols:
            try:
                result = self.calculate_growth_metrics(symbol, force)
                results[symbol] = result
                if result.get('success'):
                    succeeded += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Error calculating growth for {symbol}: {e}")
                results[symbol] = {'success': False, 'error': str(e)}
                failed += 1
        
        return {
            'success': failed == 0,
            'total': len(symbols),
            'succeeded': succeeded,
            'failed': failed,
            'results': results
        }

