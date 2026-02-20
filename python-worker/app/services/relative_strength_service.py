"""
Relative Strength Analysis Service
Implements relative strength analysis vs SPY with momentum consistency checking
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import logging

from sqlalchemy import text
from app.database import db
from app.observability.logging import get_logger

logger = get_logger(__name__)

class RelativeStrengthTier(Enum):
    STRONG_OUTPERFORMER = "strong_outperformer"    # > 10% vs SPY
    MODERATE_OUTPERFORMER = "moderate_outperformer"  # 5-10% vs SPY
    WEAK_OUTPERFORMER = "weak_outperformer"        # 0-5% vs SPY
    WEAK_UNDERPERFORMER = "weak_underperformer"    # -5% to 0% vs SPY
    STRONG_UNDERPERFORMER = "strong_underperformer"  # < -5% vs SPY

@dataclass
class RelativeStrengthData:
    tier: RelativeStrengthTier
    stock_return_90d: float
    spy_return_90d: float
    relative_strength: float  # stock - spy
    momentum_consistency: float  # 0-1, how consistent the outperformance/underperformance is
    updated_at: datetime

class RelativeStrengthService:
    """Service for analyzing relative strength vs SPY"""
    
    def __init__(self):
        self.cache_ttl = timedelta(hours=6)  # Cache for 6 hours
        self._cache: Dict[str, Tuple[RelativeStrengthData, datetime]] = {}
    
    def analyze_relative_strength(self, symbol: str) -> RelativeStrengthData:
        """Analyze relative strength of a symbol vs SPY"""
        
        # Check cache first
        if symbol in self._cache:
            cached_data, cache_time = self._cache[symbol]
            if datetime.now() - cache_time < self.cache_ttl:
                return cached_data
        
        try:
            # Calculate 90-day returns
            stock_return = self._calculate_90d_return(symbol)
            spy_return = self._calculate_90d_return('SPY')
            
            # Calculate relative strength
            relative_strength = stock_return - spy_return
            
            # Classify tier
            tier = self._classify_strength_tier(relative_strength)
            
            # Calculate momentum consistency
            consistency = self._calculate_momentum_consistency(symbol)
            
            # Create relative strength data
            rs_data = RelativeStrengthData(
                tier=tier,
                stock_return_90d=stock_return,
                spy_return_90d=spy_return,
                relative_strength=relative_strength,
                momentum_consistency=consistency,
                updated_at=datetime.now()
            )
            
            # Cache result
            self._cache[symbol] = (rs_data, datetime.now())
            
            logger.debug(f"Relative strength for {symbol}: {tier.value} (RS: {relative_strength:.2%}, consistency: {consistency:.2f})")
            
            return rs_data
            
        except Exception as e:
            logger.error(f"Error analyzing relative strength for {symbol}: {e}")
            # Return default data on error
            return RelativeStrengthData(
                tier=RelativeStrengthTier.WEAK_OUTPERFORMER,
                stock_return_90d=0.0,
                spy_return_90d=0.0,
                relative_strength=0.0,
                momentum_consistency=0.5,
                updated_at=datetime.now()
            )
    
    def _calculate_90d_return(self, symbol: str) -> float:
        """Calculate 90-day return for a symbol"""
        try:
            with db.get_session() as session:
                # Get price 90 days ago and most recent price
                query = """
                SELECT close, date
                FROM raw_market_data_daily
                WHERE symbol = :symbol
                AND date >= CURRENT_DATE - INTERVAL '95 days'
                ORDER BY date DESC
                LIMIT 90
                """
                
                result = session.execute(text(query), {"symbol": symbol})
                rows = result.fetchall()
                
                if len(rows) < 2:
                    logger.warning(f"Insufficient data for 90-day return calculation for {symbol}")
                    return 0.0
                
                # Get most recent price (first row due to DESC order)
                current_price = rows[0][0]
                
                # Get price ~90 days ago (last row)
                old_price = rows[-1][0]
                
                if not current_price or not old_price or old_price <= 0:
                    return 0.0
                
                # Calculate return
                return_90d = (current_price - old_price) / old_price
                
                return return_90d
                
        except Exception as e:
            logger.error(f"Error calculating 90-day return for {symbol}: {e}")
            return 0.0
    
    def _classify_strength_tier(self, relative_strength: float) -> RelativeStrengthTier:
        """Classify relative strength into tiers"""
        if relative_strength > 0.10:
            return RelativeStrengthTier.STRONG_OUTPERFORMER
        elif relative_strength > 0.05:
            return RelativeStrengthTier.MODERATE_OUTPERFORMER
        elif relative_strength > 0:
            return RelativeStrengthTier.WEAK_OUTPERFORMER
        elif relative_strength > -0.05:
            return RelativeStrengthTier.WEAK_UNDERPERFORMER
        else:
            return RelativeStrengthTier.STRONG_UNDERPERFORMER
    
    def _calculate_momentum_consistency(self, symbol: str) -> float:
        """Calculate how consistent the relative strength momentum is"""
        try:
            with db.get_session() as session:
                # Get daily returns for last 30 days for both symbol and SPY
                query = """
                WITH symbol_returns AS (
                    SELECT 
                        date,
                        (close - LAG(close) OVER (ORDER BY date)) / LAG(close) OVER (ORDER BY date) as daily_return
                    FROM raw_market_data_daily
                    WHERE symbol = :symbol
                    AND date >= CURRENT_DATE - INTERVAL '35 days'
                ),
                spy_returns AS (
                    SELECT 
                        date,
                        (close - LAG(close) OVER (ORDER BY date)) / LAG(close) OVER (ORDER BY date) as daily_return
                    FROM raw_market_data_daily
                    WHERE symbol = 'SPY'
                    AND date >= CURRENT_DATE - INTERVAL '35 days'
                )
                SELECT 
                    s.date,
                    s.daily_return as symbol_return,
                    sp.daily_return as spy_return,
                    (s.daily_return - sp.daily_return) as relative_return
                FROM symbol_returns s
                JOIN spy_returns sp ON s.date = sp.date
                WHERE s.daily_return IS NOT NULL
                AND sp.daily_return IS NOT NULL
                ORDER BY s.date DESC
                LIMIT 30
                """
                
                result = session.execute(text(query), {"symbol": symbol})
                rows = result.fetchall()
                
                if len(rows) < 10:
                    return 0.5  # Default consistency
                
                # Calculate relative returns
                relative_returns = [row[3] for row in rows if row[3] is not None]
                
                if not relative_returns:
                    return 0.5
                
                # Calculate consistency as percentage of days with positive relative returns
                positive_days = sum(1 for ret in relative_returns if ret > 0)
                consistency = positive_days / len(relative_returns)
                
                # Adjust for volatility (more consistent = higher score)
                if consistency > 0.7:
                    return min(consistency + 0.1, 1.0)
                elif consistency < 0.3:
                    return max(consistency - 0.1, 0.0)
                
                return consistency
                
        except Exception as e:
            logger.error(f"Error calculating momentum consistency for {symbol}: {e}")
            return 0.5
    
    def get_tier_description(self, tier: RelativeStrengthTier) -> str:
        """Get human-readable description of relative strength tier"""
        descriptions = {
            RelativeStrengthTier.STRONG_OUTPERFORMER: "Strong outperformer - beating SPY by 10%+ over 90 days",
            RelativeStrengthTier.MODERATE_OUTPERFORMER: "Moderate outperformer - beating SPY by 5-10% over 90 days",
            RelativeStrengthTier.WEAK_OUTPERFORMER: "Weak outperformer - beating SPY by 0-5% over 90 days",
            RelativeStrengthTier.WEAK_UNDERPERFORMER: "Weak underperformer - trailing SPY by 0-5% over 90 days",
            RelativeStrengthTier.STRONG_UNDERPERFORMER: "Strong underperformer - trailing SPY by 5%+ over 90 days"
        }
        return descriptions.get(tier, "Unknown tier")
    
    def get_trading_implications(self, tier: RelativeStrengthTier) -> Dict[str, Any]:
        """Get trading implications for each relative strength tier"""
        implications = {
            RelativeStrengthTier.STRONG_OUTPERFORMER: {
                "signal_bias": "bullish",
                "confidence_boost": 0.3,
                "position_size_multiplier": 1.3,
                "entry_criteria": "Standard entries allowed",
                "risk_management": "Standard stops, wider targets"
            },
            RelativeStrengthTier.MODERATE_OUTPERFORMER: {
                "signal_bias": "bullish",
                "confidence_boost": 0.15,
                "position_size_multiplier": 1.1,
                "entry_criteria": "Standard entries allowed",
                "risk_management": "Standard stops and targets"
            },
            RelativeStrengthTier.WEAK_OUTPERFORMER: {
                "signal_bias": "neutral",
                "confidence_boost": 0.05,
                "position_size_multiplier": 1.0,
                "entry_criteria": "Standard entries allowed",
                "risk_management": "Standard stops and targets"
            },
            RelativeStrengthTier.WEAK_UNDERPERFORMER: {
                "signal_bias": "bearish",
                "confidence_boost": -0.1,
                "position_size_multiplier": 0.8,
                "entry_criteria": "Stricter entry criteria required",
                "risk_management": "Tighter stops, smaller targets"
            },
            RelativeStrengthTier.STRONG_UNDERPERFORMER: {
                "signal_bias": "bearish",
                "confidence_boost": -0.25,
                "position_size_multiplier": 0.6,
                "entry_criteria": "Block most long signals",
                "risk_management": "Very tight stops, quick profits"
            }
        }
        return implications.get(tier, {})
    
    def should_allow_long_signals(self, tier: RelativeStrengthTier) -> bool:
        """Determine if long signals should be allowed based on relative strength"""
        if tier in [RelativeStrengthTier.STRONG_UNDERPERFORMER, RelativeStrengthTier.WEAK_UNDERPERFORMER]:
            return False
        return True
    
    def get_relative_strength_filter_multiplier(self, tier: RelativeStrengthTier) -> float:
        """Get multiplier for buy signals based on relative strength"""
        multipliers = {
            RelativeStrengthTier.STRONG_OUTPERFORMER: 1.0,  # Full strength
            RelativeStrengthTier.MODERATE_OUTPERFORMER: 0.9,  # Slightly reduced
            RelativeStrengthTier.WEAK_OUTPERFORMER: 0.7,   # Moderately reduced
            RelativeStrengthTier.WEAK_UNDERPERFORMER: 0.3,  # Severely reduced
            RelativeStrengthTier.STRONG_UNDERPERFORMER: 0.1  # Almost blocked
        }
        return multipliers.get(tier, 0.5)
    
    def get_top_performers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top relative strength performers"""
        try:
            with db.get_session() as session:
                # Get recent stock list (could be enhanced with universe)
                query = """
                SELECT DISTINCT symbol
                FROM raw_market_data_daily
                WHERE symbol != 'SPY'
                AND date >= CURRENT_DATE - INTERVAL '7 days'
                LIMIT 100
                """
                
                result = session.execute(text(query))
                symbols = [row[0] for row in result.fetchall()]
                
                # Analyze relative strength for each symbol
                performers = []
                for symbol in symbols:
                    try:
                        rs_data = self.analyze_relative_strength(symbol)
                        if rs_data.relative_strength > 0.05:  # Only include outperformers
                            performers.append({
                                'symbol': symbol,
                                'relative_strength': rs_data.relative_strength,
                                'tier': rs_data.tier.value,
                                'consistency': rs_data.momentum_consistency,
                                'stock_return': rs_data.stock_return_90d,
                                'spy_return': rs_data.spy_return_90d
                            })
                    except Exception:
                        continue
                
                # Sort by relative strength
                performers.sort(key=lambda x: x['relative_strength'], reverse=True)
                
                return performers[:limit]
                
        except Exception as e:
            logger.error(f"Error getting top performers: {e}")
            return []
    
    def clear_cache(self, symbol: Optional[str] = None):
        """Clear relative strength cache"""
        if symbol:
            self._cache.pop(symbol, None)
        else:
            self._cache.clear()
        logger.info(f"Relative strength cache cleared for {'all symbols' if not symbol else symbol}")
