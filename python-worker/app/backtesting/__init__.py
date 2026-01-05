"""
Backtesting Package
Comprehensive backtesting framework for signal engine validation
"""

from .tqqq_backtester import (
    TQQQBacktester,
    BacktestConfig,
    BacktestPeriod,
    BacktestResult,
    TradeResult
)

__all__ = [
    'TQQQBacktester',
    'BacktestConfig',
    'BacktestPeriod', 
    'BacktestResult',
    'TradeResult'
]
