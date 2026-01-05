"""
Base Signal Engine Interface and Data Structures
Defines the contract all signal engines must follow
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd

from app.observability.logging import get_logger

logger = get_logger(__name__)


class SignalType(Enum):
    """Signal types supported by engines"""
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


class MarketRegime(Enum):
    """Market regime classification"""
    BULL = "BULL"
    BEAR = "BEAR"
    HIGH_VOL_CHOP = "HIGH_VOL_CHOP"
    NO_TRADE = "NO_TRADE"


class EngineTier(Enum):
    """Engine access tiers"""
    BASIC = "BASIC"
    PRO = "PRO"
    ELITE = "ELITE"


@dataclass
class MarketContext:
    """Shared market state for all engines"""
    regime: MarketRegime
    regime_confidence: float
    vix: float
    nasdaq_trend: str  # "bullish" | "bearish" | "neutral"
    sector_rotation: Dict[str, float] = field(default_factory=dict)
    breadth: float = 0.0  # % stocks above 50-day MA
    yield_curve_spread: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SignalResult:
    """Unified signal output from any engine"""
    engine_name: str
    engine_version: str
    engine_tier: EngineTier
    symbol: str
    signal: SignalType
    confidence: float  # 0.0 - 1.0
    position_size_pct: float  # Recommended allocation %
    timeframe: str  # "swing" | "position" | "day"
    entry_price_range: Optional[Tuple[float, float]]
    stop_loss: Optional[float]
    take_profit: List[float] = field(default_factory=list)
    reasoning: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(days=1))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'engine_name': self.engine_name,
            'engine_version': self.engine_version,
            'engine_tier': self.engine_tier.value,
            'symbol': self.symbol,
            'signal': self.signal.value,
            'confidence': self.confidence,
            'position_size_pct': self.position_size_pct,
            'timeframe': self.timeframe,
            'entry_price_range': self.entry_price_range,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'reasoning': self.reasoning,
            'metadata': self.metadata,
            'generated_at': self.generated_at.isoformat(),
            'expires_at': self.expires_at.isoformat()
        }


def _parse_engine_tier(value: Any) -> EngineTier:
    if isinstance(value, EngineTier):
        return value
    if isinstance(value, str):
        key = value.strip().upper()
        if key in EngineTier.__members__:
            return EngineTier[key]
    return EngineTier.BASIC


class SignalEngineError(Exception):
    """Base exception for signal engine errors"""
    def __init__(self, message: str, engine_name: str = None, symbol: str = None, **context):
        super().__init__(message)
        self.engine_name = engine_name
        self.symbol = symbol
        self.context = context
        logger.error(f"SignalEngineError in {engine_name} for {symbol}: {message}", 
                    extra={'engine_name': engine_name, 'symbol': symbol, **context})


class InsufficientDataError(SignalEngineError):
    """Raised when required data is missing"""
    pass


class ModelPredictionError(SignalEngineError):
    """Raised when ML model prediction fails"""
    pass


class BaseSignalEngine(ABC):
    """Abstract base for all signal engines"""
    
    def __init__(self):
        """Initialize signal engine"""
        self.logger = get_logger(f"{self.__class__.__name__}")
        self.engine_name = self.__class__.__name__.replace('Engine', '').lower()
        self.engine_version = "1.0.0"
    
    @abstractmethod
    def generate_signal(
        self,
        symbol: str,
        market_data: pd.DataFrame,
        indicators: Dict[str, Any],
        fundamentals: Dict[str, Any],
        market_context: MarketContext
    ) -> SignalResult:
        """Generate signal for a single symbol"""
        pass
    
    @abstractmethod
    def get_engine_metadata(self) -> Dict[str, Any]:
        """Return engine name, version, description, tier"""
        pass
    
    def validate_inputs(
        self,
        symbol: str,
        market_data: pd.DataFrame,
        indicators: Dict[str, Any],
        fundamentals: Dict[str, Any],
        market_context: MarketContext
    ) -> bool:
        """Check if required data is available"""
        try:
            if not symbol:
                raise InsufficientDataError("Symbol is required", self.engine_name)
            
            if market_data is None or len(market_data) == 0:
                raise InsufficientDataError("Market data is required", self.engine_name, symbol)
            
            if indicators is None:
                raise InsufficientDataError("Indicators are required", self.engine_name, symbol)
            
            if market_context is None:
                raise InsufficientDataError("Market context is required", self.engine_name, symbol)
            
            # Check minimum data length for technical analysis
            if len(market_data) < 20:
                self.logger.warning(f"Insufficient market data length for {symbol}: {len(market_data)} < 20")
                return False
            
            return True
            
        except InsufficientDataError:
            raise
        except Exception as e:
            raise SignalEngineError(f"Input validation failed: {str(e)}", self.engine_name, symbol)
    
    def get_required_indicators(self) -> List[str]:
        """Return list of required indicators for this engine"""
        return ['price', 'volume', 'rsi', 'macd', 'sma50', 'sma200', 'ema20']
    
    def get_required_fundamentals(self) -> List[str]:
        """Return list of required fundamentals for this engine"""
        return ['sector', 'market_cap']
    
    def _calculate_confidence_from_score(self, score: float) -> float:
        """Convert internal score to confidence (0-1)"""
        return max(0.0, min(1.0, score))
    
    def _create_signal_result(
        self,
        symbol: str,
        signal: SignalType,
        confidence: float,
        reasoning: List[str],
        **kwargs
    ) -> SignalResult:
        """Create SignalResult with common fields"""
        metadata = self.get_engine_metadata()
        
        return SignalResult(
            engine_name=self.engine_name,
            engine_version=self.engine_version,
            engine_tier=_parse_engine_tier(metadata.get('tier', EngineTier.BASIC)),
            symbol=symbol,
            signal=signal,
            confidence=self._calculate_confidence_from_score(confidence),
            timeframe=kwargs.get('timeframe', 'position'),
            reasoning=reasoning,
            metadata=kwargs.get('metadata', {}),
            **{k: v for k, v in kwargs.items() if k not in ['timeframe', 'metadata']}
        )
