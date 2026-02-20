"""
Adaptive Backtesting Framework
Implements comprehensive backtesting for adaptive signal system across market cycles
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import pandas as pd
import logging

from sqlalchemy import text
from app.signal_engines.adaptive_signal_engine import AdaptiveSignalEngine, SignalScore
from app.services.market_regime_service import MarketRegimeService, MarketRegime
from app.database import db
from app.observability.logging import get_logger

logger = get_logger(__name__)

@dataclass
class BacktestTrade:
    symbol: str
    entry_date: datetime
    exit_date: Optional[datetime]
    entry_price: float
    exit_price: Optional[float]
    signal_type: str
    quantity: int
    pnl: Optional[float]
    pnl_pct: Optional[float]
    holding_days: Optional[int]
    exit_reason: str
    market_regime: str
    volatility_profile: str
    relative_strength: str

@dataclass
class BacktestResults:
    period_name: str
    start_date: str
    end_date: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_holding_period: float
    regime_performance: Dict[str, float]
    volatility_performance: Dict[str, float]
    rs_performance: Dict[str, float]
    trades: List[BacktestTrade]

class AdaptiveBacktester:
    """Comprehensive backtesting framework for adaptive signal system"""
    
    def __init__(self):
        self.adaptive_engine = AdaptiveSignalEngine()
        self.regime_service = MarketRegimeService()
        
        # Test periods covering different market conditions
        self.test_periods = [
            ("2018-01-01", "2018-12-31", "2018 Volatility Spike"),
            ("2020-01-01", "2020-12-31", "COVID Crash & Recovery"),
            ("2021-01-01", "2021-12-31", "2021 Bull Market"),
            ("2022-01-01", "2022-12-31", "2022 Bear Market"),
            ("2023-01-01", "2024-12-31", "AI Cycle & Recovery")
        ]
        
        # Test symbols (diverse universe)
        self.test_symbols = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META',  # Tech Large
            'NVDA', 'TSLA', 'AMD', 'NFLX', 'CRM',      # Tech Growth
            'JPM', 'BAC', 'WFC', 'GS', 'C',            # Finance
            'JNJ', 'PFE', 'UNH', 'ABBV', 'MDT',        # Healthcare
            'XOM', 'CVX', 'COP', 'SLB', 'EOG',        # Energy
            'SPY', 'QQQ', 'IWM', 'GLD'                 # ETFs
        ]
    
    def run_comprehensive_backtest(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run comprehensive backtest across all test periods"""
        
        if symbols is None:
            symbols = self.test_symbols
        
        logger.info(f"Starting comprehensive backtest for {len(symbols)} symbols across {len(self.test_periods)} periods")
        
        all_results = {}
        
        for start_date, end_date, period_name in self.test_periods:
            logger.info(f"Backtesting period: {period_name} ({start_date} to {end_date})")
            
            try:
                period_results = self._run_period_backtest(symbols, start_date, end_date)
                all_results[period_name] = period_results
                
                logger.info(f"Completed {period_name}: Return {period_results.total_return:.2%}, Sharpe {period_results.sharpe_ratio:.2f}")
                
            except Exception as e:
                logger.error(f"Error in period {period_name}: {e}")
                all_results[period_name] = None
        
        # Analyze robustness
        robustness_analysis = self._analyze_robustness(all_results)
        
        return {
            'period_results': all_results,
            'robustness_analysis': robustness_analysis,
            'summary': self._generate_summary(all_results, robustness_analysis)
        }
    
    def _run_period_backtest(self, symbols: List[str], start_date: str, end_date: str) -> BacktestResults:
        """Run backtest for specific period"""
        
        trades = []
        equity_curve = [100000]  # Starting with $100k
        dates = []
        
        # Process each symbol
        for symbol in symbols:
            try:
                symbol_trades = self._backtest_symbol(symbol, start_date, end_date)
                trades.extend(symbol_trades)
                
            except Exception as e:
                logger.warning(f"Error backtesting {symbol}: {e}")
                continue
        
        # Calculate performance metrics
        if not trades:
            return self._create_empty_results(start_date, end_date)
        
        # Sort trades by date
        trades.sort(key=lambda t: t.entry_date)
        
        # Calculate equity curve
        equity_curve, dates = self._calculate_equity_curve(trades)
        
        # Calculate metrics
        total_return = (equity_curve[-1] / equity_curve[0]) - 1
        sharpe_ratio = self._calculate_sharpe_ratio(equity_curve, dates)
        max_drawdown = self._calculate_max_drawdown(equity_curve)
        win_rate = self._calculate_win_rate(trades)
        profit_factor = self._calculate_profit_factor(trades)
        
        # Analyze performance by dimensions
        regime_performance = self._analyze_performance_by_dimension(trades, 'market_regime')
        volatility_performance = self._analyze_performance_by_dimension(trades, 'volatility_profile')
        rs_performance = self._analyze_performance_by_dimension(trades, 'relative_strength')
        
        # Calculate holding period
        completed_trades = [t for t in trades if t.exit_date is not None]
        avg_holding_period = sum(t.holding_days for t in completed_trades) / len(completed_trades) if completed_trades else 0
        
        return BacktestResults(
            period_name=f"{start_date} to {end_date}",
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=len(trades),
            winning_trades=len([t for t in trades if t.pnl and t.pnl > 0]),
            losing_trades=len([t for t in trades if t.pnl and t.pnl < 0]),
            avg_holding_period=avg_holding_period,
            regime_performance=regime_performance,
            volatility_performance=volatility_performance,
            rs_performance=rs_performance,
            trades=trades
        )
    
    def _backtest_symbol(self, symbol: str, start_date: str, end_date: str) -> List[BacktestTrade]:
        """Backtest a single symbol"""
        
        trades = []
        
        try:
            with db.get_session() as session:
                # Get daily data for the period
                query = """
                SELECT 
                    r.date,
                    r.close,
                    r.high,
                    r.low,
                    r.volume,
                    i.rsi_14,
                    i.sma_20,
                    i.sma_50,
                    i.sma_200,
                    i.ema_20,
                    i.macd,
                    i.macd_signal,
                    i.atr
                FROM raw_market_data_daily r
                LEFT JOIN indicators_daily i ON r.symbol = i.symbol AND r.date = i.date
                WHERE r.symbol = :symbol
                AND r.date BETWEEN :start_date AND :end_date
                ORDER BY r.date
                """
                
                result = session.execute(text(query), {
                    "symbol": symbol,
                    "start_date": start_date,
                    "end_date": end_date
                })
                
                rows = result.fetchall()
                
                if len(rows) < 30:
                    logger.warning(f"Insufficient data for {symbol} in period {start_date} to {end_date}")
                    return trades
                
                # Convert to DataFrame for easier processing
                df = pd.DataFrame(rows, columns=[
                    'date', 'close', 'high', 'low', 'volume', 'rsi', 'sma20', 'sma50', 
                    'sma200', 'ema20', 'macd', 'macd_signal', 'atr'
                ])
                
                # Process each day
                for i in range(20, len(df)):  # Start after enough data for indicators
                    row = df.iloc[i]
                    prev_row = df.iloc[i-1]
                    
                    # Calculate recent change
                    recent_change = (row['close'] - prev_row['close']) / prev_row['close']
                    
                    # Create market conditions
                    from app.signal_engines.signal_calculator_core import MarketConditions
                    conditions = MarketConditions(
                        rsi=row['rsi'],
                        sma_20=row['sma20'],
                        sma_50=row['sma50'],
                        ema_20=row['ema20'],
                        current_price=row['close'],
                        recent_change=recent_change,
                        macd=row['macd'],
                        macd_signal=row['macd_signal'],
                        volatility=0.0,  # Will be calculated if needed
                        vix_level=0.0,
                        volume=row['volume'],
                        avg_volume_20d=df['volume'].iloc[max(0, i-20):i].mean(),
                        atr=row['atr']
                    )
                    
                    # Generate signal
                    signal_score = self.adaptive_engine.generate_signal_score(symbol, conditions)
                    primary_signal = signal_score.get_primary_signal().value
                    
                    # Get market context
                    market_regime = signal_score.metadata.get('market_regime', 'unknown')
                    vol_profile = signal_score.metadata.get('volatility_profile', 'unknown')
                    rs_tier = signal_score.metadata.get('relative_strength', 'unknown')
                    
                    # Simple trading logic (can be enhanced)
                    if primary_signal in ['BUY', 'SELL'] and signal_score.confidence > 0.6:
                        # Check if we already have an open position
                        open_trades = [t for t in trades if t.exit_date is None]
                        
                        if not open_trades:  # No open position
                            # Enter new position
                            trade = BacktestTrade(
                                symbol=symbol,
                                entry_date=row['date'],
                                exit_date=None,
                                entry_price=row['close'],
                                exit_price=None,
                                signal_type=primary_signal,
                                quantity=100,  # Fixed quantity for simplicity
                                pnl=None,
                                pnl_pct=None,
                                holding_days=None,
                                exit_reason='open',
                                market_regime=market_regime,
                                volatility_profile=vol_profile,
                                relative_strength=rs_tier
                            )
                            trades.append(trade)
                        
                        elif (open_trades[0].signal_type == 'BUY' and primary_signal == 'SELL') or \
                             (open_trades[0].signal_type == 'SELL' and primary_signal == 'BUY'):
                            # Close existing position
                            open_trade = open_trades[0]
                            open_trade.exit_date = row['date']
                            open_trade.exit_price = row['close']
                            open_trade.exit_reason = f'signal_change_to_{primary_signal}'
                            
                            # Calculate P&L
                            if open_trade.signal_type == 'BUY':
                                open_trade.pnl = (open_trade.exit_price - open_trade.entry_price) * open_trade.quantity
                            else:  # SELL
                                open_trade.pnl = (open_trade.entry_price - open_trade.exit_price) * open_trade.quantity
                            
                            open_trade.pnl_pct = open_trade.pnl / (open_trade.entry_price * open_trade.quantity)
                            open_trade.holding_days = (open_trade.exit_date - open_trade.entry_date).days
                
        except Exception as e:
            logger.error(f"Error backtesting {symbol}: {e}")
        
        return trades
    
    def _calculate_equity_curve(self, trades: List[BacktestTrade]) -> Tuple[List[float], List[datetime]]:
        """Calculate equity curve from trades"""
        
        if not trades:
            return [100000], [datetime.now()]
        
        # Sort trades by entry date
        trades.sort(key=lambda t: t.entry_date)
        
        equity = [100000]
        dates = [trades[0].entry_date]
        
        for trade in trades:
            if trade.pnl is not None:
                new_equity = equity[-1] + trade.pnl
                equity.append(new_equity)
                dates.append(trade.exit_date or trade.entry_date)
        
        return equity, dates
    
    def _calculate_sharpe_ratio(self, equity_curve: List[float], dates: List[datetime]) -> float:
        """Calculate Sharpe ratio"""
        
        if len(equity_curve) < 2:
            return 0.0
        
        # Calculate daily returns
        returns = []
        for i in range(1, len(equity_curve)):
            ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
            returns.append(ret)
        
        if not returns:
            return 0.0
        
        # Calculate Sharpe ratio (assuming 252 trading days per year)
        avg_return = sum(returns) / len(returns)
        variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
        
        if variance == 0:
            return 0.0
        
        sharpe = (avg_return / (variance ** 0.5)) * (252 ** 0.5)
        
        return sharpe
    
    def _calculate_max_drawdown(self, equity_curve: List[float]) -> float:
        """Calculate maximum drawdown"""
        
        if len(equity_curve) < 2:
            return 0.0
        
        max_drawdown = 0.0
        peak = equity_curve[0]
        
        for value in equity_curve:
            if value > peak:
                peak = value
            
            drawdown = (peak - value) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return max_drawdown
    
    def _calculate_win_rate(self, trades: List[BacktestTrade]) -> float:
        """Calculate win rate"""
        
        completed_trades = [t for t in trades if t.pnl is not None]
        
        if not completed_trades:
            return 0.0
        
        winning_trades = len([t for t in completed_trades if t.pnl > 0])
        
        return winning_trades / len(completed_trades)
    
    def _calculate_profit_factor(self, trades: List[BacktestTrade]) -> float:
        """Calculate profit factor (gross profit / gross loss)"""
        
        completed_trades = [t for t in trades if t.pnl is not None]
        
        if not completed_trades:
            return 0.0
        
        gross_profit = sum(t.pnl for t in completed_trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in completed_trades if t.pnl < 0))
        
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        
        return gross_profit / gross_loss
    
    def _analyze_performance_by_dimension(self, trades: List[BacktestTrade], dimension: str) -> Dict[str, float]:
        """Analyze performance by dimension (regime, volatility, relative strength)"""
        
        completed_trades = [t for t in trades if t.pnl is not None]
        
        if not completed_trades:
            return {}
        
        # Group by dimension value
        dimension_groups = {}
        for trade in completed_trades:
            dim_value = getattr(trade, dimension, 'unknown')
            if dim_value not in dimension_groups:
                dimension_groups[dim_value] = []
            dimension_groups[dim_value].append(trade)
        
        # Calculate performance for each group
        performance = {}
        for dim_value, group_trades in dimension_groups.items():
            total_pnl = sum(t.pnl for t in group_trades)
            total_return = total_pnl / (sum(t.entry_price * t.quantity for t in group_trades))
            win_rate = len([t for t in group_trades if t.pnl > 0]) / len(group_trades)
            
            performance[dim_value] = {
                'total_return': total_return,
                'win_rate': win_rate,
                'trade_count': len(group_trades)
            }
        
        return performance
    
    def _create_empty_results(self, start_date: str, end_date: str) -> BacktestResults:
        """Create empty results for periods with no trades"""
        return BacktestResults(
            period_name=f"{start_date} to {end_date}",
            start_date=start_date,
            end_date=end_date,
            total_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            avg_holding_period=0.0,
            regime_performance={},
            volatility_performance={},
            rs_performance={},
            trades=[]
        )
    
    def _analyze_robustness(self, all_results: Dict[str, Optional[BacktestResults]]) -> Dict[str, Any]:
        """Analyze system robustness across all periods"""
        
        valid_results = {k: v for k, v in all_results.items() if v is not None}
        
        if not valid_results:
            return {'robustness_score': 0.0, 'recommendation': 'NO_DATA'}
        
        # Check robustness criteria
        criteria_met = 0
        total_criteria = 6
        
        # 1. Positive returns in most periods
        positive_periods = len([r for r in valid_results.values() if r.total_return > 0])
        if positive_periods >= len(valid_results) * 0.6:  # 60% of periods
            criteria_met += 1
        
        # 2. Reasonable max drawdown
        max_drawdowns = [r.max_drawdown for r in valid_results.values()]
        if all(dd < 0.30 for dd in max_drawdowns):  # Less than 30% drawdown
            criteria_met += 1
        
        # 3. Positive Sharpe ratio
        positive_sharpes = len([r for r in valid_results.values() if r.sharpe_ratio > 0])
        if positive_sharpes >= len(valid_results) * 0.6:
            criteria_met += 1
        
        # 4. Reasonable win rate
        win_rates = [r.win_rate for r in valid_results.values() if r.win_rate > 0]
        if win_rates and sum(win_rates) / len(win_rates) > 0.4:  # Average > 40%
            criteria_met += 1
        
        # 5. Profit factor > 1
        profit_factors = [r.profit_factor for r in valid_results.values() if r.profit_factor > 0]
        if profit_factors and sum(profit_factors) / len(profit_factors) > 1.0:
            criteria_met += 1
        
        # 6. Consistent performance across regimes
        regime_consistency = self._check_regime_consistency(valid_results)
        if regime_consistency:
            criteria_met += 1
        
        robustness_score = criteria_met / total_criteria
        
        recommendation = "ROBUST" if robustness_score >= 0.8 else \
                        "MODERATE" if robustness_score >= 0.6 else \
                        "WEAK" if robustness_score >= 0.4 else "NEEDS_IMPROVEMENT"
        
        return {
            'robustness_score': robustness_score,
            'criteria_met': criteria_met,
            'total_criteria': total_criteria,
            'recommendation': recommendation,
            'period_analysis': self._analyze_period_performance(valid_results)
        }
    
    def _check_regime_consistency(self, results: Dict[str, BacktestResults]) -> bool:
        """Check if performance is consistent across different market regimes"""
        
        # Collect regime performance across all periods
        all_regime_performance = {}
        
        for result in results.values():
            for regime, perf in result.regime_performance.items():
                if regime not in all_regime_performance:
                    all_regime_performance[regime] = []
                all_regime_performance[regime].append(perf['total_return'])
        
        # Check if most regimes have positive performance
        positive_regimes = 0
        for regime, returns in all_regime_performance.items():
            if len(returns) > 0 and sum(returns) / len(returns) > 0:
                positive_regimes += 1
        
        return positive_regimes >= len(all_regime_performance) * 0.6
    
    def _analyze_period_performance(self, results: Dict[str, BacktestResults]) -> Dict[str, Any]:
        """Analyze performance characteristics across periods"""
        
        returns = [r.total_return for r in results.values()]
        sharpe_ratios = [r.sharpe_ratio for r in results.values()]
        max_drawdowns = [r.max_drawdown for r in results.values()]
        
        return {
            'avg_return': sum(returns) / len(returns) if returns else 0,
            'return_std': self._calculate_std(returns),
            'avg_sharpe': sum(sharpe_ratios) / len(sharpe_ratios) if sharpe_ratios else 0,
            'avg_max_drawdown': sum(max_drawdowns) / len(max_drawdowns) if max_drawdowns else 0,
            'best_period': max(results.keys(), key=lambda k: results[k].total_return) if results else None,
            'worst_period': min(results.keys(), key=lambda k: results[k].total_return) if results else None
        }
    
    def _calculate_std(self, values: List[float]) -> float:
        """Calculate standard deviation"""
        if len(values) < 2:
            return 0.0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        
        return variance ** 0.5
    
    def _generate_summary(self, all_results: Dict[str, Optional[BacktestResults]], 
                         robustness: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary of backtest results"""
        
        valid_results = {k: v for k, v in all_results.items() if v is not None}
        
        if not valid_results:
            return {'status': 'NO_VALID_RESULTS'}
        
        # Overall metrics
        total_trades = sum(r.total_trades for r in valid_results.values())
        total_return = sum(r.total_return for r in valid_results.values()) / len(valid_results)
        avg_sharpe = sum(r.sharpe_ratio for r in valid_results.values()) / len(valid_results)
        max_drawdown = max(r.max_drawdown for r in valid_results.values())
        
        # Best and worst periods
        best_period = max(valid_results.items(), key=lambda x: x[1].total_return)
        worst_period = min(valid_results.items(), key=lambda x: x[1].total_return)
        
        return {
            'status': 'SUCCESS',
            'periods_tested': len(valid_results),
            'total_trades': total_trades,
            'avg_annual_return': total_return,
            'avg_sharpe_ratio': avg_sharpe,
            'max_drawdown': max_drawdown,
            'robustness_score': robustness['robustness_score'],
            'recommendation': robustness['recommendation'],
            'best_period': {
                'name': best_period[0],
                'return': best_period[1].total_return
            },
            'worst_period': {
                'name': worst_period[0],
                'return': worst_period[1].total_return
            }
        }
