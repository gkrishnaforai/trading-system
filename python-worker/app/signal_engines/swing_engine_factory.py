"""
Swing Trading Engine Factory
Manages both generic and TQQQ-specific swing trading engines
"""

from typing import Dict, Any, Optional, List
from enum import Enum

from app.signal_engines.base import BaseSignalEngine, EngineTier
from app.signal_engines.generic_swing_engine import GenericSwingEngine
from app.signal_engines.tqqq_swing_engine import TQQQSwingEngine
from app.observability.logging import get_logger

logger = get_logger(__name__)


class SwingEngineType(Enum):
    """Available swing trading engine types"""
    GENERIC = "generic_swing_trader"
    TQQQ = "tqqq_swing_trader"


class SwingEngineFactory:
    """
    Factory for creating and managing swing trading engines
    
    Provides:
    - Engine selection based on symbol characteristics
    - Proper engine initialization
    - Engine metadata and capabilities
    """
    
    def __init__(self):
        self._engines: Dict[SwingEngineType, BaseSignalEngine] = {}
        self._initialize_engines()
    
    def _initialize_engines(self):
        """Initialize all available swing trading engines"""
        try:
            # Initialize generic swing engine
            generic_engine = GenericSwingEngine()
            self._engines[SwingEngineType.GENERIC] = generic_engine
            logger.info(f"✅ Initialized {generic_engine.name}")
            
            # Initialize TQQQ-specific engine
            tqqq_engine = TQQQSwingEngine()
            self._engines[SwingEngineType.TQQQ] = tqqq_engine
            logger.info(f"✅ Initialized {tqqq_engine.name}")
            
        except Exception as e:
            logger.error(f"Error initializing swing engines: {e}")
    
    def get_engine_for_symbol(self, symbol: str) -> BaseSignalEngine:
        """
        Get the appropriate swing trading engine for a symbol
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Best suited swing trading engine for the symbol
        """
        symbol_upper = symbol.upper()
        
        # TQQQ gets specialized engine
        if symbol_upper == "TQQQ":
            engine = self._engines[SwingEngineType.TQQQ]
            logger.info(f"🎯 Selected TQQQ-specific engine for {symbol}")
            return engine
        
        # All other symbols get generic engine
        engine = self._engines[SwingEngineType.GENERIC]
        logger.info(f"📊 Selected generic swing engine for {symbol}")
        return engine
    
    def get_engine(self, engine_type: SwingEngineType) -> Optional[BaseSignalEngine]:
        """
        Get a specific engine by type
        
        Args:
            engine_type: Type of engine to retrieve
            
        Returns:
            Engine instance or None if not found
        """
        return self._engines.get(engine_type)
    
    def list_available_engines(self) -> List[Dict[str, Any]]:
        """
        Get list of all available swing trading engines with metadata
        
        Returns:
            List of engine information dictionaries
        """
        engines_info = []
        
        for engine_type, engine in self._engines.items():
            metadata = engine.get_metadata()
            engines_info.append({
                "type": engine_type.value,
                "name": engine.name,
                "version": engine.version,
                "tier": engine.tier.value,
                "description": engine.description,
                "config": metadata.get("config", {}),
                "warnings": metadata.get("warnings", []),
                "required_data_period": str(engine.get_required_data_period())
            })
        
        return engines_info
    
    def validate_symbol_engine_compatibility(self, symbol: str, engine_type: SwingEngineType) -> tuple[bool, List[str]]:
        """
        Validate if a symbol is compatible with a specific engine
        
        Args:
            symbol: Stock symbol
            engine_type: Engine type to validate against
            
        Returns:
            Tuple of (is_compatible, list_of_issues)
        """
        issues = []
        
        if engine_type == SwingEngineType.TQQQ:
            if symbol.upper() != "TQQQ":
                issues.append(f"TQQQ engine only processes TQQQ, not {symbol}")
        
        elif engine_type == SwingEngineType.GENERIC:
            if symbol.upper() == "TQQQ":
                issues.append("Use TQQQ-specific engine for TQQQ, not generic engine")
        
        return len(issues) == 0, issues
    
    def get_engine_recommendations(self, symbol: str) -> Dict[str, Any]:
        """
        Get engine recommendations for a symbol
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with recommendations and reasoning
        """
        symbol_upper = symbol.upper()
        
        if symbol_upper == "TQQQ":
            return {
                "recommended_engine": SwingEngineType.TQQQ.value,
                "alternative_engine": None,
                "reasoning": [
                    "TQQQ requires specialized handling due to leverage decay",
                    "Volatility clustering affects TQQQ differently",
                    "QQQ correlation and VIX monitoring required",
                    "Shorter holding periods minimize decay risk"
                ],
                "warnings": [
                    "High volatility instrument - not for beginners",
                    "Should sit in cash 30-50% of the time",
                    "Requires VIX and QQQ correlation monitoring"
                ]
            }
        else:
            return {
                "recommended_engine": SwingEngineType.GENERIC.value,
                "alternative_engine": None,
                "reasoning": [
                    "Standard swing trading principles apply",
                    "No leverage decay concerns",
                    "Normal risk management parameters",
                    "Suitable for 2-10 day holding periods"
                ],
                "warnings": [
                    "Not suitable for leveraged ETFs",
                    "Standard market risks apply"
                ]
            }
    
    def get_engine_performance_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics for all engines
        
        Returns:
            Dictionary with engine performance data
        """
        stats = {}
        
        for engine_type, engine in self._engines.items():
            # This would be populated with actual performance metrics
            # from backtesting or live trading results
            stats[engine_type.value] = {
                "total_signals": 0,  # Would be populated from database
                "success_rate": 0.0,
                "avg_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "last_updated": None
            }
        
        return stats


# Global factory instance
_swing_engine_factory: Optional[SwingEngineFactory] = None


def get_swing_engine_factory() -> SwingEngineFactory:
    """Get the global swing engine factory instance"""
    global _swing_engine_factory
    if _swing_engine_factory is None:
        _swing_engine_factory = SwingEngineFactory()
    return _swing_engine_factory


def get_swing_engine_for_symbol(symbol: str) -> BaseSignalEngine:
    """Convenience function to get the best swing engine for a symbol"""
    factory = get_swing_engine_factory()
    return factory.get_engine_for_symbol(symbol)


def list_swing_engines() -> List[Dict[str, Any]]:
    """Convenience function to list all available swing engines"""
    factory = get_swing_engine_factory()
    return factory.list_available_engines()
