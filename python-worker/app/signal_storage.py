"""
Signal storage functions for trading signals database
Clean implementation without syntax errors
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional

from app.database import db
from app.observability.logging import get_logger

logger = get_logger(__name__)

async def ensure_signals_table_exists():
    """Create trading_signals table if it doesn't exist"""
    try:
        create_table_query = """
        CREATE TABLE IF NOT EXISTS trading_signals (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            signal_date DATE NOT NULL,
            signal_type VARCHAR(20) NOT NULL,
            confidence DECIMAL(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            strategy VARCHAR(50) NOT NULL,
            strategy_version VARCHAR(20) DEFAULT '1.0',
            
            -- Price information
            price_at_signal DECIMAL(12,4),
            volume_at_signal BIGINT,
            
            -- Technical indicators
            sma_50 DECIMAL(12,4),
            sma_200 DECIMAL(12,4),
            ema_20 DECIMAL(12,4),
            rsi_14 DECIMAL(8,4),
            macd DECIMAL(8,4),
            macd_signal DECIMAL(8,4),
            
            -- Signal metadata
            signal_strength VARCHAR(20),
            time_horizon VARCHAR(20),
            risk_level VARCHAR(20),
            market_regime VARCHAR(20),
            volatility DECIMAL(8,4),
            
            -- Reasoning
            signal_reason TEXT,
            key_factors JSONB,
            
            -- Performance tracking
            entry_price DECIMAL(12,4),
            exit_price DECIMAL(12,4),
            profit_loss DECIMAL(12,4),
            profit_loss_pct DECIMAL(8,4),
            max_profit DECIMAL(12,4),
            max_loss DECIMAL(12,4),
            holding_days INTEGER,
            
            -- Execution details
            status VARCHAR(20) DEFAULT 'generated',
            executed_at TIMESTAMP,
            closed_at TIMESTAMP,
            
            -- System fields
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            batch_id UUID,
            
            UNIQUE(symbol, signal_date, strategy, created_at)
        );
        """
        
        db.execute_update(create_table_query)
        logger.info("✅ trading_signals table created")
        
        # Create indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_trading_signals_symbol_date ON trading_signals(symbol, signal_date DESC);",
            "CREATE INDEX IF NOT EXISTS idx_trading_signals_strategy ON trading_signals(strategy);",
            "CREATE INDEX IF NOT EXISTS idx_trading_signals_created_at ON trading_signals(created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_trading_signals_signal_type ON trading_signals(signal_type);"
        ]
        
        for index_sql in indexes:
            db.execute_update(index_sql)
        
        logger.info("✅ Indexes created")
        
    except Exception as e:
        logger.error(f"Failed to create signals table: {e}")


async def store_signal_in_database(signal_data: dict, indicators: dict, backtest_date: str = None):
    """Store signal in database following industry standards"""
    try:
        # Ensure table exists
        await ensure_signals_table_exists()
        
        # Determine signal strength based on confidence
        confidence = signal_data.get("confidence", 0.5)
        if confidence >= 0.8:
            signal_strength = "strong"
        elif confidence >= 0.6:
            signal_strength = "moderate"
        else:
            signal_strength = "weak"
        
        # Extract date from timestamp
        signal_date = backtest_date if backtest_date else datetime.now().date()
        
        # Prepare key factors as JSON string for PostgreSQL
        key_factors = {
            "sma_50": indicators.get("sma_50"),
            "sma_200": indicators.get("sma_200"),
            "ema_20": indicators.get("ema_20"),
            "rsi_14": indicators.get("rsi_14"),
            "macd": indicators.get("macd"),
            "macd_signal": indicators.get("macd_signal"),
            "price": indicators.get("price")
        }
        
        # Generate signal reason based on strategy and indicators
        signal_reason = generate_signal_reason(signal_data, indicators)
        
        # Convert to JSON string for PostgreSQL
        key_factors_json = json.dumps(key_factors)
        
        insert_query = """
        INSERT INTO trading_signals (
            symbol, signal_date, signal_type, confidence, strategy, strategy_version,
            price_at_signal, sma_50, sma_200, ema_20, rsi_14, macd, macd_signal,
            signal_strength, time_horizon, risk_level, signal_reason, key_factors,
            volatility
        ) VALUES (
            :symbol, :signal_date, :signal_type, :confidence, :strategy, :strategy_version,
            :price_at_signal, :sma_50, :sma_200, :ema_20, :rsi_14, :macd, :macd_signal,
            :signal_strength, :time_horizon, :risk_level, :signal_reason, :key_factors,
            :volatility
        )
        """
        
        db.execute_update(insert_query, {
            "symbol": signal_data["symbol"],
            "signal_date": signal_date,
            "signal_type": signal_data["signal"],
            "confidence": confidence,
            "strategy": signal_data["strategy"],
            "strategy_version": "1.0",
            "price_at_signal": indicators.get("price", 0),
            "sma_50": indicators.get("sma_50"),
            "sma_200": indicators.get("sma_200"),
            "ema_20": indicators.get("ema_20"),
            "rsi_14": indicators.get("rsi_14"),
            "macd": indicators.get("macd"),
            "macd_signal": indicators.get("macd_signal"),
            "signal_strength": signal_strength,
            "time_horizon": "short_term",
            "risk_level": "medium",
            "signal_reason": signal_reason,
            "key_factors": key_factors_json,
            "volatility": 0.2
        })
        
        logger.info(f"Stored signal for {signal_data['symbol']} in database")
        
    except Exception as e:
        logger.error(f"Failed to store signal in database: {e}")
        # Don't raise exception - signal generation should still work even if storage fails


def generate_signal_reason(signal_data: dict, indicators: dict) -> str:
    """Generate a human-readable reason for the signal"""
    signal = signal_data.get("signal", "hold")
    strategy = signal_data.get("strategy", "unknown")
    
    if signal == "buy":
        reasons = []
        if indicators.get("rsi_14", 50) < 30:
            reasons.append("RSI oversold")
        if indicators.get("sma_50", 0) > indicators.get("sma_200", 0):
            reasons.append("SMA50 above SMA200 (bullish)")
        if indicators.get("ema_20", 0) > indicators.get("sma_50", 0):
            reasons.append("EMA20 above SMA50")
        
        return f"Buy signal: {', '.join(reasons) if reasons else 'Multiple bullish indicators'}"
    
    elif signal == "sell":
        reasons = []
        if indicators.get("rsi_14", 50) > 70:
            reasons.append("RSI overbought")
        if indicators.get("sma_50", 0) < indicators.get("sma_200", 0):
            reasons.append("SMA50 below SMA200 (bearish)")
        if indicators.get("ema_20", 0) < indicators.get("sma_50", 0):
            reasons.append("EMA20 below SMA50")
        
        return f"Sell signal: {', '.join(reasons) if reasons else 'Multiple bearish indicators'}"
    
    else:
        return "Hold signal: Neutral market conditions, no clear directional bias"


async def get_recent_signals(limit: int = 20):
    """Get recent trading signals from database"""
    try:
        # Ensure trading_signals table exists
        await ensure_signals_table_exists()
        
        # Query recent signals
        query = """
            SELECT 
                symbol,
                signal_date,
                signal_type,
                confidence,
                strategy,
                signal_reason,
                signal_strength,
                time_horizon,
                risk_level,
                price_at_signal,
                sma_50,
                sma_200,
                ema_20,
                rsi_14,
                macd,
                macd_signal,
                created_at
            FROM trading_signals 
            ORDER BY created_at DESC 
            LIMIT :limit
        """
        
        results = db.execute_query(query, {"limit": limit})
        
        signals = []
        for row in results:
            signals.append({
                "symbol": row["symbol"],
                "signal": row["signal_type"],
                "confidence": float(row["confidence"]),
                "strategy": row["strategy"],
                "reason": row["signal_reason"],
                "strength": row["signal_strength"],
                "time_horizon": row["time_horizon"],
                "risk_level": row["risk_level"],
                "price_at_signal": float(row["price_at_signal"]) if row["price_at_signal"] else None,
                "indicators": {
                    "sma_50": float(row["sma_50"]) if row["sma_50"] else None,
                    "sma_200": float(row["sma_200"]) if row["sma_200"] else None,
                    "ema_20": float(row["ema_20"]) if row["ema_20"] else None,
                    "rsi_14": float(row["rsi_14"]) if row["rsi_14"] else None,
                    "macd": float(row["macd"]) if row["macd"] else None,
                    "macd_signal": float(row["macd_signal"]) if row["macd_signal"] else None
                },
                "signal_date": row["signal_date"].isoformat() if row["signal_date"] else None,
                "timestamp": row["created_at"].isoformat() if row["created_at"] else None
            })
        
        return {
            "signals": signals,
            "total": len(signals)
        }
        
    except Exception as e:
        logger.error(f"Failed to get recent signals: {e}")
        raise e
