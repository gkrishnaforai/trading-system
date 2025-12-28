# Swing Trading Implementation Guide

## Overview

This guide provides step-by-step implementation details for the swing trading system, following our existing architecture patterns (DRY, SOLID, pluggable, scalable).

## Implementation Phases

### Phase 1: Data Collection & Multi-Timeframe Support

#### 1.1 Multi-Timeframe Data Service

**File**: `python-worker/app/services/multi_timeframe_service.py`

```python
"""
Multi-Timeframe Data Service
Collects and manages data across daily, weekly, monthly timeframes
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import pandas as pd

from app.services.base import BaseService
from app.database import db
from app.data_sources.base import BaseDataSource

class MultiTimeframeService(BaseService):
    """Service for managing multi-timeframe data"""
    
    def __init__(self, data_source: Optional[BaseDataSource] = None):
        super().__init__()
        from app.di import get_container
        container = get_container()
        self.data_source = data_source or container.get('data_source')
    
    def fetch_and_save_timeframe(
        self,
        symbol: str,
        timeframe: str,  # 'daily', 'weekly', 'monthly'
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """
        Fetch and save data for a specific timeframe
        
        Returns:
            Number of rows saved
        """
        # Fetch daily data first
        daily_data = self.data_source.fetch_historical_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if daily_data is None or daily_data.empty:
            return 0
        
        # Aggregate to requested timeframe
        if timeframe == 'daily':
            aggregated = daily_data
        elif timeframe == 'weekly':
            aggregated = self._aggregate_to_weekly(daily_data)
        elif timeframe == 'monthly':
            aggregated = self._aggregate_to_monthly(daily_data)
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        
        # Save to database
        return self._save_timeframe_data(symbol, timeframe, aggregated)
    
    def _aggregate_to_weekly(self, daily_data: pd.DataFrame) -> pd.DataFrame:
        """Aggregate daily data to weekly"""
        # Set date as index if not already
        if 'date' in daily_data.columns:
            daily_data = daily_data.set_index('date')
        
        # Resample to weekly (Monday to Friday)
        weekly = daily_data.resample('W').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        })
        
        weekly = weekly.reset_index()
        weekly['date'] = weekly['date'].dt.date
        return weekly
    
    def _aggregate_to_monthly(self, daily_data: pd.DataFrame) -> pd.DataFrame:
        """Aggregate daily data to monthly"""
        if 'date' in daily_data.columns:
            daily_data = daily_data.set_index('date')
        
        monthly = daily_data.resample('M').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        })
        
        monthly = monthly.reset_index()
        monthly['date'] = monthly['date'].dt.date
        return monthly
    
    def _save_timeframe_data(
        self,
        symbol: str,
        timeframe: str,
        data: pd.DataFrame
    ) -> int:
        """Save timeframe data to database"""
        rows_saved = 0
        
        for _, row in data.iterrows():
            query = """
                INSERT OR REPLACE INTO multi_timeframe_data
                (stock_symbol, timeframe, date, open, high, low, close, volume)
                VALUES (:symbol, :timeframe, :date, :open, :high, :low, :close, :volume)
            """
            
            db.execute_update(query, {
                "symbol": symbol,
                "timeframe": timeframe,
                "date": row['date'],
                "open": row['open'],
                "high": row['high'],
                "low": row['low'],
                "close": row['close'],
                "volume": row['volume']
            })
            rows_saved += 1
        
        return rows_saved
    
    def get_timeframe_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """Get timeframe data from database"""
        query = """
            SELECT date, open, high, low, close, volume
            FROM multi_timeframe_data
            WHERE stock_symbol = :symbol AND timeframe = :timeframe
        """
        params = {"symbol": symbol, "timeframe": timeframe}
        
        if start_date:
            query += " AND date >= :start_date"
            params["start_date"] = start_date.date()
        
        if end_date:
            query += " AND date <= :end_date"
            params["end_date"] = end_date.date()
        
        query += " ORDER BY date DESC"
        
        if limit:
            query += f" LIMIT {limit}"
        
        result = db.execute_query(query, params)
        
        if not result:
            return pd.DataFrame()
        
        df = pd.DataFrame(result)
        df['date'] = pd.to_datetime(df['date'])
        return df.sort_values('date')
```

#### 1.2 Swing Trading Indicators

**File**: `python-worker/app/indicators/swing.py`

```python
"""
Swing Trading Specific Indicators
ADX, Stochastic, Williams %R, VWAP, Ichimoku, Fibonacci
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

def calculate_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> Dict[str, pd.Series]:
    """
    Calculate Average Directional Index (ADX)
    
    Returns:
        Dictionary with 'adx', 'di_plus', 'di_minus'
    """
    # Calculate True Range
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Calculate Directional Movement
    plus_dm = high.diff()
    minus_dm = low.diff()
    
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    
    # Smooth TR and DM
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    
    # Calculate DX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    
    # Calculate ADX
    adx = dx.rolling(period).mean()
    
    return {
        'adx': adx,
        'di_plus': plus_di,
        'di_minus': minus_di
    }

def calculate_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3
) -> Dict[str, pd.Series]:
    """
    Calculate Stochastic Oscillator
    
    Returns:
        Dictionary with 'stochastic_k', 'stochastic_d'
    """
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    
    k = 100 * ((close - lowest_low) / (highest_high - lowest_low))
    d = k.rolling(d_period).mean()
    
    return {
        'stochastic_k': k,
        'stochastic_d': d
    }

def calculate_williams_r(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Calculate Williams %R
    """
    highest_high = high.rolling(period).max()
    lowest_low = low.rolling(period).min()
    
    wr = -100 * ((highest_high - close) / (highest_high - lowest_low))
    
    return wr

def calculate_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: Optional[int] = None
) -> pd.Series:
    """
    Calculate Volume Weighted Average Price (VWAP)
    
    If period is None, calculates cumulative VWAP
    """
    typical_price = (high + low + close) / 3
    pv = typical_price * volume
    
    if period:
        vwap = pv.rolling(period).sum() / volume.rolling(period).sum()
    else:
        vwap = pv.cumsum() / volume.cumsum()
    
    return vwap

def calculate_fibonacci_retracements(
    high: pd.Series,
    low: pd.Series,
    period: int = 20
) -> Dict[str, pd.Series]:
    """
    Calculate Fibonacci Retracement Levels
    
    Returns:
        Dictionary with 'fib_382', 'fib_500', 'fib_618'
    """
    highest = high.rolling(period).max()
    lowest = low.rolling(period).min()
    diff = highest - lowest
    
    return {
        'fib_382': highest - (diff * 0.382),
        'fib_500': highest - (diff * 0.500),
        'fib_618': highest - (diff * 0.618)
    }
```

### Phase 2: Swing Trading Strategies

#### 2.1 Base Swing Strategy

**File**: `python-worker/app/strategies/swing/base.py`

```python
"""
Base Swing Trading Strategy
All swing strategies extend this class
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import pandas as pd

from app.strategies.base import BaseStrategy

@dataclass
class SwingStrategyResult:
    """Result from swing trading strategy"""
    signal: str  # 'BUY', 'SELL', 'HOLD'
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float  # Percentage of portfolio (0.01 = 1%)
    confidence: float  # 0.0 to 1.0
    timeframe: str  # 'daily', 'weekly'
    entry_reason: str
    exit_reason: Optional[str] = None
    risk_reward_ratio: float = 0.0
    max_hold_days: int = 7

class BaseSwingStrategy(BaseStrategy):
    """
    Base class for all swing trading strategies
    
    Features:
    - Multi-timeframe analysis
    - Risk-adjusted signals
    - Position sizing recommendations
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.max_hold_days = config.get('max_hold_days', 7) if config else 7
        self.risk_per_trade = config.get('risk_per_trade', 0.01) if config else 0.01  # 1%
    
    @abstractmethod
    def generate_swing_signal(
        self,
        daily_data: pd.DataFrame,
        weekly_data: Optional[pd.DataFrame] = None,
        indicators: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> SwingStrategyResult:
        """
        Generate swing trading signal
        
        Args:
            daily_data: Daily price data
            weekly_data: Weekly price data (for trend confirmation)
            indicators: Pre-calculated indicators
            context: Additional context (user preferences, etc.)
        
        Returns:
            SwingStrategyResult with entry/exit signals
        """
        pass
    
    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        account_balance: float,
        risk_per_trade: Optional[float] = None
    ) -> float:
        """
        Calculate position size based on risk
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            account_balance: Total account balance
            risk_per_trade: Risk per trade (default: self.risk_per_trade)
        
        Returns:
            Position size as percentage of portfolio
        """
        risk_pct = risk_per_trade or self.risk_per_trade
        risk_amount = account_balance * risk_pct
        price_risk = abs(entry_price - stop_loss)
        
        if price_risk == 0:
            return 0.0
        
        position_value = risk_amount / (price_risk / entry_price)
        position_size_pct = position_value / account_balance
        
        return min(position_size_pct, 0.10)  # Max 10% per position
    
    def calculate_risk_reward(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float
    ) -> float:
        """Calculate risk-reward ratio"""
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        
        if risk == 0:
            return 0.0
        
        return reward / risk
```

#### 2.2 Swing Trend Strategy

**File**: `python-worker/app/strategies/swing/trend_strategy.py`

```python
"""
Swing Trend Following Strategy
Multi-timeframe trend following for swing trades
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

from app.strategies.swing.base import BaseSwingStrategy, SwingStrategyResult
from app.indicators.moving_averages import calculate_ema, calculate_sma
from app.indicators.momentum import calculate_rsi, calculate_macd

class SwingTrendStrategy(BaseSwingStrategy):
    """
    Swing Trend Following Strategy
    
    Logic:
    1. Weekly trend confirmation (50-week SMA)
    2. Daily entry signals (9/21 EMA crossover)
    3. RSI momentum (50-70 range)
    4. MACD confirmation
    5. Volume confirmation
    """
    
    def get_name(self) -> str:
        return "swing_trend"
    
    def get_description(self) -> str:
        return "Multi-timeframe trend following strategy for swing trades"
    
    def generate_swing_signal(
        self,
        daily_data: pd.DataFrame,
        weekly_data: Optional[pd.DataFrame] = None,
        indicators: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> SwingStrategyResult:
        """Generate swing trend signal"""
        
        if daily_data.empty or len(daily_data) < 50:
            return SwingStrategyResult(
                signal='HOLD',
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                position_size=0.0,
                confidence=0.0,
                timeframe='daily',
                entry_reason="Insufficient data"
            )
        
        # Get latest data
        latest = daily_data.iloc[-1]
        close = latest['close']
        
        # Calculate indicators if not provided
        if indicators is None:
            indicators = self._calculate_indicators(daily_data)
        
        # Weekly trend confirmation
        weekly_trend = 'neutral'
        if weekly_data is not None and len(weekly_data) >= 50:
            weekly_sma50 = calculate_sma(weekly_data['close'], 50)
            if len(weekly_sma50) > 0:
                if weekly_data['close'].iloc[-1] > weekly_sma50.iloc[-1]:
                    weekly_trend = 'bullish'
                else:
                    weekly_trend = 'bearish'
        
        # Daily signals
        ema9 = indicators.get('ema9', pd.Series())
        ema21 = indicators.get('ema21', pd.Series())
        sma50 = indicators.get('sma50', pd.Series())
        rsi = indicators.get('rsi', pd.Series())
        macd = indicators.get('macd', pd.Series())
        macd_signal = indicators.get('macd_signal', pd.Series())
        volume_avg = indicators.get('volume_avg', pd.Series())
        
        if len(ema9) < 2 or len(ema21) < 2:
            return SwingStrategyResult(
                signal='HOLD',
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                position_size=0.0,
                confidence=0.0,
                timeframe='daily',
                entry_reason="Insufficient indicator data"
            )
        
        # Check for EMA crossover
        ema9_current = ema9.iloc[-1]
        ema9_prev = ema9.iloc[-2]
        ema21_current = ema21.iloc[-1]
        ema21_prev = ema21.iloc[-2]
        
        # Bullish crossover
        bullish_cross = (ema9_prev <= ema21_prev) and (ema9_current > ema21_current)
        
        # Entry conditions
        price_above_sma50 = len(sma50) > 0 and close > sma50.iloc[-1]
        rsi_healthy = len(rsi) > 0 and 50 <= rsi.iloc[-1] <= 70
        macd_positive = len(macd) > 0 and len(macd_signal) > 0 and macd.iloc[-1] > macd_signal.iloc[-1]
        volume_confirmed = len(volume_avg) > 0 and latest['volume'] > volume_avg.iloc[-1]
        
        # Generate signal
        if bullish_cross and price_above_sma50 and rsi_healthy and macd_positive:
            # Calculate entry/exit levels
            entry_price = close
            atr = indicators.get('atr', pd.Series())
            
            if len(atr) > 0:
                stop_loss = entry_price - (2 * atr.iloc[-1])
                take_profit = entry_price + (6 * atr.iloc[-1])  # 3:1 risk-reward
            else:
                stop_loss = entry_price * 0.98  # 2% stop
                take_profit = entry_price * 1.06  # 6% target
            
            # Calculate confidence
            confidence = 0.6  # Base confidence
            if weekly_trend == 'bullish':
                confidence += 0.2
            if volume_confirmed:
                confidence += 0.1
            if rsi.iloc[-1] > 55:
                confidence += 0.1
            
            confidence = min(confidence, 1.0)
            
            risk_reward = self.calculate_risk_reward(entry_price, stop_loss, take_profit)
            
            return SwingStrategyResult(
                signal='BUY',
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size=0.01,  # Will be calculated by risk manager
                confidence=confidence,
                timeframe='daily',
                entry_reason=f"EMA crossover, weekly trend: {weekly_trend}, RSI: {rsi.iloc[-1]:.1f}",
                risk_reward_ratio=risk_reward,
                max_hold_days=self.max_hold_days
            )
        
        # Exit conditions
        bearish_cross = (ema9_prev >= ema21_prev) and (ema9_current < ema21_current)
        rsi_overbought = len(rsi) > 0 and rsi.iloc[-1] > 75
        
        if bearish_cross or rsi_overbought:
            return SwingStrategyResult(
                signal='SELL',
                entry_price=close,
                stop_loss=0.0,
                take_profit=0.0,
                position_size=0.0,
                confidence=0.7,
                timeframe='daily',
                entry_reason="Exit signal",
                exit_reason="EMA bearish cross" if bearish_cross else "RSI overbought"
            )
        
        return SwingStrategyResult(
            signal='HOLD',
            entry_price=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            position_size=0.0,
            confidence=0.0,
            timeframe='daily',
            entry_reason="No clear signal"
        )
    
    def _calculate_indicators(self, data: pd.DataFrame) -> Dict[str, pd.Series]:
        """Calculate required indicators"""
        close = data['close']
        high = data['high']
        low = data['low']
        volume = data['volume']
        
        return {
            'ema9': calculate_ema(close, 9),
            'ema21': calculate_ema(close, 21),
            'sma50': calculate_sma(close, 50),
            'rsi': calculate_rsi(close, 14),
            'macd': calculate_macd(close)['macd'],
            'macd_signal': calculate_macd(close)['signal'],
            'atr': calculate_atr(high, low, close, 14),
            'volume_avg': volume.rolling(20).mean()
        }
```

### Phase 3: Risk Management

#### 3.1 Swing Risk Manager

**File**: `python-worker/app/services/swing_risk_manager.py`

```python
"""
Swing Trading Risk Management Service
Manages position sizing, portfolio heat, stop-losses
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from app.services.base import BaseService
from app.database import db

class SwingRiskManager(BaseService):
    """Risk management for swing trading"""
    
    def __init__(self):
        super().__init__()
        self.max_portfolio_risk = 0.05  # 5% total portfolio risk
        self.max_open_trades = 3
        self.max_position_size = 0.10  # 10% max per position
    
    def calculate_position_size(
        self,
        user_id: str,
        entry_price: float,
        stop_loss: float,
        risk_per_trade: float = 0.01
    ) -> Dict[str, Any]:
        """
        Calculate position size based on risk
        
        Returns:
            Dictionary with position_size_pct, position_value, shares
        """
        # Get account balance
        account_balance = self._get_account_balance(user_id)
        
        # Calculate risk amount
        risk_amount = account_balance * risk_per_trade
        
        # Calculate price risk
        price_risk = abs(entry_price - stop_loss)
        if price_risk == 0:
            return {
                'position_size_pct': 0.0,
                'position_value': 0.0,
                'shares': 0,
                'risk_amount': 0.0
            }
        
        # Calculate position value
        position_value = risk_amount / (price_risk / entry_price)
        position_size_pct = position_value / account_balance
        
        # Apply max position size
        position_size_pct = min(position_size_pct, self.max_position_size)
        position_value = account_balance * position_size_pct
        shares = int(position_value / entry_price)
        
        return {
            'position_size_pct': position_size_pct,
            'position_value': position_value,
            'shares': shares,
            'risk_amount': risk_amount
        }
    
    def check_portfolio_heat(
        self,
        user_id: str,
        new_trade_risk: float
    ) -> Dict[str, Any]:
        """
        Check if adding new trade would exceed portfolio risk limits
        
        Returns:
            Dictionary with allowed, current_risk, max_risk, open_trades
        """
        # Get current open trades
        open_trades = self._get_open_trades(user_id)
        current_risk = sum(trade.get('risk_amount', 0) for trade in open_trades)
        total_risk = current_risk + new_trade_risk
        
        # Get account balance
        account_balance = self._get_account_balance(user_id)
        max_risk_amount = account_balance * self.max_portfolio_risk
        
        allowed = (
            total_risk <= max_risk_amount and
            len(open_trades) < self.max_open_trades
        )
        
        return {
            'allowed': allowed,
            'current_risk': current_risk,
            'current_risk_pct': (current_risk / account_balance) * 100 if account_balance > 0 else 0,
            'total_risk': total_risk,
            'total_risk_pct': (total_risk / account_balance) * 100 if account_balance > 0 else 0,
            'max_risk': max_risk_amount,
            'max_risk_pct': self.max_portfolio_risk * 100,
            'open_trades': len(open_trades),
            'max_open_trades': self.max_open_trades
        }
    
    def _get_account_balance(self, user_id: str) -> float:
        """Get user's account balance"""
        # This would integrate with portfolio service
        # For now, return a default
        query = """
            SELECT SUM(current_value) as total_value
            FROM holdings
            WHERE portfolio_id IN (
                SELECT portfolio_id FROM portfolios WHERE user_id = :user_id
            )
        """
        result = db.execute_query(query, {"user_id": user_id})
        
        if result and result[0].get('total_value'):
            return float(result[0]['total_value'])
        
        return 100000.0  # Default $100k
    
    def _get_open_trades(self, user_id: str) -> List[Dict[str, Any]]:
        """Get user's open swing trades"""
        query = """
            SELECT trade_id, stock_symbol, entry_price, stop_loss, position_size
            FROM swing_trades
            WHERE user_id = :user_id AND status = 'open'
        """
        result = db.execute_query(query, {"user_id": user_id})
        
        trades = []
        for row in result:
            risk_amount = abs(row['entry_price'] - row['stop_loss']) * (row['position_size'] / row['entry_price'])
            trades.append({
                'trade_id': row['trade_id'],
                'symbol': row['stock_symbol'],
                'risk_amount': risk_amount
            })
        
        return trades
```

## Testing Strategy

### Unit Tests

1. **Multi-Timeframe Service Tests**
   - Test daily to weekly aggregation
   - Test daily to monthly aggregation
   - Test data saving and retrieval

2. **Indicator Tests**
   - Test ADX calculation
   - Test Stochastic calculation
   - Test Williams %R calculation
   - Test VWAP calculation

3. **Strategy Tests**
   - Test SwingTrendStrategy signal generation
   - Test entry/exit conditions
   - Test position sizing

4. **Risk Manager Tests**
   - Test position size calculation
   - Test portfolio heat limits
   - Test risk validation

### Integration Tests

1. **End-to-End Signal Generation**
   - Fetch multi-timeframe data
   - Calculate indicators
   - Generate swing signal
   - Validate risk management

2. **Backtesting**
   - Run strategy on historical data
   - Validate performance metrics
   - Compare with expected results

## Next Steps

1. **Create Migration 009**: Add swing trading tables
2. **Implement Multi-Timeframe Service**: Phase 1
3. **Implement Swing Indicators**: Phase 1
4. **Implement Swing Strategies**: Phase 2
5. **Implement Risk Manager**: Phase 3
6. **Create API Endpoints**: Phase 6
7. **Write Tests**: Throughout implementation

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-XX

