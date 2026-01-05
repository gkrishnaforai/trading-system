"""
Signal Engines Package
Multi-engine stock signal system with pluggable architecture
"""

from .base import BaseSignalEngine, SignalResult, MarketContext, SignalType
from .factory import SignalEngineFactory
from .generic_swing_engine import GenericSwingEngine, SwingRegime
from .tqqq_swing_engine import TQQQSwingEngine, TQQQRegime
from .swing_engine_factory import SwingEngineFactory, SwingEngineType, get_swing_engine_factory, get_swing_engine_for_symbol

__all__ = [
    'BaseSignalEngine',
    'SignalResult', 
    'MarketContext',
    'SignalType',
    'SignalEngineFactory',
    'GenericSwingEngine',
    'SwingRegime',
    'TQQQSwingEngine',
    'TQQQRegime',
    'SwingEngineFactory',
    'SwingEngineType',
    'get_swing_engine_factory',
    'get_swing_engine_for_symbol'
]
