"""
Volatility Percentile Service
Fixes the critical volatility percentile calculation bug
Implements true rank percentile calculation, not min-max normalization
"""

import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from app.database import db
from app.observability.logging import get_logger

logger = get_logger(__name__)


class VolatilityPercentileService:
    """
    Calculates true volatility percentiles using rank-based method
    Fixes common bugs: wrong window size, min-max confusion, insufficient lookback
    """
    
    def __init__(self):
        self.logger = get_logger(__name__)
        # Standard lookback window for percentile calculation (1 year of trading days)
        self.default_lookback_days = 252
    
    def calculate_true_percentile(self, current_value: float, historical_values: List[float]) -> float:
        """
        Calculate true rank percentile, not min-max normalization
        This fixes the critical bug where 3% ATR was showing as 0th percentile
        
        Args:
            current_value: Current ATR value
            historical_values: Historical ATR values for comparison
            
        Returns:
            True percentile rank (0.0 to 1.0)
        """
        try:
            if not historical_values or current_value is None:
                return 0.5  # Default to 50th percentile
            
            # Remove None values and ensure we have data
            clean_values = [v for v in historical_values if v is not None and v > 0]
            
            if not clean_values:
                return 0.5
            
            # Calculate true rank percentile
            # Count how many historical values are less than current value
            lower_count = sum(1 for v in clean_values if v < current_value)
            percentile = lower_count / len(clean_values)
            
            # Ensure bounds
            percentile = np.clip(percentile, 0.0, 1.0)
            
            self.logger.debug(f"True percentile calculation: {current_value:.4f} -> {percentile:.3f} "
                            f"(based on {len(clean_values)} values)")
            
            return percentile
            
        except Exception as e:
            self.logger.error(f"Error calculating true percentile: {e}")
            return 0.5
    
    def get_historical_atr_values(self, symbol: str, lookback_days: Optional[int] = None) -> List[float]:
        """
        Get historical ATR values for a symbol from the database
        
        Args:
            symbol: Stock symbol
            lookback_days: Number of days to look back (default: 252)
            
        Returns:
            List of historical ATR values
        """
        try:
            lookback_days = lookback_days or self.default_lookback_days
            
            # Calculate start date
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days + 30)  # Extra buffer for weekends/holidays
            
            query = """
                SELECT date, atr
                FROM indicators_daily
                WHERE symbol = :symbol
                  AND date >= :start_date
                  AND date <= :end_date
                  AND atr IS NOT NULL
                  AND atr > 0
                  AND data_source = 'calculated'
                ORDER BY date DESC
                LIMIT :limit
            """
            
            params = {
                "symbol": symbol.upper(),
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "limit": lookback_days
            }
            
            rows = db.execute_query(query, params)
            
            if not rows:
                self.logger.warning(f"No historical ATR data found for {symbol}")
                return []
            
            atr_values = [float(row['atr']) for row in rows if row.get('atr')]
            
            self.logger.debug(f"Retrieved {len(atr_values)} ATR values for {symbol}")
            
            return atr_values
            
        except Exception as e:
            self.logger.error(f"Error retrieving historical ATR values for {symbol}: {e}")
            return []
    
    def calculate_atr_percentile(
        self, 
        symbol: str, 
        current_atr_percent: Optional[float] = None,
        lookback_days: Optional[int] = None
    ) -> float:
        """
        Calculate ATR percentile for a symbol using true rank method
        Falls back to cross-sectional percentile if insufficient historical data
        
        Args:
            symbol: Stock symbol
            current_atr_percent: Current ATR percent (if None, will fetch from database)
            lookback_days: Lookback period for percentile calculation
            
        Returns:
            ATR percentile (0.0 to 1.0)
        """
        try:
            # Get current ATR if not provided
            if current_atr_percent is None:
                current_atr_percent = self.get_current_atr_percent(symbol)
            
            if current_atr_percent is None or current_atr_percent <= 0:
                self.logger.warning(f"Invalid current ATR for {symbol}: {current_atr_percent}")
                return 0.5
            
            # Get historical ATR values
            historical_values = self.get_historical_atr_values(symbol, lookback_days)
            
            # Check if we have sufficient historical data
            if len(historical_values) >= 30:  # Minimum sample size for meaningful percentile
                percentile = self.calculate_true_percentile(current_atr_percent, historical_values)
                self.logger.info(f"ATR percentile for {symbol}: {percentile:.3f} "
                               f"(time-series, sample: {len(historical_values)} values)")
                return percentile
            
            # Fallback: Use cross-sectional percentile across all stocks
            self.logger.warning(f"Insufficient ATR history for {symbol} ({len(historical_values)} values), "
                              f"using cross-sectional fallback")
            percentile = self.calculate_cross_sectional_percentile(symbol, current_atr_percent)
            
            self.logger.info(f"ATR percentile for {symbol}: {percentile:.3f} "
                           f"(cross-sectional fallback)")
            
            return percentile
            
        except Exception as e:
            self.logger.error(f"Error calculating ATR percentile for {symbol}: {e}")
            return 0.5
    
    def calculate_cross_sectional_percentile(self, symbol: str, current_atr: float) -> float:
        """
        Calculate percentile across all stocks (cross-sectional comparison)
        Used as fallback when historical data is insufficient
        """
        try:
            # Get current ATR values for all stocks
            query = """
                SELECT DISTINCT symbol, atr
                FROM indicators_daily
                WHERE data_source = 'calculated'
                  AND atr IS NOT NULL
                  AND atr > 0
                  AND date = (
                    SELECT MAX(date) FROM indicators_daily 
                    WHERE data_source = 'calculated'
                  )
            """
            
            rows = db.execute_query(query)
            
            if not rows:
                self.logger.warning("No cross-sectional ATR data available")
                return 0.5
            
            all_atr_values = [float(row['atr']) for row in rows if row.get('atr')]
            
            if not all_atr_values:
                return 0.5
            
            # Calculate percentile across all stocks
            percentile = self.calculate_true_percentile(current_atr, all_atr_values)
            
            self.logger.debug(f"Cross-sectional percentile for {symbol}: {percentile:.3f} "
                            f"(across {len(all_atr_values)} stocks)")
            
            return percentile
            
        except Exception as e:
            self.logger.error(f"Error calculating cross-sectional percentile for {symbol}: {e}")
            return 0.5
    
    def get_current_atr_percent(self, symbol: str) -> Optional[float]:
        """
        Get current ATR percent for a symbol from the database
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Current ATR percent or None if not found
        """
        try:
            query = """
                SELECT atr
                FROM indicators_daily
                WHERE symbol = :symbol
                  AND data_source = 'calculated'
                  AND atr IS NOT NULL
                  AND atr > 0
                ORDER BY date DESC
                LIMIT 1
            """
            
            rows = db.execute_query(query, {"symbol": symbol.upper()})
            
            if not rows:
                return None
            
            return float(rows[0]['atr'])
            
        except Exception as e:
            self.logger.error(f"Error getting current ATR for {symbol}: {e}")
            return None
    
    def calculate_volatility_profile(
        self, 
        symbol: str, 
        current_atr: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive volatility profile for a symbol
        
        Args:
            symbol: Stock symbol
            current_atr: Current ATR value (optional)
            
        Returns:
            Dictionary with volatility profile information
        """
        try:
            # Get current ATR if not provided
            if current_atr is None:
                current_atr = self.get_current_atr_percent(symbol)
            
            # Calculate percentile
            percentile = self.calculate_atr_percentile(symbol, current_atr)
            
            # Get historical values for statistics
            historical_values = self.get_historical_atr_values(symbol)
            
            volatility_profile = {
                "current_atr": current_atr,
                "percentile": percentile,
                "profile": self._classify_volatility_profile(percentile),
                "sample_size": len(historical_values),
                "statistics": self._calculate_atr_statistics(historical_values) if historical_values else {}
            }
            
            self.logger.info(f"Volatility profile for {symbol}: {volatility_profile}")
            
            return volatility_profile
            
        except Exception as e:
            self.logger.error(f"Error calculating volatility profile for {symbol}: {e}")
            return {
                "current_atr": current_atr,
                "percentile": 0.5,
                "profile": "normal",
                "sample_size": 0,
                "statistics": {}
            }
    
    def _classify_volatility_profile(self, percentile: float) -> str:
        """
        Classify volatility profile based on percentile
        """
        if percentile < 0.1:
            return "extremely_low"
        elif percentile < 0.3:
            return "low"
        elif percentile < 0.7:
            return "normal"
        elif percentile < 0.9:
            return "high"
        else:
            return "extremely_high"
    
    def _calculate_atr_statistics(self, atr_values: List[float]) -> Dict[str, float]:
        """
        Calculate ATR statistics for historical values
        """
        if not atr_values:
            return {}
        
        atr_array = np.array(atr_values)
        
        return {
            "mean": float(np.mean(atr_array)),
            "median": float(np.median(atr_array)),
            "std": float(np.std(atr_array)),
            "min": float(np.min(atr_array)),
            "max": float(np.max(atr_array)),
            "p25": float(np.percentile(atr_array, 25)),
            "p75": float(np.percentile(atr_array, 75))
        }
    
    def validate_percentile_calculation(self, symbol: str) -> Dict[str, Any]:
        """
        Validate percentile calculation by checking edge cases
        Useful for debugging and ensuring the fix works correctly
        """
        try:
            historical_values = self.get_historical_atr_values(symbol)
            
            if not historical_values:
                return {"error": "No historical data"}
            
            # Test edge cases
            min_val = min(historical_values)
            max_val = max(historical_values)
            median_val = np.median(historical_values)
            
            min_percentile = self.calculate_true_percentile(min_val, historical_values)
            max_percentile = self.calculate_true_percentile(max_val, historical_values)
            median_percentile = self.calculate_true_percentile(median_val, historical_values)
            
            validation = {
                "symbol": symbol,
                "sample_size": len(historical_values),
                "min_value": min_val,
                "max_value": max_val,
                "median_value": median_val,
                "min_percentile": min_percentile,
                "max_percentile": max_percentile,
                "median_percentile": median_percentile,
                "validation_passed": (
                    0.0 <= min_percentile <= 0.1 and  # Min should be near 0
                    0.9 <= max_percentile <= 1.0 and  # Max should be near 1
                    0.4 <= median_percentile <= 0.6    # Median should be near 0.5
                )
            }
            
            self.logger.info(f"Percentile validation for {symbol}: {validation}")
            
            return validation
            
        except Exception as e:
            self.logger.error(f"Error validating percentile calculation for {symbol}: {e}")
            return {"error": str(e)}
