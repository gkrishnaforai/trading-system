"""
Workflow Gates - Fail-Fast Validation
Industry Standard: Pre-flight checks before proceeding to next stage
"""
import logging
from typing import Optional
from datetime import date, datetime, timedelta
from dataclasses import dataclass

from app.database import db
from app.data_validation.signal_readiness import SignalReadinessValidator

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    """Result of a gate check"""
    passed: bool
    reason: Optional[str] = None
    action: Optional[str] = None  # 'RETRY_INGESTION', 'FIX_DATA_QUALITY', 'COMPUTE_INDICATORS', etc.
    metadata: Optional[dict] = None


class BaseGate:
    """Base class for workflow gates"""
    
    def check(self, symbol: str, date: date, workflow_id: Optional[str] = None) -> GateResult:
        """
        Check if gate passes for symbol and date
        
        Args:
            symbol: Stock symbol
            date: Date to check
            workflow_id: Optional workflow ID for audit trail
        
        Returns:
            GateResult with pass/fail status
        """
        raise NotImplementedError
    
    def _log_gate_result(self, workflow_id: Optional[str], stage: str, symbol: str, result: GateResult):
        """Log gate result to database for audit trail"""
        if workflow_id:
            try:
                db.execute_update(
                    """
                    INSERT INTO workflow_gate_results
                    (gate_result_id, workflow_id, stage, symbol, gate_name, passed, reason, action, checked_at)
                    VALUES (:gate_id, :workflow_id, :stage, :symbol, :gate_name, :passed, :reason, :action, CURRENT_TIMESTAMP)
                    """,
                    {
                        "gate_id": f"{workflow_id}_{stage}_{symbol}_{datetime.now().isoformat()}",
                        "workflow_id": workflow_id,
                        "stage": stage,
                        "symbol": symbol,
                        "gate_name": self.__class__.__name__,
                        "passed": 1 if result.passed else 0,
                        "reason": result.reason,
                        "action": result.action
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to log gate result: {e}")


class DataIngestionGate(BaseGate):
    """
    Gate 1: Data Ingestion
    Validates raw data exists and passes quality checks
    """
    
    def check(self, symbol: str, check_date: date, workflow_id: Optional[str] = None) -> GateResult:
        """Check if data ingestion is complete and valid"""
        try:
            # Check 1: Raw data exists (check latest date, not necessarily check_date)
            # This allows for data from previous trading day
            raw_data = db.execute_query(
                """
                SELECT COUNT(*) as count, MAX(date) as latest_date
                FROM raw_market_data
                WHERE stock_symbol = :symbol
                """,
                {"symbol": symbol}
            )
            
            if not raw_data or raw_data[0]['count'] == 0:
                result = GateResult(
                    passed=False,
                    reason=f"No raw data found for {symbol}",
                    action="RETRY_INGESTION"
                )
                self._log_gate_result(workflow_id, "ingestion", symbol, result)
                return result
            
            # Check 2: Validation report exists and passed
            validation = db.execute_query(
                """
                SELECT overall_status, critical_issues, warnings, rows_dropped
                FROM data_validation_reports
                WHERE symbol = :symbol AND data_type = 'price_historical'
                ORDER BY validation_timestamp DESC
                LIMIT 1
                """,
                {"symbol": symbol}
            )
            
            if not validation:
                result = GateResult(
                    passed=False,
                    reason=f"No validation report found for {symbol}",
                    action="VALIDATE_DATA"
                )
                self._log_gate_result(workflow_id, "ingestion", symbol, result)
                return result
            
            val = validation[0]
            if val['overall_status'] == 'fail':
                result = GateResult(
                    passed=False,
                    reason=f"Data validation failed: {val['critical_issues']} critical issues, {val['warnings']} warnings",
                    action="FIX_DATA_QUALITY",
                    metadata={
                        "critical_issues": val['critical_issues'],
                        "warnings": val['warnings'],
                        "rows_dropped": val['rows_dropped']
                    }
                )
                self._log_gate_result(workflow_id, "ingestion", symbol, result)
                return result
            
            # Check 3: Data is recent (within last 5 days for EOD data)
            if raw_data[0]['latest_date']:
                latest_date = datetime.strptime(raw_data[0]['latest_date'], '%Y-%m-%d').date() if isinstance(raw_data[0]['latest_date'], str) else raw_data[0]['latest_date']
                days_old = (date.today() - latest_date).days
                if days_old > 5:
                    result = GateResult(
                        passed=False,
                        reason=f"Data is stale: {days_old} days old",
                        action="REFRESH_DATA"
                    )
                    self._log_gate_result(workflow_id, "ingestion", symbol, result)
                    return result
            
            # All checks passed
            result = GateResult(
                passed=True,
                reason=f"Data ingestion validated for {symbol}",
                metadata={"row_count": raw_data[0]['count']}
            )
            self._log_gate_result(workflow_id, "ingestion", symbol, result)
            return result
            
        except Exception as e:
            logger.error(f"Error in DataIngestionGate for {symbol}: {e}", exc_info=True)
            result = GateResult(
                passed=False,
                reason=f"Gate check error: {str(e)}",
                action="RETRY_INGESTION"
            )
            self._log_gate_result(workflow_id, "ingestion", symbol, result)
            return result


class IndicatorComputationGate(BaseGate):
    """
    Gate 2: Indicator Computation
    Validates indicators are computed and valid
    """
    
    def check(self, symbol: str, check_date: date, workflow_id: Optional[str] = None) -> GateResult:
        """Check if indicators are computed and valid"""
        try:
            # Check 1: Indicators exist (check latest date, not necessarily check_date)
            indicators = db.execute_query(
                """
                SELECT 
                    ema9, ema21, sma50, sma100, sma200,
                    ema12, ema26, ema20, ema50,
                    rsi, macd, macd_signal, atr
                FROM aggregated_indicators
                WHERE stock_symbol = :symbol
                ORDER BY date DESC
                LIMIT 1
                """,
                {"symbol": symbol}
            )
            
            if not indicators:
                result = GateResult(
                    passed=False,
                    reason=f"No indicators found for {symbol}",
                    action="COMPUTE_INDICATORS"
                )
                self._log_gate_result(workflow_id, "indicators", symbol, result)
                return result
            
            # Check 2: Critical indicators are not null
            ind = indicators[0]
            required_indicators = {
                'ema9': ind.get('ema9'),
                'sma50': ind.get('sma50'),
                'sma200': ind.get('sma200'),
                'rsi': ind.get('rsi'),
                'macd': ind.get('macd')
            }
            
            missing = [name for name, value in required_indicators.items() if value is None]
            
            if missing:
                result = GateResult(
                    passed=False,
                    reason=f"Missing critical indicators: {', '.join(missing)}",
                    action="RECOMPUTE_INDICATORS",
                    metadata={"missing_indicators": missing}
                )
                self._log_gate_result(workflow_id, "indicators", symbol, result)
                return result
            
            # Check 3: Indicators are reasonable (not NaN, not extreme)
            # RSI should be 0-100
            if ind.get('rsi') is not None:
                rsi = float(ind['rsi'])
                if rsi < 0 or rsi > 100:
                    result = GateResult(
                        passed=False,
                        reason=f"Invalid RSI value: {rsi} (expected 0-100)",
                        action="RECOMPUTE_INDICATORS"
                    )
                    self._log_gate_result(workflow_id, "indicators", symbol, result)
                    return result
            
            # All checks passed
            result = GateResult(
                passed=True,
                reason=f"Indicators validated for {symbol}",
                metadata={"indicators_available": len([v for v in required_indicators.values() if v is not None])}
            )
            self._log_gate_result(workflow_id, "indicators", symbol, result)
            return result
            
        except Exception as e:
            logger.error(f"Error in IndicatorComputationGate for {symbol}: {e}", exc_info=True)
            result = GateResult(
                passed=False,
                reason=f"Gate check error: {str(e)}",
                action="RECOMPUTE_INDICATORS"
            )
            self._log_gate_result(workflow_id, "indicators", symbol, result)
            return result


class SignalGenerationGate(BaseGate):
    """
    Gate 3: Signal Generation
    Validates data is ready for signal generation
    """
    
    def __init__(self):
        self.readiness_validator = SignalReadinessValidator()
    
    def check(self, symbol: str, check_date: date, workflow_id: Optional[str] = None) -> GateResult:
        """Check if signals can be generated"""
        try:
            # Use SignalReadinessValidator
            readiness = self.readiness_validator.check_readiness(symbol, "swing_trend")
            
            if readiness.readiness_status == "not_ready":
                result = GateResult(
                    passed=False,
                    reason=f"Signal readiness check failed: {', '.join(readiness.readiness_reason)}",
                    action="FIX_DATA_QUALITY",
                    metadata={
                        "readiness_status": readiness.readiness_status,
                        "data_quality_score": readiness.data_quality_score,
                        "missing_indicators": readiness.missing_indicators,
                        "recommendations": readiness.recommendations
                    }
                )
                self._log_gate_result(workflow_id, "signals", symbol, result)
                return result
            
            if readiness.readiness_status == "partial":
                # Partial readiness - allow but log warning
                logger.warning(f"Partial readiness for {symbol}: {', '.join(readiness.readiness_reason)}")
                result = GateResult(
                    passed=True,
                    reason=f"Partial readiness (quality score: {readiness.data_quality_score:.2f})",
                    action="MONITOR",
                    metadata={
                        "readiness_status": readiness.readiness_status,
                        "data_quality_score": readiness.data_quality_score,
                        "warnings": readiness.readiness_reason
                    }
                )
                self._log_gate_result(workflow_id, "signals", symbol, result)
                return result
            
            # Ready
            result = GateResult(
                passed=True,
                reason=f"Signal generation ready for {symbol}",
                metadata={
                    "readiness_status": readiness.readiness_status,
                    "data_quality_score": readiness.data_quality_score
                }
            )
            self._log_gate_result(workflow_id, "signals", symbol, result)
            return result
            
        except Exception as e:
            logger.error(f"Error in SignalGenerationGate for {symbol}: {e}", exc_info=True)
            result = GateResult(
                passed=False,
                reason=f"Gate check error: {str(e)}",
                action="RETRY_SIGNAL_CHECK"
            )
            self._log_gate_result(workflow_id, "signals", symbol, result)
            return result

