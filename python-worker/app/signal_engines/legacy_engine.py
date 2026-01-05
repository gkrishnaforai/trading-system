"""
Legacy Signal Engine
Wrapper around existing StockInsightsService logic
"""

from typing import Dict, Any
import pandas as pd

from .base import BaseSignalEngine, SignalResult, SignalType, SignalEngineError
from app.services.stock_insights_service import StockInsightsService
from app.observability.logging import get_logger

logger = get_logger(__name__)


class LegacyEngine(BaseSignalEngine):
    """
    Legacy engine that wraps existing StockInsightsService logic
    Preserves current behavior while fitting into new architecture
    """
    
    def __init__(self):
        super().__init__()
        self.engine_name = "legacy"
        self.engine_version = "1.0.0"
        self.insights_service = StockInsightsService()
    
    def generate_signal(
        self,
        symbol: str,
        market_data: pd.DataFrame,
        indicators: Dict[str, Any],
        fundamentals: Dict[str, Any],
        market_context
    ) -> SignalResult:
        """
        Generate signal using existing StockInsightsService logic
        
        Args:
            symbol: Stock symbol
            market_data: Historical price data
            indicators: Technical indicators
            fundamentals: Fundamental data
            market_context: Market regime context
            
        Returns:
            SignalResult with legacy-based recommendation
        """
        try:
            # Validate inputs
            self.validate_inputs(symbol, market_data, indicators, fundamentals, market_context)
            
            # Use existing insights service
            insights = self.insights_service.get_stock_insights(symbol, run_all_strategies=False)
            
            if not insights:
                raise SignalEngineError("No insights generated", self.engine_name, symbol)
            
            # Extract signal from overall recommendation
            overall_rec = insights.get('overall_recommendation', {})
            signal_str = overall_rec.get('signal', 'HOLD').upper()
            
            # Map to signal type
            signal_map = {
                'BUY': SignalType.BUY,
                'SELL': SignalType.SELL,
                'HOLD': SignalType.HOLD
            }
            signal = signal_map.get(signal_str, SignalType.HOLD)
            
            # Extract confidence (use default if not available)
            confidence = overall_rec.get('confidence', 0.5)
            
            # Generate reasoning from available data
            reasoning = []
            
            # Add technical reasoning
            if indicators:
                rsi = indicators.get('rsi')
                if rsi:
                    if rsi > 70:
                        reasoning.append(f"RSI overbought ({rsi:.1f})")
                    elif rsi < 30:
                        reasoning.append(f"RSI oversold ({rsi:.1f})")
                    else:
                        reasoning.append(f"RSI neutral ({rsi:.1f})")
                
                # Add moving average analysis
                sma50 = indicators.get('sma50')
                sma200 = indicators.get('sma200')
                if sma50 and sma200:
                    if sma50 > sma200:
                        reasoning.append(f"Bullish trend (SMA50 > SMA200)")
                    else:
                        reasoning.append(f"Bearish trend (SMA50 < SMA200)")
            
            # Add fundamental reasoning
            if fundamentals:
                pe_ratio = fundamentals.get('pe_ratio')
                if pe_ratio:
                    if 10 <= pe_ratio <= 25:
                        reasoning.append(f"Reasonable valuation (P/E: {pe_ratio:.1f})")
                    elif pe_ratio > 35:
                        reasoning.append(f"Expensive valuation (P/E: {pe_ratio:.1f})")
            
            # Add market context
            reasoning.append(f"Market regime: {market_context.regime.value}")
            
            # Set position size based on confidence and signal
            if signal == SignalType.BUY:
                position_size = min(0.15, confidence * 0.2)  # Max 15%
            elif signal == SignalType.SELL:
                position_size = -min(0.15, confidence * 0.2)  # Short position
            else:
                position_size = 0.0
            
            # Get current price for entry range
            current_price = market_data.iloc[-1]['close'] if len(market_data) > 0 else None
            entry_range = None
            stop_loss = None
            
            if current_price:
                # Simple entry range (±1% around current price)
                entry_range = (current_price * 0.99, current_price * 1.01)
                # Simple stop loss (5% below entry)
                stop_loss = current_price * 0.95
            
            return self._create_signal_result(
                symbol=symbol,
                signal=signal,
                confidence=confidence,
                reasoning=reasoning,
                position_size_pct=position_size,
                entry_price_range=entry_range,
                stop_loss=stop_loss,
                timeframe='position',
                metadata={
                    'source': 'legacy_insights',
                    'original_signal': signal_str,
                    'market_regime': market_context.regime.value
                }
            )
            
        except Exception as e:
            if isinstance(e, SignalEngineError):
                raise
            raise SignalEngineError(f"Failed to generate legacy signal: {str(e)}", self.engine_name, symbol)
    
    def get_engine_metadata(self) -> Dict[str, Any]:
        """Return engine metadata"""
        return {
            'name': self.engine_name,
            'display_name': 'Legacy Engine',
            'description': 'Wraps existing StockInsightsService logic with technical and fundamental analysis',
            'tier': 'BASIC',
            'timeframe': 'position',
            'version': self.engine_version,
            'features': [
                'Technical momentum (RSI, MACD, EMAs)',
                'Basic fundamental checks (P/E, debt)',
                'Trend strength analysis',
                'Market regime awareness'
            ]
        }
    
    def get_required_indicators(self) -> list:
        """Return required indicators for legacy engine"""
        return ['price', 'volume', 'rsi', 'macd', 'sma50', 'sma200', 'ema20']
    
    def get_required_fundamentals(self) -> list:
        """Return required fundamentals for legacy engine"""
        return ['sector', 'market_cap', 'pe_ratio']
