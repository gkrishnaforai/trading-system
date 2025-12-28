"""
Portfolio signal generation service
Generates portfolio-level signals based on holdings and strategies
"""
from datetime import date, datetime
from typing import List, Dict, Any, Optional
import uuid

from app.database import db
from app.services.base import BaseService
from app.services.indicator_service import IndicatorService
from app.services.strategy_service import StrategyService
from app.exceptions import DatabaseError, ValidationError
from app.utils.validation_patterns import validate_symbol_param
from app.utils.exception_handler import handle_exceptions, handle_database_errors


class PortfolioService(BaseService):
    """
    Service for portfolio-level signal generation
    
    SOLID: Single Responsibility - only handles portfolio signal generation
    Dependency Injection: Receives dependencies via constructor
    """
    
    def __init__(
        self,
        indicator_service: IndicatorService,
        strategy_service: StrategyService
    ):
        """
        Initialize portfolio service with dependencies
        
        Args:
            indicator_service: Indicator service instance
            strategy_service: Strategy service instance
        """
        super().__init__()
        self.indicator_service = indicator_service
        self.strategy_service = strategy_service
    
    def generate_portfolio_signals(self, portfolio_id: str) -> int:
        """
        Generate signals for all holdings in a portfolio
        
        Returns:
            Number of signals generated
        """
        try:
            # Get all holdings for the portfolio
            query = """
                SELECT h.holding_id, h.stock_symbol, h.position_type, h.strategy_tag,
                       p.user_id, u.subscription_level
                FROM holdings h
                JOIN portfolios p ON h.portfolio_id = p.portfolio_id
                JOIN users u ON p.user_id = u.user_id
                WHERE h.portfolio_id = :portfolio_id
            """
            
            holdings = db.execute_query(query, {"portfolio_id": portfolio_id})
            
            if not holdings:
                self.log_warning(f"No holdings found for portfolio {portfolio_id}")
                return 0
            
            signals_generated = 0
            
            for holding in holdings:
                symbol = holding['stock_symbol']
                position_type = holding['position_type']
                strategy_tag = holding.get('strategy_tag')
                subscription_level = holding['subscription_level']
                
                # Get latest indicators
                indicators = self.indicator_service.get_latest_indicators(symbol)
                
                if not indicators:
                    self.log_warning(f"No indicators found for {symbol}, skipping signal generation", 
                                   context={'symbol': symbol, 'portfolio_id': portfolio_id})
                    continue
                
                # Validate symbol using pattern
                try:
                    symbol = validate_symbol_param(symbol)
                except ValidationError:
                    self.log_warning(f"Invalid symbol: {symbol}", 
                                   context={'symbol': symbol, 'portfolio_id': portfolio_id})
                    continue
                
                # Get strategy for this portfolio
                portfolio_strategy = self.strategy_service.get_portfolio_strategy(portfolio_id)
                
                # Generate signal using the portfolio's strategy
                signal = self._generate_signal_for_holding(
                    holding, indicators, subscription_level, portfolio_strategy
                )
                
                if signal:
                    # Save signal
                    signal_id = str(uuid.uuid4())
                    query = """
                        INSERT OR REPLACE INTO portfolio_signals
                        (signal_id, portfolio_id, stock_symbol, date, signal_type,
                         suggested_allocation, stop_loss, confidence_score, subscription_level_required)
                        VALUES (:signal_id, :portfolio_id, :symbol, :date, :signal_type,
                                :allocation, :stop_loss, :confidence, :subscription_level)
                    """
                    
                    params = {
                        "signal_id": signal_id,
                        "portfolio_id": portfolio_id,
                        "symbol": symbol,
                        "date": date.today(),
                        "signal_type": signal['signal_type'],
                        "allocation": signal.get('suggested_allocation'),
                        "stop_loss": signal.get('stop_loss'),
                        "confidence": signal.get('confidence_score', 0.5),
                        "subscription_level": signal.get('subscription_level_required', 'basic')
                    }
                    
                    db.execute_update(query, params)
                    signals_generated += 1
            
            self.log_info(f"✅ Generated {signals_generated} signals for portfolio {portfolio_id}",
                         context={'portfolio_id': portfolio_id, 'signals_generated': signals_generated})
            return signals_generated
            
        except DatabaseError as e:
            self.log_error(f"Database error generating portfolio signals", e,
                         context={'portfolio_id': portfolio_id})
            raise
        except Exception as e:
            self.log_error(f"Unexpected error generating portfolio signals", e,
                         context={'portfolio_id': portfolio_id})
            raise DatabaseError(f"Failed to generate portfolio signals: {str(e)}", 
                              details={'portfolio_id': portfolio_id}) from e
    
    def _generate_signal_for_holding(
        self,
        holding: Dict[str, Any],
        indicators: Dict[str, Any],
        subscription_level: str,
        strategy_name: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Generate signal for a specific holding
        
        Returns:
            Signal dictionary or None
        """
        symbol = holding['stock_symbol']
        position_type = holding['position_type']
        strategy_tag = holding.get('strategy_tag')
        
        # Use strategy system if strategy_name is provided
        if strategy_name:
            # Convert indicators to format expected by strategies
            strategy_indicators = {
                'price': indicators.get('sma50') or 100,  # Use SMA50 as proxy for price
                'ema20': indicators.get('ema20'),
                'ema50': indicators.get('ema50'),
                'sma200': indicators.get('sma200'),
                'macd_line': indicators.get('macd'),
                'macd_signal': indicators.get('macd_signal'),
                'macd_histogram': indicators.get('macd_histogram'),
                'rsi': indicators.get('rsi'),
                'long_term_trend': indicators.get('long_term_trend'),
                'medium_term_trend': indicators.get('medium_term_trend'),
            }
            
            # Execute strategy
            strategy_result = self.strategy_service.execute_strategy(
                strategy_name,
                strategy_indicators,
                context={'symbol': symbol, 'position_type': position_type}
            )
            signal = strategy_result.signal
            confidence_score = strategy_result.confidence
        else:
            # Fallback to old method
            signal = indicators.get('signal', 'hold')
            confidence_score = self._calculate_confidence(indicators)
        
        # Determine signal type based on position and strategy
        signal_type = signal
        
        # Strategy-specific signals
        if strategy_tag == 'covered_call' and signal == 'hold':
            signal_type = 'covered_call'
        elif strategy_tag == 'protective_put' and signal == 'sell':
            signal_type = 'protective_put'
        
        # Ensure confidence_score is set
        if confidence_score is None:
            confidence_score = self._calculate_confidence(indicators)
        
        # Allocation percentage (0-100)
        if signal == 'buy':
            suggested_allocation = min(confidence_score * 100, 20)  # Max 20% per position
        elif signal == 'sell':
            suggested_allocation = 0  # Exit position
        else:
            suggested_allocation = None
        
        # Calculate stop loss
        stop_loss = None
        if indicators.get('atr') and indicators.get('close'):
            atr = indicators['atr']
            current_price = indicators.get('close') or indicators.get('sma50', 100)
            if position_type == 'long':
                stop_loss = current_price - (atr * 2)
            elif position_type == 'short':
                stop_loss = current_price + (atr * 2)
        
        # Determine subscription level required
        subscription_level_required = 'basic'
        if indicators.get('momentum_score') or indicators.get('pullback_zone_lower'):
            subscription_level_required = 'pro'
        if strategy_tag in ['covered_call', 'protective_put']:
            subscription_level_required = 'elite'
        
        return {
            'signal_type': signal_type,
            'suggested_allocation': suggested_allocation,
            'stop_loss': stop_loss,
            'confidence_score': confidence_score,
            'subscription_level_required': subscription_level_required
        }
    
    def _calculate_confidence(self, indicators: Dict[str, Any]) -> float:
        """
        Calculate confidence score (0-1) based on indicator alignment
        
        Higher confidence when:
        - Multiple indicators align
        - Strong trend confirmation
        - Good momentum
        """
        confidence = 0.5  # Base confidence
        
        # Trend alignment
        if indicators.get('long_term_trend') == 'bullish':
            confidence += 0.15
        if indicators.get('medium_term_trend') == 'bullish':
            confidence += 0.10
        
        # Signal strength
        signal = indicators.get('signal', 'hold')
        if signal == 'buy':
            confidence += 0.15
        elif signal == 'sell':
            confidence += 0.10
        
        # Momentum
        momentum = indicators.get('momentum_score', 50)
        if momentum > 60:
            confidence += 0.10
        elif momentum < 40:
            confidence -= 0.10
        
        # Clamp to 0-1
        return max(0.0, min(1.0, confidence))

