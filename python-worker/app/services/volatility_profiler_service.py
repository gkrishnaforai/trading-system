"""
Volatility Profiling Service
Implements dynamic volatility profiling based on ATR and historical percentiles
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging

from sqlalchemy import text
from app.database import db
from app.observability.logging import get_logger

logger = get_logger(__name__)

class VolatilityProfile(Enum):
    LOW = "low"      # ATR < 2%
    NORMAL = "normal" # ATR 2-4% 
    HIGH = "high"    # ATR > 4%

@dataclass
class VolatilityData:
    profile: VolatilityProfile
    atr_pct: float      # ATR as percentage of price
    atr_percentile: float  # Historical percentile (0-1)
    volatility_trend: str  # "rising", "falling", "stable"
    updated_at: datetime

class VolatilityProfilerService:
    """Service for analyzing and profiling volatility patterns"""
    
    def __init__(self):
        self.cache_ttl = timedelta(hours=4)  # Cache for 4 hours
        self._cache: Dict[str, Tuple[VolatilityData, datetime]] = {}
    
    def get_volatility_profile(self, symbol: str, market_data: Optional[Dict] = None) -> VolatilityData:
        """Get volatility profile for a symbol"""
        
        # Check cache first
        if symbol in self._cache:
            cached_data, cache_time = self._cache[symbol]
            if datetime.now() - cache_time < self.cache_ttl:
                return cached_data
        
        try:
            # Calculate ATR percentage
            atr_pct = self._calculate_atr_percentage(symbol, market_data)
            
            # Get historical percentile
            percentile = self._get_volatility_percentile(symbol, atr_pct)
            
            # Determine profile
            if atr_pct < 0.02:
                profile = VolatilityProfile.LOW
            elif atr_pct < 0.04:
                profile = VolatilityProfile.NORMAL
            else:
                profile = VolatilityProfile.HIGH
            
            # Determine volatility trend
            trend = self._get_volatility_trend(symbol)
            
            # Create volatility data
            vol_data = VolatilityData(
                profile=profile,
                atr_pct=atr_pct,
                atr_percentile=percentile,
                volatility_trend=trend,
                updated_at=datetime.now()
            )
            
            # Cache result
            self._cache[symbol] = (vol_data, datetime.now())
            
            logger.debug(f"Volatility profile for {symbol}: {profile.value} (ATR: {atr_pct:.2%}, percentile: {percentile:.2f})")
            
            return vol_data
            
        except Exception as e:
            logger.error(f"Error getting volatility profile for {symbol}: {e}")
            # Return default profile on error
            return VolatilityData(
                profile=VolatilityProfile.NORMAL,
                atr_pct=0.03,
                atr_percentile=0.5,
                volatility_trend="stable",
                updated_at=datetime.now()
            )
    
    def _calculate_atr_percentage(self, symbol: str, market_data: Optional[Dict] = None) -> float:
        """Calculate ATR as percentage of current price"""
        try:
            if market_data and 'atr' in market_data and 'close' in market_data:
                # Use provided market data
                atr = market_data['atr']
                current_price = market_data['close']
            else:
                # Fetch from database
                with db.get_session() as session:
                    query = """
                    SELECT 
                        r.close,
                        i.atr
                    FROM raw_market_data_daily r
                    JOIN indicators_daily i ON r.symbol = i.symbol AND r.date = i.date
                    WHERE r.symbol = :symbol
                    ORDER BY r.date DESC
                    LIMIT 1
                    """
                    
                    result = session.execute(text(query), {"symbol": symbol})
                    row = result.fetchone()
                    
                    if not row:
                        logger.warning(f"No ATR data found for {symbol}")
                        return 0.03  # Default 3%
                    
                    current_price = row[0]
                    atr = row[1]
            
            # Calculate ATR as percentage
            if atr and current_price and current_price > 0:
                atr_pct = atr / current_price
            else:
                atr_pct = 0.03  # Default 3%
            
            return atr_pct
            
        except Exception as e:
            logger.error(f"Error calculating ATR percentage for {symbol}: {e}")
            return 0.03
    
    def _get_volatility_percentile(self, symbol: str, current_atr_pct: float) -> float:
        """Calculate historical percentile of current ATR"""
        try:
            with db.get_session() as session:
                # Get last 252 trading days (1 year) of ATR data
                query = """
                SELECT i.atr, r.close
                FROM raw_market_data_daily r
                JOIN indicators_daily i ON r.symbol = i.symbol AND r.date = i.date
                WHERE r.symbol = :symbol
                AND r.date >= CURRENT_DATE - INTERVAL '1 year'
                ORDER BY r.date DESC
                """
                
                result = session.execute(text(query), {"symbol": symbol})
                rows = result.fetchall()
                
                if len(rows) < 30:  # Need at least 30 days
                    return 0.5  # Default to middle percentile
                
                # Calculate ATR percentages for historical data
                atr_percentages = []
                for row in rows:
                    atr = row[0]
                    close = row[1]
                    
                    if atr and close and close > 0:
                        atr_pct = atr / close
                        atr_percentages.append(atr_pct)
                
                if not atr_percentages:
                    return 0.5
                
                # Calculate percentile
                atr_percentages.sort()
                n = len(atr_percentages)
                
                # Find where current ATR falls in historical distribution
                for i, hist_atr in enumerate(atr_percentages):
                    if current_atr_pct <= hist_atr:
                        return i / n
                
                return 1.0  # Current ATR is higher than all historical values
                
        except Exception as e:
            logger.error(f"Error calculating volatility percentile for {symbol}: {e}")
            return 0.5
    
    def _get_volatility_trend(self, symbol: str) -> str:
        """Determine volatility trend over last 30 days"""
        try:
            with db.get_session() as session:
                # Get last 30 days of ATR data
                query = """
                SELECT i.atr, r.close, r.date
                FROM raw_market_data_daily r
                JOIN indicators_daily i ON r.symbol = i.symbol AND r.date = i.date
                WHERE r.symbol = :symbol
                AND r.date >= CURRENT_DATE - INTERVAL '30 days'
                ORDER BY r.date ASC
                """
                
                result = session.execute(text(query), {"symbol": symbol})
                rows = result.fetchall()
                
                if len(rows) < 10:
                    return "stable"
                
                # Calculate ATR percentages and trend
                atr_percentages = []
                for row in rows:
                    atr = row[0]
                    close = row[1]
                    
                    if atr and close and close > 0:
                        atr_pct = atr / close
                        atr_percentages.append(atr_pct)
                
                if len(atr_percentages) < 10:
                    return "stable"
                
                # Calculate trend using linear regression
                n = len(atr_percentages)
                x = list(range(n))
                
                x_mean = sum(x) / n
                y_mean = sum(atr_percentages) / n
                
                numerator = sum((x[i] - x_mean) * (atr_percentages[i] - y_mean) for i in range(n))
                denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
                
                if denominator == 0:
                    return "stable"
                
                slope = numerator / denominator
                
                # Determine trend based on slope magnitude
                if slope > 0.0001:  # Rising volatility
                    return "rising"
                elif slope < -0.0001:  # Falling volatility
                    return "falling"
                else:
                    return "stable"
                
        except Exception as e:
            logger.error(f"Error determining volatility trend for {symbol}: {e}")
            return "stable"
    
    def get_profile_description(self, profile: VolatilityProfile) -> str:
        """Get human-readable description of volatility profile"""
        descriptions = {
            VolatilityProfile.LOW: "Low volatility - ATR < 2%, stable price movements, lower risk",
            VolatilityProfile.NORMAL: "Normal volatility - ATR 2-4%, moderate price movements, balanced risk",
            VolatilityProfile.HIGH: "High volatility - ATR > 4%, large price movements, higher risk"
        }
        return descriptions.get(profile, "Unknown profile")
    
    def get_trading_adjustments(self, profile: VolatilityProfile) -> Dict[str, Any]:
        """Get trading adjustments for each volatility profile"""
        adjustments = {
            VolatilityProfile.LOW: {
                "stop_loss_multiplier": 0.8,  # Tighter stops
                "take_profit_multiplier": 0.9,  # Smaller targets
                "position_size_multiplier": 1.2,  # Larger positions
                "breakout_threshold_multiplier": 0.8,  # Lower threshold for breakouts
                "confidence_adjustment": 0.1  # Boost confidence
            },
            VolatilityProfile.NORMAL: {
                "stop_loss_multiplier": 1.0,  # Standard stops
                "take_profit_multiplier": 1.0,  # Standard targets
                "position_size_multiplier": 1.0,  # Standard positions
                "breakout_threshold_multiplier": 1.0,  # Standard threshold
                "confidence_adjustment": 0.0  # No adjustment
            },
            VolatilityProfile.HIGH: {
                "stop_loss_multiplier": 1.3,  # Wider stops
                "take_profit_multiplier": 1.2,  # Larger targets
                "position_size_multiplier": 0.7,  # Smaller positions
                "breakout_threshold_multiplier": 1.5,  # Higher threshold for breakouts
                "confidence_adjustment": -0.1  # Reduce confidence
            }
        }
        return adjustments.get(profile, {})
    
    def get_volatility_percentile_description(self, percentile: float) -> str:
        """Get description of volatility percentile"""
        if percentile >= 0.9:
            return "Extremely high (90th+ percentile)"
        elif percentile >= 0.75:
            return "High (75th-90th percentile)"
        elif percentile >= 0.6:
            return "Moderately high (60th-75th percentile)"
        elif percentile >= 0.4:
            return "Normal (40th-60th percentile)"
        elif percentile >= 0.25:
            return "Moderately low (25th-40th percentile)"
        else:
            return "Low (below 25th percentile)"
    
    def clear_cache(self, symbol: Optional[str] = None):
        """Clear volatility profile cache"""
        if symbol:
            self._cache.pop(symbol, None)
        else:
            self._cache.clear()
        logger.info(f"Volatility profile cache cleared for {'all symbols' if not symbol else symbol}")
