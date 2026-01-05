"""
Generic ETF Swing Engine
Uses common logic extracted from TQQQ engine but configurable for different ETFs
"""

from typing import Dict, Any, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass
from app.signal_engines.signal_calculator_core import (
    SignalType, MarketConditions, SignalResult
)
from app.signal_engines.unified_tqqq_swing_engine import MarketRegime
from app.signal_engines.common_signal_logic import (
    SignalEngineUtils, MeanReversionLogic, TrendContinuationLogic, 
    BreakoutLogic, VolatilityExpansionLogic
)

class InstrumentType(Enum):
    """Different instrument types with specific characteristics"""
    # ETFs
    TQQQ = "tqqq"      # 3x leveraged, high volatility
    QQQ = "qqq"        # 1x tech, high volatility  
    SMH = "smh"        # 1x semiconductors, high volatility
    SPY = "spy"        # 1x S&P 500, moderate volatility
    IWM = "iwm"        # 1x small cap, moderate volatility
    GLD = "gld"        # Gold, different dynamics
    
    # Stocks by sector/market cap
    TECH_LARGE = "tech_large"      # AAPL, MSFT, GOOGL, etc.
    TECH_GROWTH = "tech_growth"    # NVDA, TSLA, META, etc.
    TECH_VALUE = "tech_value"      # INTC, IBM, etc.
    FINANCE = "finance"            # JPM, BAC, WFC, etc.
    HEALTHCARE = "healthcare"      # JNJ, PFE, UNH, etc.
    CONSUMER = "consumer"          # AMZN, HD, MCD, etc.
    ENERGY = "energy"              # XOM, CVX, COP, etc.
    INDUSTRIAL = "industrial"      # CAT, DE, BA, etc.
    SMALL_CAP = "small_cap"        # Small cap stocks
    MID_CAP = "mid_cap"            # Mid cap stocks
    MICRO_CAP = "micro_cap"        # Micro cap stocks

@dataclass
class InstrumentConfig:
    """Instrument-specific configuration parameters"""
    # Volatility thresholds
    volatility_expansion_threshold: float = 4.0
    high_volatility_threshold: float = 8.0
    
    # RSI thresholds
    rsi_oversold: float = 45.0
    rsi_moderately_oversold: float = 35.0
    rsi_overbought: float = 65.0
    rsi_extreme_oversold: float = 30.0
    rsi_extreme_overbought: float = 70.0
    
    # Trend sensitivity
    trend_sensitivity: float = 1.0  # 1.0 = normal, >1.0 = more sensitive
    risk_off_downtrend: bool = True  # Any downtrend = risk-off?
    
    # Momentum thresholds
    breakout_momentum_threshold: float = 0.02
    breakout_rsi_upper_bound: float = 70.0
    
    # Mean reversion thresholds
    mean_reversion_rsi_upper: float = 60.0
    mean_reversion_momentum_threshold: float = 0.04

# ETF-specific configurations
ETF_CONFIGS = {
    InstrumentType.QQQ: InstrumentConfig(
        volatility_expansion_threshold=6.0,  # Higher threshold (less sensitive)
        high_volatility_threshold=10.0,
        rsi_oversold=40.0,  # More aggressive
        rsi_moderately_oversold=30.0,
        rsi_overbought=60.0,
        rsi_extreme_oversold=25.0,
        rsi_extreme_overbought=75.0,
        trend_sensitivity=1.0,  # Normal sensitivity
        risk_off_downtrend=False,  # Not all downtrends = risk-off
        breakout_momentum_threshold=0.025,
        breakout_rsi_upper_bound=75.0,
        mean_reversion_rsi_upper=65.0,
        mean_reversion_momentum_threshold=0.05
    ),
    
    InstrumentType.SMH: InstrumentConfig(
        volatility_expansion_threshold=5.0,
        high_volatility_threshold=9.0,
        rsi_oversold=42.0,
        rsi_moderately_oversold=32.0,
        rsi_overbought=62.0,
        rsi_extreme_oversold=28.0,
        rsi_extreme_overbought=72.0,
        trend_sensitivity=1.1,  # Slightly more sensitive (sector momentum)
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.03,
        breakout_rsi_upper_bound=72.0,
        mean_reversion_rsi_upper=62.0,
        mean_reversion_momentum_threshold=0.045
    ),
    
    InstrumentType.SPY: InstrumentConfig(
        volatility_expansion_threshold=8.0,  # Much higher threshold
        high_volatility_threshold=12.0,
        rsi_oversold=35.0,  # Much more aggressive
        rsi_moderately_oversold=25.0,
        rsi_overbought=55.0,
        rsi_extreme_oversold=20.0,
        rsi_extreme_overbought=80.0,
        trend_sensitivity=0.8,  # Less sensitive (more stable)
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.015,
        breakout_rsi_upper_bound=80.0,
        mean_reversion_rsi_upper=70.0,
        mean_reversion_momentum_threshold=0.06
    ),
    
    InstrumentType.IWM: InstrumentConfig(
        volatility_expansion_threshold=7.0,
        high_volatility_threshold=11.0,
        rsi_oversold=38.0,
        rsi_moderately_oversold=28.0,
        rsi_overbought=58.0,
        rsi_extreme_oversold=23.0,
        rsi_extreme_overbought=77.0,
        trend_sensitivity=0.9,  # Slightly less sensitive
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.02,
        breakout_rsi_upper_bound=77.0,
        mean_reversion_rsi_upper=68.0,
        mean_reversion_momentum_threshold=0.055
    ),
    
    InstrumentType.GLD: InstrumentConfig(
        volatility_expansion_threshold=5.5,  # Gold has different volatility patterns
        high_volatility_threshold=9.5,
        rsi_oversold=30.0,  # Gold uses more extreme RSI
        rsi_moderately_oversold=20.0,
        rsi_overbought=70.0,
        rsi_extreme_oversold=15.0,
        rsi_extreme_overbought=85.0,
        trend_sensitivity=0.7,  # Gold trends are slower
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.025,
        breakout_rsi_upper_bound=80.0,
        mean_reversion_rsi_upper=75.0,
        mean_reversion_momentum_threshold=0.07
    )
}

# Stock-specific configurations
STOCK_CONFIGS = {
    # Tech Large Cap (stable, liquid)
    InstrumentType.TECH_LARGE: InstrumentConfig(
        volatility_expansion_threshold=6.0,
        high_volatility_threshold=10.0,
        rsi_oversold=35.0,
        rsi_moderately_oversold=25.0,
        rsi_overbought=65.0,
        rsi_extreme_oversold=20.0,
        rsi_extreme_overbought=80.0,
        trend_sensitivity=0.9,
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.02,
        breakout_rsi_upper_bound=75.0,
        mean_reversion_rsi_upper=70.0,
        mean_reversion_momentum_threshold=0.04
    ),
    
    # Tech Growth (high volatility, momentum)
    InstrumentType.TECH_GROWTH: InstrumentConfig(
        volatility_expansion_threshold=5.0,
        high_volatility_threshold=8.0,
        rsi_oversold=40.0,
        rsi_moderately_oversold=30.0,
        rsi_overbought=70.0,
        rsi_extreme_oversold=25.0,
        rsi_extreme_overbought=75.0,
        trend_sensitivity=1.2,  # More sensitive to trends
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.03,
        breakout_rsi_upper_bound=72.0,
        mean_reversion_rsi_upper=65.0,
        mean_reversion_momentum_threshold=0.045
    ),
    
    # Tech Value (more conservative)
    InstrumentType.TECH_VALUE: InstrumentConfig(
        volatility_expansion_threshold=7.0,
        high_volatility_threshold=11.0,
        rsi_oversold=30.0,
        rsi_moderately_oversold=20.0,
        rsi_overbought=60.0,
        rsi_extreme_oversold=15.0,
        rsi_extreme_overbought=85.0,
        trend_sensitivity=0.8,
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.015,
        breakout_rsi_upper_bound=80.0,
        mean_reversion_rsi_upper=75.0,
        mean_reversion_momentum_threshold=0.05
    ),
    
    # Finance (moderate volatility)
    InstrumentType.FINANCE: InstrumentConfig(
        volatility_expansion_threshold=6.5,
        high_volatility_threshold=10.5,
        rsi_oversold=38.0,
        rsi_moderately_oversold=28.0,
        rsi_overbought=62.0,
        rsi_extreme_oversold=23.0,
        rsi_extreme_overbought=77.0,
        trend_sensitivity=0.95,
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.022,
        breakout_rsi_upper_bound=75.0,
        mean_reversion_rsi_upper=68.0,
        mean_reversion_momentum_threshold=0.048
    ),
    
    # Healthcare (defensive, stable)
    InstrumentType.HEALTHCARE: InstrumentConfig(
        volatility_expansion_threshold=7.5,
        high_volatility_threshold=12.0,
        rsi_oversold=32.0,
        rsi_moderately_oversold=22.0,
        rsi_overbought=58.0,
        rsi_extreme_oversold=18.0,
        rsi_extreme_overbought=82.0,
        trend_sensitivity=0.7,  # Less sensitive, more stable
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.018,
        breakout_rsi_upper_bound=80.0,
        mean_reversion_rsi_upper=72.0,
        mean_reversion_momentum_threshold=0.055
    ),
    
    # Consumer (mixed volatility)
    InstrumentType.CONSUMER: InstrumentConfig(
        volatility_expansion_threshold=6.0,
        high_volatility_threshold=9.5,
        rsi_oversold=36.0,
        rsi_moderately_oversold=26.0,
        rsi_overbought=64.0,
        rsi_extreme_oversold=21.0,
        rsi_extreme_overbought=79.0,
        trend_sensitivity=0.9,
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.02,
        breakout_rsi_upper_bound=76.0,
        mean_reversion_rsi_upper=69.0,
        mean_reversion_momentum_threshold=0.047
    ),
    
    # Energy (high volatility)
    InstrumentType.ENERGY: InstrumentConfig(
        volatility_expansion_threshold=5.5,
        high_volatility_threshold=9.0,
        rsi_oversold=42.0,
        rsi_moderately_oversold=32.0,
        rsi_overbought=68.0,
        rsi_extreme_oversold=27.0,
        rsi_extreme_overbought=73.0,
        trend_sensitivity=1.1,  # More sensitive to commodity trends
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.025,
        breakout_rsi_upper_bound=72.0,
        mean_reversion_rsi_upper=65.0,
        mean_reversion_momentum_threshold=0.043
    ),
    
    # Industrial (moderate volatility)
    InstrumentType.INDUSTRIAL: InstrumentConfig(
        volatility_expansion_threshold=6.5,
        high_volatility_threshold=10.5,
        rsi_oversold=37.0,
        rsi_moderately_oversold=27.0,
        rsi_overbought=63.0,
        rsi_extreme_oversold=22.0,
        rsi_extreme_overbought=78.0,
        trend_sensitivity=0.85,
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.019,
        breakout_rsi_upper_bound=77.0,
        mean_reversion_rsi_upper=70.0,
        mean_reversion_momentum_threshold=0.051
    ),
    
    # Small Cap (high volatility)
    InstrumentType.SMALL_CAP: InstrumentConfig(
        volatility_expansion_threshold=5.0,
        high_volatility_threshold=8.5,
        rsi_oversold=40.0,
        rsi_moderately_oversold=30.0,
        rsi_overbought=66.0,
        rsi_extreme_oversold=25.0,
        rsi_extreme_overbought=75.0,
        trend_sensitivity=1.15,  # More sensitive
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.025,
        breakout_rsi_upper_bound=73.0,
        mean_reversion_rsi_upper=66.0,
        mean_reversion_momentum_threshold=0.045
    ),
    
    # Mid Cap (moderate-high volatility)
    InstrumentType.MID_CAP: InstrumentConfig(
        volatility_expansion_threshold=5.5,
        high_volatility_threshold=9.0,
        rsi_oversold=38.0,
        rsi_moderately_oversold=28.0,
        rsi_overbought=64.0,
        rsi_extreme_oversold=23.0,
        rsi_extreme_overbought=77.0,
        trend_sensitivity=1.0,
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.022,
        breakout_rsi_upper_bound=74.0,
        mean_reversion_rsi_upper=68.0,
        mean_reversion_momentum_threshold=0.046
    ),
    
    # Micro Cap (very high volatility)
    InstrumentType.MICRO_CAP: InstrumentConfig(
        volatility_expansion_threshold=4.5,
        high_volatility_threshold=7.5,
        rsi_oversold=42.0,
        rsi_moderately_oversold=32.0,
        rsi_overbought=68.0,
        rsi_extreme_oversold=27.0,
        rsi_extreme_overbought=73.0,
        trend_sensitivity=1.3,  # Very sensitive to trends
        risk_off_downtrend=False,
        breakout_momentum_threshold=0.03,
        breakout_rsi_upper_bound=71.0,
        mean_reversion_rsi_upper=64.0,
        mean_reversion_momentum_threshold=0.04
    )
}

# Combined configurations
ALL_CONFIGS = {**ETF_CONFIGS, **STOCK_CONFIGS}

class GenericInstrumentEngine:
    """
    Configurable instrument swing engine for different instrument types (ETFs and Stocks)
    Uses common logic extracted from TQQQ engine but with instrument-specific parameters
    """
    
    def __init__(self, instrument_type: InstrumentType, custom_config: Optional[InstrumentConfig] = None):
        self.instrument_type = instrument_type
        self.config = custom_config or ALL_CONFIGS[instrument_type]
        self.name = f"generic_{instrument_type.value}_swing"
        self.version = "1.0.0"
        self.description = f"Generic {instrument_type.value.upper()} swing engine with configurable parameters"
    
    def detect_market_regime(self, conditions: MarketConditions) -> MarketRegime:
        """ETF-specific regime detection"""
        
        # Calculate trend conditions with sensitivity
        is_uptrend = (
            conditions.sma_20 > conditions.sma_50 and
            conditions.current_price > conditions.sma_50
        )
        
        is_downtrend = (
            conditions.sma_20 < conditions.sma_50 and
            conditions.current_price < conditions.sma_50
        )
        
        # Priority 1: Volatility Expansion (ETF-specific threshold)
        if conditions.volatility > self.config.volatility_expansion_threshold:
            return MarketRegime.VOLATILITY_EXPANSION
        
        # Priority 2: Extreme RSI conditions (ETF-specific thresholds)
        if conditions.rsi > self.config.rsi_extreme_overbought or conditions.rsi < self.config.rsi_extreme_oversold:
            return MarketRegime.MEAN_REVERSION
        
        # Priority 3: Trend Continuation (ETF-specific risk-off logic)
        if is_uptrend:
            return MarketRegime.TREND_CONTINUATION
        elif is_downtrend and self.config.risk_off_downtrend:
            return MarketRegime.VOLATILITY_EXPANSION
        elif is_downtrend:
            return MarketRegime.MEAN_REVERSION  # Downtrend but not risk-off
        
        # Priority 4: Breakout (ETF-specific thresholds)
        if (
            conditions.recent_change > self.config.breakout_momentum_threshold and
            conditions.rsi > 55 and conditions.rsi < self.config.breakout_rsi_upper_bound and
            conditions.current_price > conditions.sma_20
        ):
            return MarketRegime.BREAKOUT
        
        # Priority 5: Default → Mean Reversion
        return MarketRegime.MEAN_REVERSION
    
    def generate_signal(self, conditions: MarketConditions) -> SignalResult:
        """Generate signal using ETF-specific logic with common components"""
        
        regime = self.detect_market_regime(conditions)
        
        # Convert config to dict for logic classes
        config_dict = {
            'rsi_oversold': self.config.rsi_oversold,
            'rsi_moderately_oversold': self.config.rsi_moderately_oversold,
            'rsi_overbought': self.config.rsi_overbought,
            'mean_reversion_rsi_upper': self.config.mean_reversion_rsi_upper,
            'mean_reversion_momentum_threshold': self.config.mean_reversion_momentum_threshold,
            'breakout_momentum_threshold': self.config.breakout_momentum_threshold,
            'breakout_rsi_upper_bound': self.config.breakout_rsi_upper_bound,
            'high_volatility_threshold': self.config.high_volatility_threshold,
            'rsi_extreme_oversold': self.config.rsi_extreme_oversold
        }
        
        # Use common logic classes with ETF-specific config
        if regime == MarketRegime.MEAN_REVERSION:
            result = MeanReversionLogic.generate_signal(conditions, config_dict)
        elif regime == MarketRegime.TREND_CONTINUATION:
            result = TrendContinuationLogic.generate_signal(conditions, config_dict)
        elif regime == MarketRegime.BREAKOUT:
            result = BreakoutLogic.generate_signal(conditions, config_dict)
        elif regime == MarketRegime.VOLATILITY_EXPANSION:
            result = VolatilityExpansionLogic.generate_signal(conditions, config_dict)
        else:
            result = SignalEngineUtils.create_signal_result(
                SignalType.HOLD, 0.0, ["Unknown regime"]
            )
        
        # Add ETF-specific metadata
        result.metadata.update({
            'instrument_type': self.instrument_type.value,
            'regime': regime.value,
            'engine_name': self.name,
            'engine_version': self.version,
            'volatility_threshold': self.config.volatility_expansion_threshold,
            'risk_off_downtrend': self.config.risk_off_downtrend
        })
        
        return result
    
    def get_engine_metadata(self) -> Dict[str, Any]:
        """Get engine metadata"""
        return {
            'display_name': f'{self.instrument_type.value.upper()} Swing Engine',
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'instrument_type': self.instrument_type.value,
            'config': {
                'volatility_threshold': self.config.volatility_expansion_threshold,
                'rsi_oversold': self.config.rsi_oversold,
                'rsi_overbought': self.config.rsi_overbought,
                'risk_off_downtrend': self.config.risk_off_downtrend,
                'trend_sensitivity': self.config.trend_sensitivity
            },
            'features': [
                'Market regime classification',
                'Regime-specific signal logic',
                'Always generates BUY/SELL/HOLD',
                f'Optimized for {self.instrument_type.value.upper()} characteristics',
                'Uses proven TQQQ engine logic',
                'ETF-specific parameter tuning'
            ]
        }

# Factory function
def create_instrument_engine(symbol: str) -> GenericInstrumentEngine:
    """Create instrument engine based on symbol"""
    
    # ETF mappings
    etf_type_map = {
        'QQQ': InstrumentType.QQQ,
        'SMH': InstrumentType.SMH,
        'SPY': InstrumentType.SPY,
        'IWM': InstrumentType.IWM,
        'GLD': InstrumentType.GLD
    }
    
    # Stock mappings by sector/market cap
    stock_type_map = {
        # Tech Large Cap
        'AAPL': InstrumentType.TECH_LARGE,
        'MSFT': InstrumentType.TECH_LARGE,
        'GOOGL': InstrumentType.TECH_LARGE,
        'GOOG': InstrumentType.TECH_LARGE,
        
        # Tech Growth
        'NVDA': InstrumentType.TECH_GROWTH,
        'TSLA': InstrumentType.TECH_GROWTH,
        'META': InstrumentType.TECH_GROWTH,
        'AMD': InstrumentType.TECH_GROWTH,
        
        # Tech Value
        'INTC': InstrumentType.TECH_VALUE,
        'IBM': InstrumentType.TECH_VALUE,
        'CSCO': InstrumentType.TECH_VALUE,
        
        # Finance
        'JPM': InstrumentType.FINANCE,
        'BAC': InstrumentType.FINANCE,
        'WFC': InstrumentType.FINANCE,
        'GS': InstrumentType.FINANCE,
        
        # Healthcare
        'JNJ': InstrumentType.HEALTHCARE,
        'PFE': InstrumentType.HEALTHCARE,
        'UNH': InstrumentType.HEALTHCARE,
        'ABBV': InstrumentType.HEALTHCARE,
        
        # Consumer
        'AMZN': InstrumentType.CONSUMER,
        'HD': InstrumentType.CONSUMER,
        'MCD': InstrumentType.CONSUMER,
        'NKE': InstrumentType.CONSUMER,
        
        # Energy
        'XOM': InstrumentType.ENERGY,
        'CVX': InstrumentType.ENERGY,
        'COP': InstrumentType.ENERGY,
        'SLB': InstrumentType.ENERGY,
        
        # Industrial
        'CAT': InstrumentType.INDUSTRIAL,
        'DE': InstrumentType.INDUSTRIAL,
        'BA': InstrumentType.INDUSTRIAL,
        'GE': InstrumentType.INDUSTRIAL
    }
    
    # Check if it's an ETF
    if symbol.upper() in etf_type_map:
        return GenericInstrumentEngine(etf_type_map[symbol.upper()])
    
    # Check if it's a known stock
    elif symbol.upper() in stock_type_map:
        return GenericInstrumentEngine(stock_type_map[symbol.upper()])
    
    # Default to tech large cap for unknown stocks (most common)
    else:
        return GenericInstrumentEngine(InstrumentType.TECH_LARGE)

# Utility function to get available instrument types
def get_available_instrument_types() -> List[Dict[str, str]]:
    """Get list of available instrument types with metadata"""
    instrument_list = []
    for instrument_type in InstrumentType:
        config = ALL_CONFIGS[instrument_type]
        category = "ETF" if instrument_type in ETF_CONFIGS else "Stock"
        instrument_list.append({
            'symbol': instrument_type.value,
            'display_name': instrument_type.value.upper(),
            'description': f"{instrument_type.value.upper()} - {category}",
            'category': category,
            'volatility_threshold': config.volatility_expansion_threshold,
            'risk_off_downtrend': config.risk_off_downtrend,
            'rsi_oversold': config.rsi_oversold,
            'rsi_overbought': config.rsi_overbought
        })
    return instrument_list

# Utility function to get stock examples by type
def get_stock_examples() -> Dict[str, List[str]]:
    """Get example stocks for each stock type"""
    return {
        'tech_large': ['AAPL', 'MSFT', 'GOOGL', 'GOOG'],
        'tech_growth': ['NVDA', 'TSLA', 'META', 'AMD'],
        'tech_value': ['INTC', 'IBM', 'CSCO'],
        'finance': ['JPM', 'BAC', 'WFC', 'GS'],
        'healthcare': ['JNJ', 'PFE', 'UNH', 'ABBV'],
        'consumer': ['AMZN', 'HD', 'MCD', 'NKE'],
        'energy': ['XOM', 'CVX', 'COP', 'SLB'],
        'industrial': ['CAT', 'DE', 'BA', 'GE']
    }
