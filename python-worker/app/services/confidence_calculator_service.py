"""
Confidence Calculator Service
Implements clean, mathematically coherent confidence calculation
Direction Score ∈ [-1, +1] × Environment Confidence ∈ [0.3, 0.9] = Final Confidence
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple
from app.observability.logging import get_logger

logger = get_logger(__name__)


class ConfidenceCalculator:
    """
    Centralized confidence calculation with clean mathematical architecture
    Separates direction (market edge) from confidence (environment reliability)
    """
    
    # Regime-adaptive weight matrices - systematic, not conditional
    WEIGHT_MATRIX = {
        "bull": {
            "rs": 0.21, "trend": 0.22, "momentum": 0.27, "breakout": 0.16,
            "rsi_trend": 0.05, "volume_confirmation": 0.05, "volume_trend": 0.04
        },
        "bear": {
            "rs": 0.18, "trend": 0.38, "momentum": 0.22, "breakout": 0.13,
            "rsi_trend": 0.03, "volume_confirmation": 0.04, "volume_trend": 0.02
        },
        "sideways": {
            "rs": 0.34, "trend": 0.17, "momentum": 0.17, "breakout": 0.17,
            "rsi_trend": 0.05, "volume_confirmation": 0.05, "volume_trend": 0.05
        }
    }
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    def calculate_direction_score(
        self, 
        normalized_components: Dict[str, float], 
        regime: str
    ) -> float:
        """
        Calculate pure directional score, independent of environment factors
        Range: [-1, +1]
        """
        try:
            weights = self.WEIGHT_MATRIX.get(regime, self.WEIGHT_MATRIX["sideways"])
            
            direction_score = sum(
                weights.get(component, 0.0) * value
                for component, value in normalized_components.items()
                if component in weights
            )
            
            # Ensure bounds
            direction_score = np.clip(direction_score, -1.0, 1.0)
            
            self.logger.debug(f"Direction score: {direction_score:.3f} (regime: {regime}, components: {normalized_components})")
            
            return direction_score
            
        except Exception as e:
            self.logger.error(f"Error calculating direction score: {e}")
            return 0.0
    
    def calculate_regime_clarity(self, regime: str, regime_data: Optional[Dict[str, Any]] = None) -> float:
        """
        Calculate regime clarity based on how well-defined the market regime is
        Range: [0.3, 0.9]
        """
        regime_clarity_map = {
            "strong_bull": 0.9,
            "bull": 0.8,
            "strong_bear": 0.85, 
            "bear": 0.75,
            "sideways": 0.5,
            "transitioning": 0.4,
            "choppy": 0.3
        }
        
        clarity = regime_clarity_map.get(regime, 0.5)
        
        # Adjust based on regime confidence if available
        if regime_data and 'regime_confidence' in regime_data:
            regime_confidence = regime_data['regime_confidence']
            # Blend with regime confidence
            clarity = 0.7 * clarity + 0.3 * regime_confidence
        
        return np.clip(clarity, 0.3, 0.9)
    
    def calculate_volatility_clarity(self, volatility_percentile: float) -> float:
        """
        Calculate volatility clarity based on ATR percentile
        Ideal range (40-70th percentile) = highest clarity
        Range: [0.3, 0.9]
        """
        if volatility_percentile is None:
            return 0.5  # Default to moderate clarity
        
        # Ideal volatility range gets highest clarity
        if 40 <= volatility_percentile <= 70:
            return 0.9  # Ideal volatility
        elif 20 <= volatility_percentile < 40 or 70 < volatility_percentile <= 85:
            return 0.7  # Acceptable volatility
        else:
            return 0.5  # Extreme compression or panic
    
    def calculate_signal_consistency(self, normalized_components: Dict[str, float]) -> float:
        """
        Calculate how consistent the signal components are
        All components aligned = highest clarity
        Mixed signals = lower clarity
        Range: [0.3, 0.9]
        """
        if not normalized_components:
            return 0.3
        
        # Count positive vs negative components
        positive_count = sum(1 for v in normalized_components.values() if v > 0.1)
        negative_count = sum(1 for v in normalized_components.values() if v < -0.1)
        neutral_count = len(normalized_components) - positive_count - negative_count
        
        total_count = len(normalized_components)
        
        if total_count == 0:
            return 0.3
        
        # Calculate alignment ratio
        max_aligned = max(positive_count, negative_count)
        alignment_ratio = max_aligned / total_count
        
        # Convert to clarity score
        if alignment_ratio >= 0.8:
            return 0.9  # Highly consistent
        elif alignment_ratio >= 0.6:
            return 0.7  # Moderately consistent
        elif alignment_ratio >= 0.4:
            return 0.5  # Mixed signals
        else:
            return 0.3  # Very inconsistent
    
    def calculate_environment_confidence(
        self,
        regime: str,
        volatility_percentile: float,
        normalized_components: Dict[str, float],
        regime_data: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Calculate environment confidence using multiplicative model
        Range: [0.3, 0.9]
        """
        try:
            # Calculate individual clarity components
            regime_clarity = self.calculate_regime_clarity(regime, regime_data)
            volatility_clarity = self.calculate_volatility_clarity(volatility_percentile)
            signal_consistency = self.calculate_signal_consistency(normalized_components)
            
            # Multiplicative model - any factor = 0 reduces confidence significantly
            raw_confidence = regime_clarity * volatility_clarity * signal_consistency
            
            # Apply sigmoid for smooth bounding (optional, can use direct clipping)
            # Using direct clipping for simplicity and predictability
            bounded_confidence = np.clip(raw_confidence, 0.3, 0.9)
            
            self.logger.debug(f"Environment confidence: {bounded_confidence:.3f} "
                            f"(regime: {regime_clarity:.3f}, "
                            f"volatility: {volatility_clarity:.3f}, "
                            f"consistency: {signal_consistency:.3f})")
            
            return bounded_confidence
            
        except Exception as e:
            self.logger.error(f"Error calculating environment confidence: {e}")
            return 0.5  # Default to moderate confidence
    
    def calculate_final_confidence(
        self,
        direction_score: float,
        environment_confidence: float
    ) -> float:
        """
        Calculate final confidence using clean multiplicative architecture
        Final Confidence = |Direction Score| × Environment Confidence
        Range: [0, 0.9]
        """
        try:
            final_confidence = abs(direction_score) * environment_confidence
            
            # Ensure bounds
            final_confidence = np.clip(final_confidence, 0.0, 0.9)
            
            self.logger.debug(f"Final confidence: {final_confidence:.3f} "
                            f"(|direction|: {abs(direction_score):.3f} × "
                            f"environment: {environment_confidence:.3f})")
            
            return final_confidence
            
        except Exception as e:
            self.logger.error(f"Error calculating final confidence: {e}")
            return 0.0
    
    def calculate_complete_confidence(
        self,
        normalized_components: Dict[str, float],
        regime: str,
        volatility_percentile: float,
        regime_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, float, float]:
        """
        Calculate complete confidence package
        Returns: (direction_score, environment_confidence, final_confidence)
        """
        try:
            # Step 1: Calculate direction score (pure market edge)
            direction_score = self.calculate_direction_score(normalized_components, regime)
            
            # Step 2: Calculate environment confidence (market condition reliability)
            environment_confidence = self.calculate_environment_confidence(
                regime, volatility_percentile, normalized_components, regime_data
            )
            
            # Step 3: Calculate final confidence (multiplicative model)
            final_confidence = self.calculate_final_confidence(direction_score, environment_confidence)
            
            self.logger.info(f"Complete confidence calculation: "
                           f"direction={direction_score:.3f}, "
                           f"environment={environment_confidence:.3f}, "
                           f"final={final_confidence:.3f}")
            
            return direction_score, environment_confidence, final_confidence
            
        except Exception as e:
            self.logger.error(f"Error in complete confidence calculation: {e}")
            return 0.0, 0.5, 0.0
