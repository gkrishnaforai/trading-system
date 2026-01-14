"""
Actionable Levels Service for Pro Tier
Calculates entry zones, stop-loss, and target levels
"""
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from app.services.base import BaseService
from app.indicators.signals import calculate_pullback_zones, calculate_stop_loss
from app.utils.series_utils import extract_latest_value
from app.exceptions import ValidationError


class ActionableLevelsService(BaseService):
    """
    Calculates actionable trading levels for Pro tier users
    Provides entry zones, stop-loss, and target levels
    
    SOLID: Single Responsibility - only calculates actionable levels
    """
    
    def __init__(self):
        """Initialize actionable levels service"""
        super().__init__()
    
    def calculate_actionable_levels(
        self,
        indicators: Dict[str, Any],
        current_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate actionable levels for trading
        
        Args:
            indicators: Dictionary of calculated indicators
            current_price: Current stock price (optional)
        
        Returns:
            Dictionary with:
            - entry_zone: Dict with 'lower' and 'upper' prices
            - stop_loss: Stop-loss price
            - first_target: First target/exit zone
            - risk_level: Risk assessment (Low/Moderate/High)
        """
        # Extract indicators
        price = indicators.get('price')
        ema20 = indicators.get('ema20')
        atr = indicators.get('atr')
        sma50 = indicators.get('sma50')
        sma200 = indicators.get('sma200')
        long_term_trend = indicators.get('long_term_trend')
        
        # Get latest values using utility (DRY)
        price_val = extract_latest_value(price, current_price)
        
        if price_val is None:
            return {
                'entry_zone': {'lower': None, 'upper': None},
                'stop_loss': None,
                'first_target': None,
                'risk_level': 'Unknown'
            }
        
        # Calculate entry zone (pullback zone)
        entry_lower, entry_upper = calculate_pullback_zones(price, ema20, atr)
        
        # Convert to dict format for compatibility
        entry_zone = {
            'lower': entry_lower.iloc[-1] if len(entry_lower) > 0 and not pd.isna(entry_lower.iloc[-1]) else None,
            'upper': entry_upper.iloc[-1] if len(entry_upper) > 0 and not pd.isna(entry_upper.iloc[-1]) else None
        }
        
        # Calculate stop-loss (2x ATR)
        stop_loss = calculate_stop_loss(price, atr, multiplier=2.0, position_type='long')
        
        # Calculate first target (1.5x ATR above entry zone upper)
        first_target = None
        if entry_zone.get('upper'):
            atr_val = atr.iloc[-1] if isinstance(atr, pd.Series) and len(atr) > 0 else None
            if atr_val:
                first_target = entry_zone['upper'] + (atr_val * 1.5)
        
        # Calculate risk level
        risk_level = self._calculate_risk_level(
            price_val, entry_zone, stop_loss, atr, sma50, sma200, long_term_trend
        )
        
        return {
            'entry_zone': entry_zone,
            'stop_loss': stop_loss,
            'first_target': first_target,
            'risk_level': risk_level
        }
    
    def _calculate_risk_level(
        self,
        price: float,
        entry_zone: Dict[str, Optional[float]],
        stop_loss: Optional[float],
        atr: Any,
        sma50: Any,
        sma200: Any,
        long_term_trend: Any
    ) -> str:
        """Calculate risk level (Low/Moderate/High)"""
        if not stop_loss or not entry_zone.get('upper'):
            return 'Unknown'
        
        # Calculate risk as percentage
        entry_price = entry_zone.get('upper', price)
        risk_pct = abs((entry_price - stop_loss) / entry_price) * 100
        
        # Get ATR value using utility (DRY)
        atr_val = extract_latest_value(atr)
        atr_pct = (atr_val / price * 100) if atr_val and price else None
        
        # Determine risk level
        if risk_pct < 3 and (not atr_pct or atr_pct < 2):
            return 'Low'
        elif risk_pct < 5 and (not atr_pct or atr_pct < 4):
            return 'Moderate'
        else:
            return 'High'

