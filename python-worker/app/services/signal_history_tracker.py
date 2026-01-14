#!/usr/bin/env python3
"""
Signal History Tracking System

Tracks signal changes over time for analysis and alert generation.
Stores previous and current analysis to detect recommendation changes.

Industry Standards:
- Signal state persistence
- Change detection alerts
- Historical performance tracking
- Signal quality monitoring

Author: Trading System
Date: 2026-01-06
"""

from dataclasses import dataclass, asdict
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from enum import Enum
import json
import logging

from app.database import db
from app.observability.logging import get_logger

logger = get_logger(__name__)


class SignalType(Enum):
    """Signal types following industry standards"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    AVOID = "AVOID"
    MONITORING = "MONITORING"


class SignalQuality(Enum):
    """Signal quality levels"""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RiskLevel(Enum):
    """Risk level classifications"""
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


@dataclass
class RecoverySignal:
    """Comprehensive recovery signal data structure"""
    symbol: str
    signal_type: SignalType
    signal_name: str
    confidence: float
    risk_level: RiskLevel
    position_size: int  # Percentage
    signal_quality: SignalQuality
    execution_size: str  # REDUCED/NORMAL/FULL
    
    # Recovery-specific metrics
    recovery_confidence: float
    context_ok: bool
    downtrend_weakening: bool
    momentum_shift: bool
    accumulation_ok: bool
    relative_strength_positive: bool
    
    # Risk management
    hard_stop: float
    swing_low: float
    
    # Market context
    vix_level: float
    volatility: float
    relative_strength: float
    
    # Technical indicators
    macd_histogram: float
    rsi: float
    volume_ratio: float
    
    # Metadata
    timestamp: datetime
    analysis_date: date
    engine_version: str = "1.0"


class SignalHistoryTracker:
    """
    Tracks signal history and detects changes for alerts
    
    Industry Standard Features:
    - Signal state persistence
    - Change detection
    - Performance tracking
    - Alert generation
    """
    
    def __init__(self):
        self.engine_version = "1.0"
        
    def save_signal(self, signal: RecoverySignal) -> bool:
        """
        Save signal to database for historical tracking
        
        Returns:
            bool: Success status
        """
        try:
            # Check for existing signal today
            existing = self._get_today_signal(signal.symbol)
            
            if existing:
                # Update existing signal
                success = self._update_signal(signal)
                if success:
                    self._detect_and_log_change(existing, signal)
                return success
            else:
                # Insert new signal
                return self._insert_signal(signal)
                
        except Exception as e:
            logger.error(f"Error saving signal for {signal.symbol}: {e}")
            return False
    
    def get_signal_history(self, symbol: str, days: int = 30) -> List[RecoverySignal]:
        """
        Get signal history for a symbol
        
        Args:
            symbol: Stock/ETF symbol
            days: Number of days to look back
            
        Returns:
            List[RecoverySignal]: Historical signals
        """
        try:
            query = """
                SELECT signal_data 
                FROM signal_history 
                WHERE symbol = %s 
                AND analysis_date >= CURRENT_DATE - INTERVAL '%s days'
                ORDER BY analysis_date DESC, timestamp DESC
            """
            
            result = db.execute_query(query, (symbol.upper(), days))
            
            signals = []
            for row in result:
                signal_data = json.loads(row['signal_data'])
                signals.append(self._deserialize_signal(signal_data))
            
            return signals
            
        except Exception as e:
            logger.error(f"Error getting signal history for {symbol}: {e}")
            return []
    
    def get_current_signal(self, symbol: str) -> Optional[RecoverySignal]:
        """
        Get current signal for a symbol
        
        Args:
            symbol: Stock/ETF symbol
            
        Returns:
            Optional[RecoverySignal]: Current signal or None
        """
        try:
            signal_data = self._get_today_signal(symbol)
            return signal_data if signal_data else None
            
        except Exception as e:
            logger.error(f"Error getting current signal for {symbol}: {e}")
            return None
    
    def get_signal_changes(self, symbol: str, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get recent signal changes for alert generation
        
        Args:
            symbol: Stock/ETF symbol
            hours: Hours to look back for changes
            
        Returns:
            List[Dict]: Signal change events
        """
        try:
            query = """
                SELECT old_signal, new_signal, change_type, timestamp
                FROM signal_changes 
                WHERE symbol = %s 
                AND timestamp >= NOW() - INTERVAL '%s hours'
                ORDER BY timestamp DESC
            """
            
            result = db.execute_query(query, (symbol.upper(), hours))
            
            changes = []
            for row in result:
                changes.append({
                    'old_signal': json.loads(row['old_signal']),
                    'new_signal': json.loads(row['new_signal']),
                    'change_type': row['change_type'],
                    'timestamp': row['timestamp']
                })
            
            return changes
            
        except Exception as e:
            logger.error(f"Error getting signal changes for {symbol}: {e}")
            return []
    
    def _get_today_signal(self, symbol: str) -> Optional[RecoverySignal]:
        """Get today's signal for a symbol"""
        try:
            query = """
                SELECT signal_data 
                FROM signal_history 
                WHERE symbol = %s 
                AND analysis_date = CURRENT_DATE
                ORDER BY timestamp DESC
                LIMIT 1
            """
            
            result = db.execute_query(query, (symbol.upper(),))
            
            if result:
                signal_data = json.loads(result[0]['signal_data'])
                return self._deserialize_signal(signal_data)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting today's signal for {symbol}: {e}")
            return None
    
    def _insert_signal(self, signal: RecoverySignal) -> bool:
        """Insert new signal record"""
        try:
            query = """
                INSERT INTO signal_history 
                (symbol, analysis_date, timestamp, signal_data, engine_version)
                VALUES (%s, %s, %s, %s, %s)
            """
            
            signal_data = json.dumps(asdict(signal), default=str)
            
            db.execute_query(query, (
                signal.symbol.upper(),
                signal.analysis_date,
                signal.timestamp,
                signal_data,
                self.engine_version
            ))
            
            logger.info(f"✅ Saved new signal for {signal.symbol}: {signal.signal_type}")
            return True
            
        except Exception as e:
            logger.error(f"Error inserting signal for {signal.symbol}: {e}")
            return False
    
    def _update_signal(self, signal: RecoverySignal) -> bool:
        """Update existing signal record"""
        try:
            query = """
                UPDATE signal_history 
                SET signal_data = %s, timestamp = %s, engine_version = %s
                WHERE symbol = %s 
                AND analysis_date = CURRENT_DATE
                AND timestamp = (
                    SELECT MAX(timestamp) 
                    FROM signal_history 
                    WHERE symbol = %s 
                    AND analysis_date = CURRENT_DATE
                )
            """
            
            signal_data = json.dumps(asdict(signal), default=str)
            
            db.execute_query(query, (
                signal_data,
                signal.timestamp,
                self.engine_version,
                signal.symbol.upper(),
                signal.symbol.upper()
            ))
            
            logger.info(f"✅ Updated signal for {signal.symbol}: {signal.signal_type}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating signal for {signal.symbol}: {e}")
            return False
    
    def _detect_and_log_change(self, old_signal: RecoverySignal, new_signal: RecoverySignal) -> None:
        """
        Detect signal changes and log for alerts
        
        Industry Standard Change Detection:
        - Signal type changes (BUY → SELL)
        - Confidence threshold breaches
        - Risk level changes
        - Quality level changes
        """
        changes = []
        
        # Signal type change (most important)
        if old_signal.signal_type != new_signal.signal_type:
            changes.append({
                'type': 'SIGNAL_TYPE_CHANGE',
                'old': old_signal.signal_type.value,
                'new': new_signal.signal_type.value,
                'importance': 'HIGH'
            })
        
        # Confidence threshold breach
        old_conf_category = self._get_confidence_category(old_signal.confidence)
        new_conf_category = self._get_confidence_category(new_signal.confidence)
        
        if old_conf_category != new_conf_category:
            changes.append({
                'type': 'CONFIDENCE_THRESHOLD_CHANGE',
                'old': f"{old_conf_category} ({old_signal.confidence:.2f})",
                'new': f"{new_conf_category} ({new_signal.confidence:.2f})",
                'importance': 'MEDIUM'
            })
        
        # Risk level change
        if old_signal.risk_level != new_signal.risk_level:
            changes.append({
                'type': 'RISK_LEVEL_CHANGE',
                'old': old_signal.risk_level.value,
                'new': new_signal.risk_level.value,
                'importance': 'MEDIUM'
            })
        
        # Quality level change
        if old_signal.signal_quality != new_signal.signal_quality:
            changes.append({
                'type': 'QUALITY_CHANGE',
                'old': old_signal.signal_quality.value,
                'new': new_signal.signal_quality.value,
                'importance': 'LOW'
            })
        
        # Log changes for alerts
        if changes:
            self._log_signal_changes(old_signal, new_signal, changes)
    
    def _log_signal_changes(self, old_signal: RecoverySignal, new_signal: RecoverySignal, changes: List[Dict]) -> None:
        """Log signal changes to database for alert generation"""
        try:
            for change in changes:
                query = """
                    INSERT INTO signal_changes 
                    (symbol, old_signal, new_signal, change_type, change_details, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                
                change_details = json.dumps({
                    'old_value': change['old'],
                    'new_value': change['new'],
                    'importance': change['importance']
                })
                
                db.execute_query(query, (
                    new_signal.symbol.upper(),
                    json.dumps(asdict(old_signal), default=str),
                    json.dumps(asdict(new_signal), default=str),
                    change['type'],
                    change_details,
                    new_signal.timestamp
                ))
                
                # Log for monitoring
                logger.info(f"🔄 Signal Change for {new_signal.symbol}: {change['type']} - {change['old']} → {change['new']}")
                
        except Exception as e:
            logger.error(f"Error logging signal changes: {e}")
    
    def _get_confidence_category(self, confidence: float) -> str:
        """Get confidence category for threshold tracking"""
        if confidence >= 0.70:
            return "VERY_HIGH"
        elif confidence >= 0.55:
            return "HIGH"
        elif confidence >= 0.40:
            return "MEDIUM"
        elif confidence >= 0.25:
            return "LOW"
        else:
            return "VERY_LOW"
    
    def _deserialize_signal(self, signal_data: Dict) -> RecoverySignal:
        """Deserialize signal data from dictionary"""
        # Convert enums back
        signal_type = SignalType(signal_data['signal_type'])
        signal_quality = SignalQuality(signal_data['signal_quality'])
        risk_level = RiskLevel(signal_data['risk_level'])
        
        # Parse datetime
        timestamp = datetime.fromisoformat(signal_data['timestamp'])
        analysis_date = date.fromisoformat(signal_data['analysis_date'])
        
        return RecoverySignal(
            symbol=signal_data['symbol'],
            signal_type=signal_type,
            signal_name=signal_data['signal_name'],
            confidence=signal_data['confidence'],
            risk_level=risk_level,
            position_size=signal_data['position_size'],
            signal_quality=signal_quality,
            execution_size=signal_data['execution_size'],
            recovery_confidence=signal_data['recovery_confidence'],
            context_ok=signal_data['context_ok'],
            downtrend_weakening=signal_data['downtrend_weakening'],
            momentum_shift=signal_data['momentum_shift'],
            accumulation_ok=signal_data['accumulation_ok'],
            relative_strength_positive=signal_data['relative_strength_positive'],
            hard_stop=signal_data['hard_stop'],
            swing_low=signal_data['swing_low'],
            vix_level=signal_data['vix_level'],
            volatility=signal_data['volatility'],
            relative_strength=signal_data['relative_strength'],
            macd_histogram=signal_data['macd_histogram'],
            rsi=signal_data['rsi'],
            volume_ratio=signal_data['volume_ratio'],
            timestamp=timestamp,
            analysis_date=analysis_date,
            engine_version=signal_data.get('engine_version', '1.0')
        )


# Factory function for dependency injection
def create_signal_tracker() -> SignalHistoryTracker:
    """Factory function to create signal history tracker"""
    return SignalHistoryTracker()
