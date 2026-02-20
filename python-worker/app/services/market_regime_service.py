"""
Market Regime Detection Service
Implements institutional-grade market regime detection using SPY, VIX, and trend analysis
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from sqlalchemy import text
from app.database import db
from app.observability.logging import get_logger

logger = get_logger(__name__)

class MarketRegime(Enum):
    STRONG_BULL = "strong_bull"      # SPY > 200MA + slope > 0 + VIX < 20
    MILD_BULL = "mild_bull"          # SPY > 200MA + slope > 0 + VIX 20-25
    SIDEWAYS = "sideways"            # SPY ± 5% of 200MA + VIX 20-30
    MILD_BEAR = "mild_bear"          # SPY < 200MA + slope < 0 + VIX 25-35
    STRONG_BEAR = "strong_bear"      # SPY < 200MA + slope < 0 + VIX > 35

@dataclass
class MarketRegimeData:
    regime: MarketRegime
    spy_vs_ma200: float  # % above/below 200MA
    ma200_slope: float   # 200MA trend direction
    vix_level: float     # Current VIX
    confidence: float    # Regime detection confidence
    updated_at: datetime

class MarketRegimeService:
    """Service for detecting and analyzing market regimes"""
    
    def __init__(self):
        self.cache_ttl = timedelta(hours=1)  # Cache for 1 hour
        self._cached_regime: Optional[MarketRegimeData] = None
        self._cache_timestamp: Optional[datetime] = None
    
    def detect_market_regime(self) -> MarketRegimeData:
        """Detect current market regime using SPY, VIX, and trend analysis"""
        
        # Check cache first
        if (self._cached_regime and 
            self._cache_timestamp and 
            datetime.now() - self._cache_timestamp < self.cache_ttl):
            return self._cached_regime
        
        try:
            # Get SPY data
            spy_data = self._get_spy_analysis()
            
            # Get VIX data
            vix_data = self._get_vix_data()
            
            # Classify regime
            regime = self._classify_regime(spy_data, vix_data)
            
            # Calculate confidence
            confidence = self._calculate_confidence(spy_data, vix_data)
            
            # Create regime data
            regime_data = MarketRegimeData(
                regime=regime,
                spy_vs_ma200=spy_data['vs_ma200'],
                ma200_slope=spy_data['ma200_slope'],
                vix_level=vix_data['level'],
                confidence=confidence,
                updated_at=datetime.now()
            )
            
            # Cache result
            self._cached_regime = regime_data
            self._cache_timestamp = datetime.now()
            
            logger.info(f"Market regime detected: {regime.value} (confidence: {confidence:.2f})")
            
            return regime_data
            
        except Exception as e:
            logger.error(f"Error detecting market regime: {e}")
            # Return default regime on error
            return MarketRegimeData(
                regime=MarketRegime.SIDEWAYS,
                spy_vs_ma200=0.0,
                ma200_slope=0.0,
                vix_level=25.0,
                confidence=0.0,
                updated_at=datetime.now()
            )
    
    def _get_spy_analysis(self) -> Dict[str, float]:
        """Get SPY analysis including 200MA position and slope"""
        try:
            with db.get_session() as session:
                # Get latest SPY data with indicators
                query = """
                SELECT 
                    r.date,
                    r.close,
                    i.sma_200,
                    i.ema_20,
                    i.sma_50
                FROM raw_market_data_daily r
                JOIN indicators_daily i ON r.symbol = i.symbol AND r.date = i.date
                WHERE r.symbol = 'SPY'
                ORDER BY r.date DESC
                LIMIT 60
                """
                
                result = session.execute(text(query))
                rows = result.fetchall()
                
                if not rows:
                    logger.warning("No SPY data found")
                    return {'vs_ma200': 0.0, 'ma200_slope': 0.0}
                
                # Get latest data
                latest = rows[0]
                current_price = latest[1]
                ma200 = latest[2]
                
                # Calculate % above/below 200MA
                if ma200 and ma200 > 0:
                    vs_ma200 = (current_price / ma200) - 1
                else:
                    vs_ma200 = 0.0
                
                # Calculate 200MA slope (using linear regression on last 30 days)
                ma200_slope = self._calculate_ma200_slope(rows)
                
                return {
                    'vs_ma200': vs_ma200,
                    'ma200_slope': ma200_slope,
                    'current_price': current_price,
                    'ma200': ma200
                }
                
        except Exception as e:
            logger.error(f"Error getting SPY analysis: {e}")
            return {'vs_ma200': 0.0, 'ma200_slope': 0.0}
    
    def _calculate_ma200_slope(self, rows: list) -> float:
        """Calculate 200MA slope using linear regression"""
        try:
            if len(rows) < 30:
                return 0.0
            
            # Get last 30 days of MA200 values
            recent_rows = rows[:30]
            ma200_values = []
            
            for row in recent_rows:
                ma200 = row[2]  # sma_200
                if ma200:
                    ma200_values.append(ma200)
            
            if len(ma200_values) < 10:
                return 0.0
            
            # Simple linear regression to calculate slope
            n = len(ma200_values)
            x = list(range(n))  # Time indices
            
            # Calculate slope using least squares
            x_mean = sum(x) / n
            y_mean = sum(ma200_values) / n
            
            numerator = sum((x[i] - x_mean) * (ma200_values[i] - y_mean) for i in range(n))
            denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
            
            if denominator == 0:
                return 0.0
            
            slope = numerator / denominator
            
            # Normalize slope as percentage
            if ma200_values[-1] > 0:
                slope_pct = (slope / ma200_values[-1]) * 100
            else:
                slope_pct = 0.0
            
            return slope_pct
            
        except Exception as e:
            logger.error(f"Error calculating MA200 slope: {e}")
            return 0.0
    
    def _get_vix_data(self) -> Dict[str, float]:
        """Get current VIX level"""
        try:
            with db.get_session() as session:
                # Get latest VIX data
                query = """
                SELECT close
                FROM raw_market_data_daily
                WHERE symbol = 'VIX'
                ORDER BY date DESC
                LIMIT 1
                """
                
                result = session.execute(text(query))
                row = result.fetchone()
                
                if row and row[0]:
                    vix_level = float(row[0])
                else:
                    # Fallback to default VIX
                    vix_level = 20.0
                    logger.warning("No VIX data found, using default")
                
                return {'level': vix_level}
                
        except Exception as e:
            logger.error(f"Error getting VIX data: {e}")
            return {'level': 20.0}
    
    def _classify_regime(self, spy_data: Dict[str, float], vix_data: Dict[str, float]) -> MarketRegime:
        """Classify market regime based on SPY and VIX data"""
        
        spy_vs_ma200 = spy_data['vs_ma200']
        ma200_slope = spy_data['ma200_slope']
        vix_level = vix_data['level']
        
        # Strong Bull: SPY > 5% above 200MA + positive slope + VIX < 20
        if (spy_vs_ma200 > 0.05 and 
            ma200_slope > 0.1 and 
            vix_level < 20):
            return MarketRegime.STRONG_BULL
        
        # Mild Bull: SPY > 2% above 200MA + positive slope + VIX < 25
        elif (spy_vs_ma200 > 0.02 and 
              ma200_slope > 0.05 and 
              vix_level < 25):
            return MarketRegime.MILD_BULL
        
        # Strong Bear: SPY > 5% below 200MA + negative slope + VIX > 35
        elif (spy_vs_ma200 < -0.05 and 
              ma200_slope < -0.1 and 
              vix_level > 35):
            return MarketRegime.STRONG_BEAR
        
        # Mild Bear: SPY > 2% below 200MA + negative slope + VIX > 25
        elif (spy_vs_ma200 < -0.02 and 
              ma200_slope < -0.05 and 
              vix_level > 25):
            return MarketRegime.MILD_BEAR
        
        # Sideways: Everything else
        else:
            return MarketRegime.SIDEWAYS
    
    def _calculate_confidence(self, spy_data: Dict[str, float], vix_data: Dict[str, float]) -> float:
        """Calculate confidence in regime detection"""
        
        confidence = 0.5  # Base confidence
        
        # Add confidence based on how extreme the values are
        spy_vs_ma200 = abs(spy_data['vs_ma200'])
        ma200_slope = abs(spy_data['ma200_slope'])
        vix_level = vix_data['level']
        
        # Strong SPY position adds confidence
        if spy_vs_ma200 > 0.1:
            confidence += 0.2
        elif spy_vs_ma200 > 0.05:
            confidence += 0.1
        
        # Strong slope adds confidence
        if ma200_slope > 0.2:
            confidence += 0.2
        elif ma200_slope > 0.1:
            confidence += 0.1
        
        # Extreme VIX adds confidence
        if vix_level > 30 or vix_level < 15:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def get_regime_description(self, regime: MarketRegime) -> str:
        """Get human-readable description of market regime"""
        descriptions = {
            MarketRegime.STRONG_BULL: "Strong bull market - SPY well above 200MA with positive slope and low VIX",
            MarketRegime.MILD_BULL: "Mild bull market - SPY above 200MA with positive slope and moderate VIX",
            MarketRegime.SIDEWAYS: "Sideways/choppy market - SPY around 200MA with neutral VIX",
            MarketRegime.MILD_BEAR: "Mild bear market - SPY below 200MA with negative slope and elevated VIX",
            MarketRegime.STRONG_BEAR: "Strong bear market - SPY well below 200MA with negative slope and high VIX"
        }
        return descriptions.get(regime, "Unknown regime")
    
    def get_trading_implications(self, regime: MarketRegime) -> Dict[str, str]:
        """Get trading implications for each regime"""
        implications = {
            MarketRegime.STRONG_BULL: {
                "strategy": "Momentum and trend following",
                "risk_tolerance": "High",
                "position_sizing": "Full positions",
                "entry_criteria": "Allow higher RSI entries (45+)",
                "exit_criteria": "Trail stops, take partial profits"
            },
            MarketRegime.MILD_BULL: {
                "strategy": "Balanced momentum and value",
                "risk_tolerance": "Moderate-High",
                "position_sizing": "75% positions",
                "entry_criteria": "Standard RSI (35+)",
                "exit_criteria": "Standard stops and targets"
            },
            MarketRegime.SIDEWAYS: {
                "strategy": "Mean reversion and range trading",
                "risk_tolerance": "Moderate",
                "position_sizing": "50% positions",
                "entry_criteria": "Oversold/overbought extremes",
                "exit_criteria": "Quick exits on range boundaries"
            },
            MarketRegime.MILD_BEAR: {
                "strategy": "Capital preservation and selective longs",
                "risk_tolerance": "Low-Moderate",
                "position_sizing": "25% positions",
                "entry_criteria": "Deep oversold only (RSI < 30)",
                "exit_criteria": "Tight stops, quick profits"
            },
            MarketRegime.STRONG_BEAR: {
                "strategy": "Capital preservation only",
                "risk_tolerance": "Low",
                "position_sizing": "Cash or minimal positions",
                "entry_criteria": "Extreme oversold only (RSI < 25)",
                "exit_criteria": "Very tight stops, immediate profits"
            }
        }
        return implications.get(regime, {})
