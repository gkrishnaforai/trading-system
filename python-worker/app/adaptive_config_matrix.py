"""
Adaptive Configuration Matrix
Implements 3D configuration matrix: (Volatility, Regime, Relative Strength) -> Config
"""

from typing import Dict, Any, Tuple
from enum import Enum
import logging

from app.services.market_regime_service import MarketRegime
from app.services.volatility_profiler_service import VolatilityProfile
from app.services.relative_strength_service import RelativeStrengthTier
from app.observability.logging import get_logger

logger = get_logger(__name__)

class ConfigMatrix:
    """3D configuration matrix for adaptive signal generation"""
    
    def __init__(self):
        self.matrix = self._build_config_matrix()
        
    def _build_config_matrix(self) -> Dict[Tuple[VolatilityProfile, MarketRegime, RelativeStrengthTier], Dict[str, Any]]:
        """Build 3D configuration matrix"""
        matrix = {}
        
        # Generate configurations for all combinations
        for vol_profile in VolatilityProfile:
            for regime in MarketRegime:
                for rs_tier in RelativeStrengthTier:
                    key = (vol_profile, regime, rs_tier)
                    matrix[key] = self._generate_config(vol_profile, regime, rs_tier)
        
        return matrix
    
    def _generate_config(self, vol: VolatilityProfile, regime: MarketRegime, rs: RelativeStrengthTier) -> Dict[str, Any]:
        """Generate configuration for specific combination of volatility, regime, and relative strength"""
        
        # Base configuration
        config = {
            'rsi_oversold': 35,
            'rsi_overbought': 70,
            'rsi_extreme_oversold': 25,
            'rsi_extreme_overbought': 80,
            'breakout_threshold': 0.02,
            'breakout_rsi_upper_bound': 65,
            'confidence_boost': 0.0,
            'stop_loss_pct': 0.08,
            'take_profit_pct': 0.20,
            'score_weights': {
                'trend': 0.3,
                'momentum': 0.4,
                'breakout': 0.3
            }
        }
        
        # Adjust based on market regime
        if regime in [MarketRegime.STRONG_BULL, MarketRegime.MILD_BULL]:
            # Bull market adjustments
            config['rsi_oversold'] += 10  # Allow higher entries in bull markets
            config['rsi_extreme_oversold'] += 5
            config['confidence_boost'] += 0.1
            config['score_weights']['momentum'] = 0.5  # Emphasize momentum in bull markets
            config['score_weights']['trend'] = 0.4
            config['score_weights']['breakout'] = 0.1
            
        elif regime in [MarketRegime.STRONG_BEAR, MarketRegime.MILD_BEAR]:
            # Bear market adjustments
            config['rsi_oversold'] -= 15  # Require deeper oversold in bear markets
            config['rsi_extreme_oversold'] -= 10
            config['rsi_overbought'] -= 5  # Lower overbought threshold in bear markets
            config['confidence_boost'] -= 0.1
            config['score_weights']['trend'] = 0.5  # Emphasize trend in bear markets
            config['score_weights']['momentum'] = 0.3
            config['score_weights']['breakout'] = 0.2
            
        else:  # SIDEWAYS
            # Sideways market adjustments
            config['score_weights']['trend'] = 0.2  # De-emphasize trend in sideways
            config['score_weights']['momentum'] = 0.4
            config['score_weights']['breakout'] = 0.4
        
        # Adjust based on volatility profile
        if vol == VolatilityProfile.HIGH:
            # High volatility adjustments
            config['breakout_threshold'] *= 1.5  # Require stronger momentum
            config['breakout_rsi_upper_bound'] += 5  # Higher RSI threshold for breakouts
            config['stop_loss_pct'] *= 1.3  # Wider stops
            config['take_profit_pct'] *= 1.2  # Larger targets
            config['confidence_boost'] -= 0.1  # Reduce confidence in high volatility
            
        elif vol == VolatilityProfile.LOW:
            # Low volatility adjustments
            config['breakout_threshold'] *= 0.7  # Lower threshold for breakouts
            config['breakout_rsi_upper_bound'] -= 5  # Lower RSI threshold for breakouts
            config['stop_loss_pct'] *= 0.8  # Tighter stops
            config['take_profit_pct'] *= 0.9  # Smaller targets
            config['confidence_boost'] += 0.1  # Boost confidence in low volatility
        
        # Adjust based on relative strength
        if rs in [RelativeStrengthTier.STRONG_OUTPERFORMER, RelativeStrengthTier.MODERATE_OUTPERFORMER]:
            # Outperformers
            config['confidence_boost'] += 0.2
            config['stop_loss_pct'] *= 0.9  # Tighter stops for strong stocks
            config['take_profit_pct'] *= 1.1  # Larger targets for strong stocks
            
        elif rs in [RelativeStrengthTier.STRONG_UNDERPERFORMER, RelativeStrengthTier.WEAK_UNDERPERFORMER]:
            # Underperformers
            config['confidence_boost'] -= 0.2
            config['stop_loss_pct'] *= 1.2  # Wider stops for weak stocks
            config['take_profit_pct'] *= 0.8  # Smaller targets for weak stocks
            config['rsi_oversold'] -= 5  # Require even deeper oversold for underperformers
        
        # Special case combinations
        self._apply_special_cases(config, vol, regime, rs)
        
        # Ensure values stay in reasonable ranges
        self._validate_config(config)
        
        return config
    
    def _apply_special_cases(self, config: Dict[str, Any], vol: VolatilityProfile, 
                           regime: MarketRegime, rs: RelativeStrengthTier):
        """Apply special case adjustments for specific combinations"""
        
        # Strong bull + strong outperformer + normal volatility = best case
        if (regime == MarketRegime.STRONG_BULL and 
            rs == RelativeStrengthTier.STRONG_OUTPERFORMER and 
            vol == VolatilityProfile.NORMAL):
            config['confidence_boost'] += 0.2
            config['score_weights']['momentum'] = 0.6
            config['score_weights']['trend'] = 0.3
            config['score_weights']['breakout'] = 0.1
        
        # Strong bear + strong underperformer + high volatility = worst case
        elif (regime == MarketRegime.STRONG_BEAR and 
              rs == RelativeStrengthTier.STRONG_UNDERPERFORMER and 
              vol == VolatilityProfile.HIGH):
            config['confidence_boost'] -= 0.3
            config['rsi_oversold'] -= 10  # Very deep oversold required
            config['breakout_threshold'] *= 2.0  # Very high threshold
            config['score_weights']['trend'] = 0.6  # Heavy emphasis on trend
            config['score_weights']['momentum'] = 0.2
            config['score_weights']['breakout'] = 0.2
        
        # Sideways + high volatility = choppy conditions
        elif (regime == MarketRegime.SIDEWAYS and vol == VolatilityProfile.HIGH):
            config['confidence_boost'] -= 0.2
            config['score_weights']['breakout'] = 0.5  # Emphasize breakouts in choppy markets
            config['score_weights']['momentum'] = 0.3
            config['score_weights']['trend'] = 0.2
        
        # Low volatility + any regime = more reliable signals
        elif vol == VolatilityProfile.LOW:
            config['confidence_boost'] += 0.1
            config['breakout_threshold'] *= 0.8  # Lower threshold for low vol breakouts
    
    def _validate_config(self, config: Dict[str, Any]):
        """Ensure configuration values stay in reasonable ranges"""
        
        # RSI bounds
        config['rsi_oversold'] = max(15, min(50, config['rsi_oversold']))
        config['rsi_overbought'] = max(50, min(85, config['rsi_overbought']))
        config['rsi_extreme_oversold'] = max(10, min(40, config['rsi_extreme_oversold']))
        config['rsi_extreme_overbought'] = max(60, min(90, config['rsi_extreme_overbought']))
        
        # Ensure logical consistency
        config['rsi_extreme_oversold'] = min(config['rsi_extreme_oversold'], config['rsi_oversold'])
        config['rsi_overbought'] = min(config['rsi_overbought'], config['rsi_extreme_overbought'])
        
        # Breakout thresholds
        config['breakout_threshold'] = max(0.005, min(0.1, config['breakout_threshold']))
        config['breakout_rsi_upper_bound'] = max(55, min(75, config['breakout_rsi_upper_bound']))
        
        # Risk management
        config['stop_loss_pct'] = max(0.03, min(0.15, config['stop_loss_pct']))
        config['take_profit_pct'] = max(0.1, min(0.4, config['take_profit_pct']))
        
        # Confidence boost
        config['confidence_boost'] = max(-0.5, min(0.5, config['confidence_boost']))
        
        # Score weights (must sum to 1.0)
        total_weight = sum(config['score_weights'].values())
        if total_weight > 0:
            for key in config['score_weights']:
                config['score_weights'][key] /= total_weight
    
    def get_config(self, vol_profile: VolatilityProfile, market_regime: MarketRegime, 
                   rs_tier: RelativeStrengthTier) -> Dict[str, Any]:
        """Get configuration for specific combination"""
        
        key = (vol_profile, market_regime, rs_tier)
        
        if key not in self.matrix:
            logger.warning(f"Configuration not found for {key}, using default")
            return self._get_default_config()
        
        return self.matrix[key].copy()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration for fallback"""
        return {
            'rsi_oversold': 35,
            'rsi_overbought': 70,
            'rsi_extreme_oversold': 25,
            'rsi_extreme_overbought': 80,
            'breakout_threshold': 0.02,
            'breakout_rsi_upper_bound': 65,
            'confidence_boost': 0.0,
            'stop_loss_pct': 0.08,
            'take_profit_pct': 0.20,
            'score_weights': {
                'trend': 0.3,
                'momentum': 0.4,
                'breakout': 0.3
            }
        }
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get summary of configuration matrix"""
        
        summary = {
            'total_combinations': len(self.matrix),
            'volatility_profiles': list(VolatilityProfile),
            'market_regimes': list(MarketRegime),
            'relative_strength_tiers': list(RelativeStrengthTier),
            'example_configs': {}
        }
        
        # Add a few example configurations
        examples = [
            (VolatilityProfile.NORMAL, MarketRegime.STRONG_BULL, RelativeStrengthTier.STRONG_OUTPERFORMER),
            (VolatilityProfile.HIGH, MarketRegime.STRONG_BEAR, RelativeStrengthTier.STRONG_UNDERPERFORMER),
            (VolatilityProfile.NORMAL, MarketRegime.SIDEWAYS, RelativeStrengthTier.WEAK_OUTPERFORMER)
        ]
        
        for vol, regime, rs in examples:
            key = (vol, regime, rs)
            if key in self.matrix:
                config_name = f"{vol.value}_{regime.value}_{rs.value}"
                summary['example_configs'][config_name] = {
                    'rsi_oversold': self.matrix[key]['rsi_oversold'],
                    'rsi_overbought': self.matrix[key]['rsi_overbought'],
                    'breakout_threshold': self.matrix[key]['breakout_threshold'],
                    'confidence_boost': self.matrix[key]['confidence_boost']
                }
        
        return summary
    
    def update_config(self, vol_profile: VolatilityProfile, market_regime: MarketRegime,
                     rs_tier: RelativeStrengthTier, updates: Dict[str, Any]):
        """Update specific configuration"""
        
        key = (vol_profile, market_regime, rs_tier)
        
        if key not in self.matrix:
            self.matrix[key] = self._get_default_config()
        
        # Apply updates
        self.matrix[key].update(updates)
        
        # Validate updated config
        self._validate_config(self.matrix[key])
        
        logger.info(f"Updated configuration for {key}")
    
    def get_regime_specific_configs(self, regime: MarketRegime) -> Dict[str, Any]:
        """Get all configurations for a specific market regime"""
        
        regime_configs = {}
        
        for (vol, reg, rs), config in self.matrix.items():
            if reg == regime:
                key = f"{vol.value}_{rs.value}"
                regime_configs[key] = config.copy()
        
        return regime_configs
    
    def get_volatility_specific_configs(self, vol_profile: VolatilityProfile) -> Dict[str, Any]:
        """Get all configurations for a specific volatility profile"""
        
        vol_configs = {}
        
        for (vol, reg, rs), config in self.matrix.items():
            if vol == vol_profile:
                key = f"{reg.value}_{rs.value}"
                vol_configs[key] = config.copy()
        
        return vol_configs
