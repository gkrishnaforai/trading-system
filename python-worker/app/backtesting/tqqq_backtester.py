"""
TQQQ Swing Engine Backtesting System
Comprehensive backtesting framework for validating TQQQ swing trading strategies
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import pandas as pd
import numpy as np
from dataclasses import dataclass

from app.signal_engines.tqqq_swing_engine import TQQQSwingEngine, TQQQRegime
from app.signal_engines.base import SignalResult, SignalType, MarketContext, MarketRegime
from app.utils.database_helper import DatabaseQueryHelper
from app.observability.logging import get_logger

logger = get_logger(__name__)


class BacktestPeriod(Enum):
    """Predefined backtest periods"""
    LAST_MONTH = "1_month"
    LAST_QUARTER = "3_months"
    LAST_SEMI_ANNUAL = "6_months"
    LAST_YEAR = "1_year"
    YEAR_TO_DATE = "ytd"
    CUSTOM = "custom"


@dataclass
class BacktestConfig:
    """Configuration for backtesting"""
    period: BacktestPeriod = BacktestPeriod.LAST_YEAR
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    initial_capital: float = 10000.0
    position_size_pct: float = 0.015  # 1.5% per trade (TQQQ default)
    max_positions: int = 1  # TQQQ only one position at a time
    include_commission: bool = True
    commission_rate: float = 0.001  # 0.1% per trade
    slippage: float = 0.0005  # 0.05% slippage


@dataclass
class TradeResult:
    """Result of a single trade"""
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    signal: SignalType
    exit_reason: str
    gross_pnl: float
    net_pnl: float
    return_pct: float
    holding_days: int
    regime_at_entry: str
    vix_at_entry: float
    confidence: float


@dataclass
class BacktestResult:
    """Complete backtest results"""
    config: BacktestConfig
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    avg_trade_return: float
    avg_winning_trade: float
    avg_losing_trade: float
    largest_win: float
    largest_loss: float
    profit_factor: float
    trades: List[TradeResult]
    equity_curve: List[Tuple[datetime, float]]
    regime_performance: Dict[str, Dict[str, Any]]
    monthly_returns: Dict[str, float]
    volatility_stats: Dict[str, float]


class TQQQBacktester:
    """
    TQQQ Swing Engine Backtesting System
    
    Provides comprehensive backtesting capabilities for the TQQQ swing trading engine
    with realistic market conditions, transaction costs, and performance metrics.
    """
    
    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()
        self.engine = TQQQSwingEngine()
        self.logger = get_logger(__name__)
    
    def run_backtest(self, symbol: str = "TQQQ") -> BacktestResult:
        """
        Run comprehensive backtest for TQQQ swing engine
        
        Args:
            symbol: Symbol to backtest (should be TQQQ)
            
        Returns:
            Complete backtest results with detailed metrics
        """
        try:
            # Get date range
            start_date, end_date = self._get_date_range()
            
            self.logger.info(f"🚀 Starting TQQQ backtest from {start_date.date()} to {end_date.date()}")
            
            # Load historical data
            tqqq_data, qqq_data, vix_data = self._load_historical_data(symbol, start_date, end_date)
            
            if tqqq_data.empty or qqq_data.empty or vix_data.empty:
                raise ValueError("Insufficient historical data for backtesting")
            
            # Generate signals for each day
            signals = self._generate_signals(tqqq_data, qqq_data, vix_data, start_date, end_date)
            
            # Execute trades and calculate performance
            trades, equity_curve = self._execute_trades(signals, tqqq_data)
            
            # Calculate performance metrics
            result = self._calculate_performance_metrics(trades, equity_curve, start_date, end_date)
            
            self.logger.info(f"✅ Backtest completed: {result.total_return:.2%} return, {result.win_rate:.1%} win rate")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Backtest failed: {e}")
            raise
    
    def _get_date_range(self) -> Tuple[datetime, datetime]:
        """Get start and end dates for backtest"""
        end_date = datetime.now()
        
        if self.config.period == BacktestPeriod.CUSTOM:
            if not self.config.start_date or not self.config.end_date:
                raise ValueError("Custom period requires start_date and end_date")
            return self.config.start_date, self.config.end_date
        
        # Calculate start date based on period
        period_days = {
            BacktestPeriod.LAST_MONTH: 30,
            BacktestPeriod.LAST_QUARTER: 90,
            BacktestPeriod.LAST_SEMI_ANNUAL: 180,
            BacktestPeriod.LAST_YEAR: 365,
            BacktestPeriod.YEAR_TO_DATE: datetime.now().timetuple().tm_yday
        }
        
        days = period_days.get(self.config.period, 365)
        start_date = end_date - timedelta(days=days)
        
        return start_date, end_date
    
    def _load_historical_data(self, symbol: str, start_date: datetime, end_date: datetime) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Load historical data for TQQQ, QQQ, and VIX"""
        try:
            # Load TQQQ data
            tqqq_data = DatabaseQueryHelper.get_historical_data(symbol, start_date.date(), end_date.date())
            if not tqqq_data:
                raise ValueError(f"No TQQQ data found for period {start_date.date()} to {end_date.date()}")
            
            tqqq_df = pd.DataFrame(tqqq_data)
            tqqq_df['date'] = pd.to_datetime(tqqq_df['date'])
            tqqq_df.set_index('date', inplace=True)
            
            # Load QQQ data
            qqq_data = DatabaseQueryHelper.get_historical_data("QQQ", start_date.date(), end_date.date())
            if not qqq_data:
                raise ValueError(f"No QQQ data found for period {start_date.date()} to {end_date.date()}")
            
            qqq_df = pd.DataFrame(qqq_data)
            qqq_df['date'] = pd.to_datetime(qqq_df['date'])
            qqq_df.set_index('date', inplace=True)
            
            # Load VIX data
            vix_data = DatabaseQueryHelper.get_historical_data("VIX", start_date.date(), end_date.date())
            if not vix_data:
                raise ValueError(f"No VIX data found for period {start_date.date()} to {end_date.date()}")
            
            vix_df = pd.DataFrame(vix_data)
            vix_df['date'] = pd.to_datetime(vix_df['date'])
            vix_df.set_index('date', inplace=True)
            
            self.logger.info(f"📊 Loaded data: TQQQ ({len(tqqq_df)} days), QQQ ({len(qqq_df)} days), VIX ({len(vix_df)} days)")
            
            return tqqq_df, qqq_df, vix_df
            
        except Exception as e:
            self.logger.error(f"Error loading historical data: {e}")
            raise
    
    def _generate_signals(self, tqqq_data: pd.DataFrame, qqq_data: pd.DataFrame, vix_data: pd.DataFrame,
                         start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Generate signals for each trading day"""
        signals = []
        
        # Create market context (simplified for backtest)
        market_context = MarketContext(
            current_date=start_date,
            market_regime=MarketRegime.NEUTRAL,
            vix=vix_data['close'].iloc[0] if not vix_data.empty else 20.0,
            spx_change=0.0,
            ndx_change=0.0,
            sector_performance={},
            macro_indicators={}
        )
        
        # Generate signal for each day
        for date in pd.date_range(start_date.date(), end_date.date(), freq='D'):
            if date.weekday() >= 5:  # Skip weekends
                continue
            
            if date not in tqqq_data.index:
                continue
            
            # Get data up to current date
            tqqq_hist = tqqq_data.loc[:date]
            qqq_hist = qqq_data.loc[:date] if date in qqq_data.index else qqq_data.loc[:date].iloc[-1:]
            vix_hist = vix_data.loc[:date] if date in vix_data.index else vix_data.loc[:date].iloc[-1:]
            
            if len(tqqq_hist) < 30:  # Need minimum data for engine
                continue
            
            # Update market context
            market_context.current_date = date
            if date in vix_data.index:
                market_context.vix = vix_data.loc[date, 'close']
            
            try:
                # Generate signal
                signal_result = self.engine.generate_signal("TQQQ", tqqq_hist, market_context)
                
                signals.append({
                    'date': date,
                    'signal': signal_result.signal,
                    'confidence': signal_result.confidence,
                    'entry_price_range': signal_result.entry_price_range,
                    'stop_loss': signal_result.stop_loss,
                    'take_profit': signal_result.take_profit,
                    'reasoning': signal_result.reasoning,
                    'metadata': signal_result.metadata,
                    'actual_price': tqqq_data.loc[date, 'close']
                })
                
            except Exception as e:
                self.logger.warning(f"Error generating signal for {date}: {e}")
                continue
        
        self.logger.info(f"🎯 Generated {len(signals)} signals for backtest")
        return signals
    
    def _execute_trades(self, signals: List[Dict[str, Any]], tqqq_data: pd.DataFrame) -> Tuple[List[TradeResult], List[Tuple[datetime, float]]]:
        """Execute trades based on signals and calculate equity curve"""
        trades = []
        equity_curve = []
        current_capital = self.config.initial_capital
        current_position = None
        
        for signal in signals:
            date = signal['date']
            signal_type = signal['signal']
            price = signal['actual_price']
            
            # Update equity curve
            if current_position:
                # Update position value
                unrealized_pnl = (price - current_position['entry_price']) * current_position['shares']
                current_value = current_capital + (current_position['shares'] * price)
            else:
                current_value = current_capital
            
            equity_curve.append((date, current_value))
            
            # Handle current position
            if current_position:
                # Check for exit conditions
                exit_triggered = False
                exit_reason = ""
                
                if signal_type == SignalType.SELL:
                    exit_triggered = True
                    exit_reason = "SELL signal"
                elif signal_type == SignalType.HOLD and current_position['signal'] == SignalType.BUY:
                    # Check stop loss
                    if current_position['stop_loss'] and price <= current_position['stop_loss']:
                        exit_triggered = True
                        exit_reason = "Stop loss hit"
                    # Check take profit
                    elif current_position['take_profit'] and price >= current_position['take_profit'][0]:
                        exit_triggered = True
                        exit_reason = "Take profit hit"
                    # Time-based exit (TQQQ specific)
                    elif (date - current_position['entry_date']).days >= 7:  # Max 7 days
                        exit_triggered = True
                        exit_reason = "Time exit (7 days max)"
                
                if exit_triggered:
                    # Close position
                    exit_price = price * (1 - self.config.slippage) if signal_type == SignalType.SELL else price
                    
                    # Calculate trade result
                    gross_pnl = (exit_price - current_position['entry_price']) * current_position['shares']
                    commission = self.config.commission_rate * (current_position['entry_price'] + exit_price) * current_position['shares'] if self.config.include_commission else 0
                    net_pnl = gross_pnl - commission
                    return_pct = net_pnl / (current_position['entry_price'] * current_position['shares'])
                    
                    trade_result = TradeResult(
                        entry_date=current_position['entry_date'],
                        exit_date=date,
                        entry_price=current_position['entry_price'],
                        exit_price=exit_price,
                        signal=current_position['signal'],
                        exit_reason=exit_reason,
                        gross_pnl=gross_pnl,
                        net_pnl=net_pnl,
                        return_pct=return_pct,
                        holding_days=(date - current_position['entry_date']).days,
                        regime_at_entry=current_position['regime'],
                        vix_at_entry=current_position['vix'],
                        confidence=current_position['confidence']
                    )
                    
                    trades.append(trade_result)
                    current_capital += net_pnl
                    current_position = None
            
            # Enter new position
            if signal_type == SignalType.BUY and not current_position:
                position_size = current_capital * self.config.position_size_pct
                shares = position_size / price
                
                current_position = {
                    'entry_date': date,
                    'entry_price': price * (1 + self.config.slippage),
                    'shares': shares,
                    'signal': signal_type,
                    'stop_loss': signal['stop_loss'],
                    'take_profit': signal['take_profit'],
                    'regime': signal['metadata'].get('regime', 'UNKNOWN'),
                    'vix': signal['metadata'].get('vix', 0),
                    'confidence': signal['confidence']
                }
        
        # Close any open position at the end
        if current_position:
            final_price = tqqq_data.iloc[-1]['close']
            gross_pnl = (final_price - current_position['entry_price']) * current_position['shares']
            commission = self.config.commission_rate * (current_position['entry_price'] + final_price) * current_position['shares'] if self.config.include_commission else 0
            net_pnl = gross_pnl - commission
            return_pct = net_pnl / (current_position['entry_price'] * current_position['shares'])
            
            trade_result = TradeResult(
                entry_date=current_position['entry_date'],
                exit_date=tqqq_data.index[-1],
                entry_price=current_position['entry_price'],
                exit_price=final_price,
                signal=current_position['signal'],
                exit_reason="End of backtest",
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                return_pct=return_pct,
                holding_days=(tqqq_data.index[-1] - current_position['entry_date']).days,
                regime_at_entry=current_position['regime'],
                vix_at_entry=current_position['vix'],
                confidence=current_position['confidence']
            )
            
            trades.append(trade_result)
            current_capital += net_pnl
        
        return trades, equity_curve
    
    def _calculate_performance_metrics(self, trades: List[TradeResult], equity_curve: List[Tuple[datetime, float]],
                                     start_date: datetime, end_date: datetime) -> BacktestResult:
        """Calculate comprehensive performance metrics"""
        
        if not trades:
            # Return empty result if no trades
            return BacktestResult(
                config=self.config,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_return=0.0,
                annualized_return=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                calmar_ratio=0.0,
                avg_trade_return=0.0,
                avg_winning_trade=0.0,
                avg_losing_trade=0.0,
                largest_win=0.0,
                largest_loss=0.0,
                profit_factor=0.0,
                trades=[],
                equity_curve=equity_curve,
                regime_performance={},
                monthly_returns={},
                volatility_stats={}
            )
        
        # Basic trade statistics
        winning_trades = [t for t in trades if t.net_pnl > 0]
        losing_trades = [t for t in trades if t.net_pnl <= 0]
        
        total_trades = len(trades)
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = win_count / total_trades if total_trades > 0 else 0
        
        # Return calculations
        total_return = (equity_curve[-1][1] - self.config.initial_capital) / self.config.initial_capital
        
        # Annualized return
        days = (end_date - start_date).days
        annualized_return = (1 + total_return) ** (365 / days) - 1 if days > 0 else 0
        
        # Drawdown calculation
        equity_values = [eq[1] for eq in equity_curve]
        peak = equity_values[0]
        max_drawdown = 0
        
        for value in equity_values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # Risk ratios
        daily_returns = pd.Series(equity_values).pct_change().dropna()
        sharpe_ratio = daily_returns.mean() / daily_returns.std() * np.sqrt(252) if daily_returns.std() > 0 else 0
        
        downside_returns = daily_returns[daily_returns < 0]
        sortino_ratio = daily_returns.mean() / downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 and downside_returns.std() > 0 else 0
        
        calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else 0
        
        # Trade statistics
        trade_returns = [t.return_pct for t in trades]
        avg_trade_return = np.mean(trade_returns) if trade_returns else 0
        avg_winning_trade = np.mean([t.return_pct for t in winning_trades]) if winning_trades else 0
        avg_losing_trade = np.mean([t.return_pct for t in losing_trades]) if losing_trades else 0
        
        largest_win = max([t.return_pct for t in winning_trades]) if winning_trades else 0
        largest_loss = min([t.return_pct for t in losing_trades]) if losing_trades else 0
        
        # Profit factor
        gross_profit = sum([t.gross_pnl for t in winning_trades])
        gross_loss = abs(sum([t.gross_pnl for t in losing_trades]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Regime performance
        regime_performance = {}
        for regime in set([t.regime_at_entry for t in trades]):
            regime_trades = [t for t in trades if t.regime_at_entry == regime]
            regime_wins = [t for t in regime_trades if t.net_pnl > 0]
            regime_performance[regime] = {
                'trades': len(regime_trades),
                'wins': len(regime_wins),
                'win_rate': len(regime_wins) / len(regime_trades) if regime_trades else 0,
                'avg_return': np.mean([t.return_pct for t in regime_trades]) if regime_trades else 0,
                'total_return': sum([t.net_pnl for t in regime_trades])
            }
        
        # Monthly returns
        monthly_returns = {}
        for trade in trades:
            month_key = trade.exit_date.strftime('%Y-%m')
            if month_key not in monthly_returns:
                monthly_returns[month_key] = 0
            monthly_returns[month_key] += trade.net_pnl
        
        # Normalize monthly returns
        for month in monthly_returns:
            monthly_returns[month] = monthly_returns[month] / self.config.initial_capital
        
        # Volatility statistics
        volatility_stats = {
            'daily_vol': daily_returns.std(),
            'annualized_vol': daily_returns.std() * np.sqrt(252),
            'vol_skew': daily_returns.skew(),
            'vol_kurtosis': daily_returns.kurtosis()
        }
        
        return BacktestResult(
            config=self.config,
            total_trades=total_trades,
            winning_trades=win_count,
            losing_trades=loss_count,
            win_rate=win_rate,
            total_return=total_return,
            annualized_return=annualized_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            avg_trade_return=avg_trade_return,
            avg_winning_trade=avg_winning_trade,
            avg_losing_trade=avg_losing_trade,
            largest_win=largest_win,
            largest_loss=largest_loss,
            profit_factor=profit_factor,
            trades=trades,
            equity_curve=equity_curve,
            regime_performance=regime_performance,
            monthly_returns=monthly_returns,
            volatility_stats=volatility_stats
        )
