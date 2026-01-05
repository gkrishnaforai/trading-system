"""
Market Context Service
Detects market regime and provides market context for signal engines
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from app.signal_engines.base import MarketContext, MarketRegime
from app.repositories.macro_data_repository import MacroDataRepository
from app.observability.logging import get_logger

logger = get_logger(__name__)


class MarketContextService:
    """Service for detecting market regime and providing context"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
    
    def get_market_context(self) -> MarketContext:
        """
        Get current market context with regime detection
        
        Returns:
            MarketContext with current market state
        """
        try:
            # Get macro data
            macro_data = self._get_latest_macro_data()
            
            # Detect market regime
            regime, regime_confidence = self._detect_market_regime(macro_data)
            
            # Get NASDAQ trend
            nasdaq_trend = self._analyze_nasdaq_trend(macro_data)
            
            # Get sector rotation data
            sector_rotation = self._get_sector_rotation()
            
            # Get breadth data
            breadth = macro_data.get('sp500_above_50d_pct', 0.0)
            
            # Get yield curve spread
            yield_curve_spread = macro_data.get('yield_curve_spread', 0.0)
            
            return MarketContext(
                regime=regime,
                regime_confidence=regime_confidence,
                vix=macro_data.get('vix_close', 20.0),
                nasdaq_trend=nasdaq_trend,
                sector_rotation=sector_rotation,
                breadth=breadth,
                yield_curve_spread=yield_curve_spread,
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get market context: {str(e)}")
            # Return default context on error
            return MarketContext(
                regime=MarketRegime.HIGH_VOL_CHOP,
                regime_confidence=0.5,
                vix=20.0,
                nasdaq_trend="neutral",
                sector_rotation={},
                breadth=0.5,
                yield_curve_spread=0.0,
                timestamp=datetime.utcnow()
            )
    
    def _get_latest_macro_data(self) -> Dict[str, Any]:
        """Get latest macro data from database"""
        try:
            # Get most recent macro data
            macro_data = MacroDataRepository.fetch_latest()
            
            if not macro_data:
                # Return defaults if no data available
                return {
                    'vix_close': 20.0,
                    'nasdaq_close': 15000.0,
                    'nasdaq_sma50': 14500.0,
                    'nasdaq_sma200': 14000.0,
                    'sp500_above_50d_pct': 0.5,
                    'yield_curve_spread': 0.5,
                    'fed_funds_rate': 3.0
                }
            
            return macro_data
            
        except Exception as e:
            self.logger.error(f"Failed to get macro data: {str(e)}")
            return {}
    
    def _detect_market_regime(self, macro_data: Dict[str, Any]) -> tuple:
        """
        Detect market regime using multiple factors
        
        Returns:
            Tuple of (MarketRegime, confidence)
        """
        try:
            score = 0.0
            confidence_factors = []
            
            # Factor 1: NASDAQ trend (40% weight)
            nasdaq_score, nasdaq_confidence = self._score_nasdaq_trend(macro_data)
            score += nasdaq_score * 0.4
            confidence_factors.append(nasdaq_confidence)
            
            # Factor 2: VIX regime (30% weight)
            vix_score, vix_confidence = self._score_vix_regime(macro_data)
            score += vix_score * 0.3
            confidence_factors.append(vix_confidence)
            
            # Factor 3: Breadth (20% weight)
            breadth_score, breadth_confidence = self._score_breadth(macro_data)
            score += breadth_score * 0.2
            confidence_factors.append(breadth_confidence)
            
            # Factor 4: Yield curve (10% weight)
            yield_score, yield_confidence = self._score_yield_curve(macro_data)
            score += yield_score * 0.1
            confidence_factors.append(yield_confidence)
            
            # Determine regime from score
            if score > 1.5:
                regime = MarketRegime.BULL
            elif score < -1.5:
                regime = MarketRegime.BEAR
            elif abs(score) <= 0.5:
                regime = MarketRegime.HIGH_VOL_CHOP
            else:
                regime = MarketRegime.HIGH_VOL_CHOP  # Neutral territory
            
            # Special NO_TRADE conditions
            vix = macro_data.get('vix_close', 20.0)
            breadth = macro_data.get('sp500_above_50d_pct', 0.5)
            
            if vix > 40 or breadth < 0.2:
                regime = MarketRegime.NO_TRADE
                confidence = 0.9
            else:
                confidence = np.mean(confidence_factors)
            
            return regime, confidence
            
        except Exception as e:
            self.logger.error(f"Failed to detect market regime: {str(e)}")
            return MarketRegime.HIGH_VOL_CHOP, 0.5
    
    def _score_nasdaq_trend(self, macro_data: Dict[str, Any]) -> tuple:
        """Score NASDAQ trend for regime detection"""
        try:
            nasdaq_close = macro_data.get('nasdaq_close')
            nasdaq_sma50 = macro_data.get('nasdaq_sma50')
            nasdaq_sma200 = macro_data.get('nasdaq_sma200')
            
            if not all([nasdaq_close, nasdaq_sma50, nasdaq_sma200]):
                return 0.0, 0.5
            
            score = 0.0
            confidence = 0.8
            
            # Price vs moving averages
            if nasdaq_close > nasdaq_sma200 > nasdaq_sma50:
                score += 2.0  # Strong bull
            elif nasdaq_close > nasdaq_sma50 > nasdaq_sma200:
                score += 1.0  # Bull
            elif nasdaq_close < nasdaq_sma50 < nasdaq_sma200:
                score -= 1.0  # Bear
            elif nasdaq_close < nasdaq_sma200 < nasdaq_sma50:
                score -= 2.0  # Strong bear
            else:
                score = 0.0  # Choppy/neutral
                confidence = 0.5
            
            return score, confidence
            
        except Exception as e:
            self.logger.error(f"Failed to score NASDAQ trend: {str(e)}")
            return 0.0, 0.5
    
    def _score_vix_regime(self, macro_data: Dict[str, Any]) -> tuple:
        """Score VIX regime for market detection"""
        try:
            vix = macro_data.get('vix_close', 20.0)
            
            if vix < 15:
                return 1.0, 0.9  # Low vol = bullish
            elif vix < 20:
                return 0.5, 0.8  # Normal = slightly bullish
            elif vix < 30:
                return -0.5, 0.8  # Elevated = slightly bearish
            elif vix < 40:
                return -1.0, 0.9  # High = bearish
            else:
                return -2.0, 0.95  # Panic = strong bearish
                
        except Exception as e:
            self.logger.error(f"Failed to score VIX regime: {str(e)}")
            return 0.0, 0.5
    
    def _score_breadth(self, macro_data: Dict[str, Any]) -> tuple:
        """Score market breadth for regime detection"""
        try:
            breadth = macro_data.get('sp500_above_50d_pct', 0.5)
            
            if breadth > 0.7:
                return 1.0, 0.8  # Strong breadth = bullish
            elif breadth > 0.5:
                return 0.5, 0.7  # Moderate breadth = slightly bullish
            elif breadth > 0.3:
                return -0.5, 0.7  # Weak breadth = slightly bearish
            else:
                return -1.0, 0.8  # Poor breadth = bearish
                
        except Exception as e:
            self.logger.error(f"Failed to score breadth: {str(e)}")
            return 0.0, 0.5
    
    def _score_yield_curve(self, macro_data: Dict[str, Any]) -> tuple:
        """Score yield curve for regime detection"""
        try:
            spread = macro_data.get('yield_curve_spread', 0.0)
            
            if spread > 1.0:  # Normal curve > 1%
                return 0.5, 0.7  # Slightly bullish
            elif spread > 0.0:  # Positive but flat
                return 0.0, 0.6  # Neutral
            elif spread > -0.5:  # Slight inversion
                return -0.5, 0.7  # Slightly bearish
            else:  # Significant inversion
                return -1.0, 0.8  # Bearish (recession risk)
                
        except Exception as e:
            self.logger.error(f"Failed to score yield curve: {str(e)}")
            return 0.0, 0.5
    
    def _analyze_nasdaq_trend(self, macro_data: Dict[str, Any]) -> str:
        """Analyze NASDAQ trend direction"""
        try:
            nasdaq_close = macro_data.get('nasdaq_close')
            nasdaq_sma50 = macro_data.get('nasdaq_sma50')
            nasdaq_sma200 = macro_data.get('nasdaq_sma200')
            
            if not all([nasdaq_close, nasdaq_sma50, nasdaq_sma200]):
                return "neutral"
            
            if nasdaq_close > nasdaq_sma50 > nasdaq_sma200:
                return "bullish"
            elif nasdaq_close < nasdaq_sma50 < nasdaq_sma200:
                return "bearish"
            else:
                return "neutral"
                
        except Exception as e:
            self.logger.error(f"Failed to analyze NASDAQ trend: {str(e)}")
            return "neutral"
    
    def _get_sector_rotation(self) -> Dict[str, float]:
        """
        Get sector rotation momentum scores
        
        Returns:
            Dictionary mapping sector names to momentum scores (-1 to 1)
        """
        try:
            # This would typically involve analyzing sector ETF performance
            # For now, return a simplified implementation
            return {
                'technology': 0.3,
                'healthcare': 0.1,
                'finance': -0.1,
                'energy': -0.2,
                'consumer discretionary': 0.2,
                'consumer staples': -0.1,
                'industrial': 0.0,
                'utilities': -0.3,
                'real estate': -0.2,
                'materials': -0.1
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get sector rotation: {str(e)}")
            return {}
    
    def update_macro_data(self, data: Dict[str, Any]) -> bool:
        """
        Update macro data in database
        
        Args:
            data: Dictionary with macro data fields
            
        Returns:
            True if successful
        """
        try:
            # Add timestamp
            data['data_date'] = datetime.utcnow().date()
            
            # Save to database
            MacroDataRepository.save_macro_data(data)
            success = True
            
            if success:
                self.logger.info("Macro data updated successfully")
            else:
                self.logger.error("Failed to update macro data")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to update macro data: {str(e)}")
            return False
