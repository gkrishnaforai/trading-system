-- Migration 009: Swing Trading Foundation
-- Adds tables for swing trading system (Elite & Admin users)

-- Multi-timeframe data (daily, weekly, monthly)
CREATE TABLE IF NOT EXISTS multi_timeframe_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL CHECK(timeframe IN ('daily', 'weekly', 'monthly')),
    date DATE NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, timeframe, date)
);

-- Swing trading indicators
CREATE TABLE IF NOT EXISTS swing_indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_symbol TEXT NOT NULL,
    date DATE NOT NULL,
    timeframe TEXT NOT NULL CHECK(timeframe IN ('daily', 'weekly')),
    adx REAL,
    di_plus REAL,  -- +DI
    di_minus REAL, -- -DI
    stochastic_k REAL,
    stochastic_d REAL,
    williams_r REAL,
    vwap REAL,
    ichimoku_tenkan REAL,
    ichimoku_kijun REAL,
    ichimoku_senkou_a REAL,
    ichimoku_senkou_b REAL,
    fib_382 REAL,
    fib_500 REAL,
    fib_618 REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, timeframe, date)
);

-- Swing trades
CREATE TABLE IF NOT EXISTS swing_trades (
    trade_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    stock_symbol TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    entry_date DATE NOT NULL,
    entry_price REAL NOT NULL,
    entry_reason TEXT,
    position_size REAL NOT NULL,  -- Percentage of portfolio
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    trailing_stop REAL,
    max_hold_days INTEGER DEFAULT 7,
    exit_date DATE,
    exit_price REAL,
    exit_reason TEXT,
    pnl REAL,
    pnl_percent REAL,
    risk_reward_ratio REAL,
    status TEXT CHECK(status IN ('open', 'closed', 'stopped')) DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Swing trade signals
CREATE TABLE IF NOT EXISTS swing_trade_signals (
    signal_id TEXT PRIMARY KEY,
    trade_id TEXT,
    user_id TEXT NOT NULL,
    stock_symbol TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    signal_type TEXT CHECK(signal_type IN ('entry', 'exit', 'stop', 'take_profit')) NOT NULL,
    signal_price REAL NOT NULL,
    signal_date DATE NOT NULL,
    signal_reason TEXT,
    timeframe TEXT NOT NULL,
    confidence REAL,
    risk_reward_ratio REAL,
    executed BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trade_id) REFERENCES swing_trades(trade_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Swing backtest results
CREATE TABLE IF NOT EXISTS swing_backtest_results (
    backtest_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    stock_symbol TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital REAL NOT NULL,
    final_capital REAL NOT NULL,
    total_return REAL,
    total_return_pct REAL,
    win_rate REAL,
    profit_factor REAL,
    sharpe_ratio REAL,
    max_drawdown REAL,
    max_drawdown_pct REAL,
    avg_win REAL,
    avg_loss REAL,
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    avg_hold_days REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_mtf_symbol_timeframe ON multi_timeframe_data(stock_symbol, timeframe, date DESC);
CREATE INDEX IF NOT EXISTS idx_swing_indicators_symbol ON swing_indicators(stock_symbol, timeframe, date DESC);
CREATE INDEX IF NOT EXISTS idx_swing_trades_user ON swing_trades(user_id, status);
CREATE INDEX IF NOT EXISTS idx_swing_trades_symbol ON swing_trades(stock_symbol, status);
CREATE INDEX IF NOT EXISTS idx_swing_trades_status ON swing_trades(status, entry_date DESC);
CREATE INDEX IF NOT EXISTS idx_swing_signals_user ON swing_trade_signals(user_id, signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_swing_signals_trade ON swing_trade_signals(trade_id);
CREATE INDEX IF NOT EXISTS idx_swing_signals_symbol ON swing_trade_signals(stock_symbol, signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_swing_backtest_user ON swing_backtest_results(user_id, created_at DESC);

