"""
Swing Trading Risk Management Service
Manages position sizing, portfolio heat, stop-losses
Industry Standard: Fixed fractional position sizing with portfolio heat limits
"""
import logging
from typing import Dict, Any, Optional, List
import pandas as pd

from app.database import db
from app.services.base import BaseService
from app.exceptions import DatabaseError, ValidationError

logger = logging.getLogger(__name__)


class SwingRiskManager(BaseService):
    """
    Risk management for swing trading
    
    SOLID: Single Responsibility - only handles risk management
    Industry Standard: Fixed fractional position sizing, portfolio heat limits
    """
    
    def __init__(self):
        """Initialize swing risk manager"""
        super().__init__()
        self.max_portfolio_risk = 0.05  # 5% total portfolio risk
        self.max_open_trades = 3
        self.max_position_size = 0.10  # 10% max per position
    
    def calculate_position_size(
        self,
        user_id: str,
        entry_price: float,
        stop_loss: float,
        risk_per_trade: float = 0.01
    ) -> Dict[str, Any]:
        """
        Calculate position size based on risk
        
        Industry Standard: Fixed fractional position sizing
        
        Args:
            user_id: User ID
            entry_price: Entry price
            stop_loss: Stop loss price
            risk_per_trade: Risk per trade as decimal (default: 0.01 = 1%)
        
        Returns:
            Dictionary with position_size_pct, position_value, shares, risk_amount
        
        Raises:
            ValidationError: If inputs are invalid
            DatabaseError: If database query fails
        """
        if entry_price <= 0:
            raise ValidationError(f"Entry price must be positive, got {entry_price}")
        
        if stop_loss <= 0:
            raise ValidationError(f"Stop loss must be positive, got {stop_loss}")
        
        if risk_per_trade <= 0 or risk_per_trade > 0.1:
            raise ValidationError(f"Risk per trade must be between 0 and 0.1, got {risk_per_trade}")
        
        if not user_id:
            raise ValidationError("User ID is required")
        
        try:
            # Get account balance
            account_balance = self._get_account_balance(user_id)
            
            if account_balance <= 0:
                raise ValidationError(f"Account balance must be positive, got {account_balance}")
            
            # Calculate risk amount
            risk_amount = account_balance * risk_per_trade
            
            # Calculate price risk
            price_risk = abs(entry_price - stop_loss)
            if price_risk == 0:
                return {
                    'position_size_pct': 0.0,
                    'position_value': 0.0,
                    'shares': 0,
                    'risk_amount': 0.0
                }
            
            # Calculate position value
            position_value = risk_amount / (price_risk / entry_price)
            position_size_pct = position_value / account_balance
            
            # Apply max position size
            position_size_pct = min(position_size_pct, self.max_position_size)
            position_value = account_balance * position_size_pct
            shares = int(position_value / entry_price)
            
            # Recalculate actual risk amount
            actual_risk_amount = shares * price_risk
            
            return {
                'position_size_pct': position_size_pct,
                'position_value': position_value,
                'shares': shares,
                'risk_amount': actual_risk_amount
            }
            
        except Exception as e:
            logger.error(f"Error calculating position size for user {user_id}: {e}", exc_info=True)
            if isinstance(e, ValidationError):
                raise
            raise DatabaseError(f"Failed to calculate position size: {str(e)}") from e
    
    def check_portfolio_heat(
        self,
        user_id: str,
        new_trade_risk: float
    ) -> Dict[str, Any]:
        """
        Check if adding new trade would exceed portfolio risk limits
        
        Industry Standard: Portfolio heat management
        
        Args:
            user_id: User ID
            new_trade_risk: Risk amount for new trade
        
        Returns:
            Dictionary with allowed, current_risk, max_risk, open_trades
        
        Raises:
            ValidationError: If inputs are invalid
            DatabaseError: If database query fails
        """
        if not user_id:
            raise ValidationError("User ID is required")
        
        if new_trade_risk < 0:
            raise ValidationError(f"New trade risk must be non-negative, got {new_trade_risk}")
        
        try:
            # Get current open trades
            open_trades = self._get_open_trades(user_id)
            current_risk = sum(trade.get('risk_amount', 0) for trade in open_trades)
            total_risk = current_risk + new_trade_risk
            
            # Get account balance
            account_balance = self._get_account_balance(user_id)
            
            if account_balance <= 0:
                raise ValidationError(f"Account balance must be positive, got {account_balance}")
            
            max_risk_amount = account_balance * self.max_portfolio_risk
            
            # Check if new trade is allowed
            risk_ok = total_risk <= max_risk_amount
            trades_ok = len(open_trades) < self.max_open_trades
            allowed = risk_ok and trades_ok
            
            # Log for debugging
            logger.debug(
                f"Portfolio heat check for user {user_id}: "
                f"current_risk={current_risk}, new_trade_risk={new_trade_risk}, "
                f"total_risk={total_risk}, max_risk={max_risk_amount}, "
                f"account_balance={account_balance}, open_trades={len(open_trades)}, "
                f"max_open_trades={self.max_open_trades}, risk_ok={risk_ok}, trades_ok={trades_ok}, allowed={allowed}"
            )
            
            return {
                'allowed': allowed,
                'current_risk': current_risk,
                'current_risk_pct': (current_risk / account_balance) * 100 if account_balance > 0 else 0,
                'total_risk': total_risk,
                'total_risk_pct': (total_risk / account_balance) * 100 if account_balance > 0 else 0,
                'max_risk': max_risk_amount,
                'max_risk_pct': self.max_portfolio_risk * 100,
                'open_trades': len(open_trades),
                'max_open_trades': self.max_open_trades
            }
            
        except Exception as e:
            logger.error(f"Error checking portfolio heat for user {user_id}: {e}", exc_info=True)
            if isinstance(e, ValidationError):
                raise
            raise DatabaseError(f"Failed to check portfolio heat: {str(e)}") from e
    
    def _get_account_balance(self, user_id: str) -> float:
        """
        Get user's account balance from portfolio
        
        Returns:
            Account balance in dollars
        
        Raises:
            DatabaseError: If query fails
        """
        try:
            query = """
                SELECT SUM(current_value) as total_value
                FROM holdings
                WHERE portfolio_id IN (
                    SELECT portfolio_id FROM portfolios WHERE user_id = :user_id
                )
            """
            result = db.execute_query(query, {"user_id": user_id})
            
            # SQL SUM returns NULL when there are no rows, which becomes None in Python
            if result and len(result) > 0:
                total_value_raw = result[0].get('total_value')
                # Check if total_value is not None and not NaN (SQL NULL)
                # Also check if it's a valid number (not 0 or negative)
                if total_value_raw is not None:
                    # Check for NaN (SQL NULL)
                    if isinstance(total_value_raw, float) and pd.isna(total_value_raw):
                        logger.debug(f"SQL returned NULL for user {user_id}, using default balance")
                    else:
                        try:
                            total_value = float(total_value_raw)
                            if total_value > 0:
                                logger.debug(f"Found holdings value ${total_value:,.2f} for user {user_id}")
                                return total_value
                            else:
                                logger.debug(f"Holdings value is 0 or negative for user {user_id}, using default balance")
                        except (ValueError, TypeError) as e:
                            logger.debug(f"Error converting total_value for user {user_id}: {e}, using default balance")
                else:
                    logger.debug(f"total_value is None for user {user_id}, using default balance")
            else:
                logger.debug(f"No result from query for user {user_id}, using default balance")
            
            # Default balance if no holdings or query returned NULL
            logger.debug(f"No holdings found for user {user_id}, using default balance of $100,000")
            return 100000.0  # Default $100k
            
        except Exception as e:
            logger.error(f"Error getting account balance for user {user_id}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to get account balance: {str(e)}") from e
    
    def _get_open_trades(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get user's open swing trades
        
        Returns:
            List of open trades with risk amounts
        
        Raises:
            DatabaseError: If query fails
        """
        try:
            query = """
                SELECT trade_id, stock_symbol, entry_price, stop_loss, position_size
                FROM swing_trades
                WHERE user_id = :user_id AND status = 'open'
            """
            result = db.execute_query(query, {"user_id": user_id})
            
            trades = []
            for row in result:
                entry_price = float(row['entry_price'])
                stop_loss = float(row['stop_loss'])
                position_size = float(row['position_size'])
                
                # Calculate risk amount
                price_risk = abs(entry_price - stop_loss)
                position_value = entry_price * (position_size / 100.0)  # position_size is percentage
                shares = position_value / entry_price
                risk_amount = shares * price_risk
                
                trades.append({
                    'trade_id': row['trade_id'],
                    'symbol': row['stock_symbol'],
                    'risk_amount': risk_amount
                })
            
            return trades
            
        except Exception as e:
            logger.error(f"Error getting open trades for user {user_id}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to get open trades: {str(e)}") from e

