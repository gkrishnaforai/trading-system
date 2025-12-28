"""
Signal Readiness Validator
Checks if data is ready for signal generation (BUY/SELL/HOLD)
Industry Standard: Multi-source validation, indicator availability checks
"""
import logging
import json
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from dataclasses import dataclass
import uuid

from app.data_validation.validator import ValidationReport
from app.database import db

logger = logging.getLogger(__name__)


@dataclass
class SignalReadinessResult:
    """Result of signal readiness check"""
    symbol: str
    signal_type: str
    readiness_status: str  # 'ready', 'not_ready', 'partial'
    required_indicators: List[str]
    available_indicators: List[str]
    missing_indicators: List[str]
    data_quality_score: float  # 0.0 to 1.0
    validation_report_id: Optional[str]
    readiness_reason: str
    recommendations: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "readiness_status": self.readiness_status,
            "required_indicators": self.required_indicators,
            "available_indicators": self.available_indicators,
            "missing_indicators": self.missing_indicators,
            "data_quality_score": self.data_quality_score,
            "validation_report_id": self.validation_report_id,
            "readiness_reason": self.readiness_reason,
            "recommendations": self.recommendations
        }


class SignalReadinessValidator:
    """
    Validates if data is ready for signal generation
    
    Industry Standard Requirements:
    1. Sufficient historical data (minimum periods for indicators)
    2. All required indicators can be calculated
    3. Data quality meets thresholds
    4. Multi-source validation (if enabled)
    """
    
    # Signal type requirements
    SIGNAL_REQUIREMENTS = {
        'swing_trend': {
            'required_indicators': ['ema9', 'ema21', 'sma50', 'rsi', 'macd', 'atr'],
            'min_periods': 50,
            'min_valid_tail': 2,  # Need at least 2 valid values at tail for EMAs
            'data_quality_threshold': 0.8
        },
        'technical': {
            'required_indicators': ['ema20', 'sma50', 'sma200', 'rsi', 'macd'],
            'min_periods': 200,
            'min_valid_tail': 1,
            'data_quality_threshold': 0.7
        },
        'hybrid_llm': {
            'required_indicators': ['ema20', 'sma50', 'rsi', 'macd'],
            'min_periods': 200,
            'min_valid_tail': 1,
            'data_quality_threshold': 0.7
        }
    }
    
    def check_readiness(
        self,
        symbol: str,
        signal_type: str,
        validation_report: Optional[ValidationReport] = None
    ) -> SignalReadinessResult:
        """
        Check if data is ready for signal generation
        
        Args:
            symbol: Stock symbol
            signal_type: Type of signal ('swing_trend', 'technical', 'hybrid_llm')
            validation_report: Optional validation report (if not provided, fetches latest)
        
        Returns:
            SignalReadinessResult with readiness status and details
        """
        logger.info(f"🔍 Checking signal readiness for {symbol} (signal_type: {signal_type})")
        
        # Get requirements for this signal type
        requirements = self.SIGNAL_REQUIREMENTS.get(signal_type)
        if not requirements:
            return SignalReadinessResult(
                symbol=symbol,
                signal_type=signal_type,
                readiness_status='not_ready',
                required_indicators=[],
                available_indicators=[],
                missing_indicators=[],
                data_quality_score=0.0,
                validation_report_id=None,
                readiness_reason=f"Unknown signal type: {signal_type}",
                recommendations=[f"Use a valid signal type: {list(self.SIGNAL_REQUIREMENTS.keys())}"]
            )
        
        # Get validation report if not provided
        if validation_report is None:
            validation_report = self._get_latest_validation_report(symbol)
        
        # Check data availability
        data_available = self._check_data_availability(symbol, requirements['min_periods'])
        
        # Check indicator availability
        indicator_status = self._check_indicator_availability(
            symbol,
            requirements['required_indicators'],
            requirements['min_valid_tail']
        )
        
        # Calculate data quality score
        data_quality_score = self._calculate_data_quality_score(validation_report)
        
        # Determine readiness status
        readiness_status, reason, recommendations = self._determine_readiness(
            symbol,
            data_available,
            indicator_status,
            data_quality_score,
            requirements,
            validation_report
        )
        
        result = SignalReadinessResult(
            symbol=symbol,
            signal_type=signal_type,
            readiness_status=readiness_status,
            required_indicators=requirements['required_indicators'],
            available_indicators=indicator_status['available'],
            missing_indicators=indicator_status['missing'],
            data_quality_score=data_quality_score,
            validation_report_id=validation_report.report_id if validation_report else None,
            readiness_reason=reason,
            recommendations=recommendations
        )
        
        # Save to database
        self._save_readiness_result(result)
        
        logger.info(f"✅ Signal readiness check complete: {readiness_status.upper()} for {symbol}")
        
        return result
    
    def _get_latest_validation_report(self, symbol: str) -> Optional[ValidationReport]:
        """Get latest validation report for symbol"""
        try:
            query = """
                SELECT report_id, report_json, validation_timestamp
                FROM data_validation_reports
                WHERE symbol = :symbol AND data_type = 'price_historical'
                ORDER BY validation_timestamp DESC
                LIMIT 1
            """
            result = db.execute_query(query, {"symbol": symbol})
            if result:
                import json
                from datetime import datetime
                from app.data_validation.validator import ValidationReport, ValidationResult, ValidationIssue, ValidationSeverity
                
                row = result[0]
                report_dict = json.loads(row['report_json'])
                
                # Reconstruct ValidationReport from dict
                validation_results = []
                for vr_dict in report_dict.get('validation_results', []):
                    issues = []
                    for issue_dict in vr_dict.get('issues', []):
                        issue = ValidationIssue(
                            check_name=issue_dict.get('check_name', ''),
                            severity=ValidationSeverity(issue_dict.get('severity', 'info')),
                            message=issue_dict.get('message', ''),
                            affected_rows=issue_dict.get('affected_rows'),
                            affected_columns=issue_dict.get('affected_columns'),
                            metric_value=issue_dict.get('metric_value'),
                            threshold=issue_dict.get('threshold'),
                            recommendation=issue_dict.get('recommendation')
                        )
                        issues.append(issue)
                    
                    result_obj = ValidationResult(
                        check_name=vr_dict.get('check_name', ''),
                        passed=vr_dict.get('passed', False),
                        severity=ValidationSeverity(vr_dict.get('severity', 'info')),
                        issues=issues,
                        metrics=vr_dict.get('metrics', {}),
                        rows_checked=vr_dict.get('rows_checked', 0),
                        rows_failed=vr_dict.get('rows_failed', 0)
                    )
                    validation_results.append(result_obj)
                
                # Parse timestamp
                timestamp_str = row.get('validation_timestamp') or report_dict.get('timestamp')
                if isinstance(timestamp_str, str):
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                else:
                    timestamp = datetime.now()
                
                report = ValidationReport(
                    symbol=report_dict.get('symbol', symbol),
                    data_type=report_dict.get('data_type', 'price_historical'),
                    timestamp=timestamp,
                    total_rows=report_dict.get('total_rows', 0),
                    total_columns=report_dict.get('total_columns', 0),
                    rows_after_cleaning=report_dict.get('rows_after_cleaning', 0),
                    rows_dropped=report_dict.get('rows_dropped', 0),
                    validation_results=validation_results,
                    overall_status=report_dict.get('overall_status', 'unknown'),
                    critical_issues=report_dict.get('critical_issues', 0),
                    warnings=report_dict.get('warnings', 0),
                    recommendations=report_dict.get('recommendations', [])
                )
                # Set report_id from database
                report.report_id = row.get('report_id')
                return report
        except Exception as e:
            logger.warning(f"Could not fetch validation report: {e}")
        return None
    
    def _check_data_availability(self, symbol: str, min_periods: int) -> Dict[str, Any]:
        """Check if sufficient data is available"""
        try:
            query = """
                SELECT COUNT(*) as row_count
                FROM raw_market_data
                WHERE stock_symbol = :symbol
            """
            result = db.execute_query(query, {"symbol": symbol})
            row_count = result[0]['row_count'] if result else 0
            
            return {
                'available': row_count >= min_periods,
                'row_count': row_count,
                'min_required': min_periods,
                'sufficient': row_count >= min_periods
            }
        except Exception as e:
            logger.error(f"Error checking data availability: {e}")
            return {'available': False, 'row_count': 0, 'min_required': min_periods, 'sufficient': False}
    
    def _check_indicator_availability(
        self,
        symbol: str,
        required_indicators: List[str],
        min_valid_tail: int
    ) -> Dict[str, Any]:
        """Check if required indicators are available and valid"""
        try:
            # Check aggregated_indicators table
            query = """
                SELECT 
                    ema9, ema21, sma50, sma200, ema20, ema50,
                    rsi, macd, macd_signal, atr
                FROM aggregated_indicators
                WHERE stock_symbol = :symbol
                ORDER BY date DESC
                LIMIT 1
            """
            result = db.execute_query(query, {"symbol": symbol})
            
            available = []
            missing = []
            
            if result:
                latest = result[0]
                # Map indicator names to database columns
                indicator_map = {
                    'ema9': 'ema9',
                    'ema21': 'ema21',
                    'sma50': 'sma50',
                    'sma200': 'sma200',
                    'ema20': 'ema20',
                    'ema50': 'ema50',
                    'rsi': 'rsi',
                    'macd': 'macd',  # Database column is 'macd', not 'macd_line'
                    'atr': 'atr'
                }
                
                for indicator in required_indicators:
                    db_col = indicator_map.get(indicator)
                    if db_col and latest.get(db_col) is not None:
                        # Check if value is valid (not NaN, not 0 for some indicators)
                        value = latest[db_col]
                        if value is not None and (isinstance(value, (int, float)) and not (isinstance(value, float) and (value != value or value == 0))):
                            available.append(indicator)
                        else:
                            missing.append(indicator)
                    else:
                        missing.append(indicator)
            else:
                # No indicators calculated yet
                missing = required_indicators.copy()
            
            return {
                'available': available,
                'missing': missing,
                'all_available': len(missing) == 0
            }
        except Exception as e:
            logger.error(f"Error checking indicator availability: {e}")
            return {
                'available': [],
                'missing': required_indicators.copy(),
                'all_available': False
            }
    
    def _calculate_data_quality_score(self, validation_report: Optional[ValidationReport]) -> float:
        """Calculate data quality score (0.0 to 1.0)"""
        if validation_report is None:
            return 0.0
        
        # Base score
        score = 1.0
        
        # Deduct for critical issues
        if validation_report.critical_issues > 0:
            score -= min(0.5, validation_report.critical_issues * 0.1)
        
        # Deduct for warnings
        if validation_report.warnings > 0:
            score -= min(0.3, validation_report.warnings * 0.05)
        
        # Deduct for dropped rows
        if validation_report.rows_dropped > 0:
            drop_ratio = validation_report.rows_dropped / max(1, validation_report.total_rows)
            score -= min(0.2, drop_ratio)
        
        return max(0.0, min(1.0, score))
    
    def _determine_readiness(
        self,
        symbol: str,
        data_available: Dict[str, Any],
        indicator_status: Dict[str, Any],
        data_quality_score: float,
        requirements: Dict[str, Any],
        validation_report: Optional[ValidationReport]
    ) -> tuple[str, str, List[str]]:
        """Determine readiness status, reason, and recommendations"""
        recommendations = []
        
        # Check data availability
        if not data_available.get('sufficient', False):
            return (
                'not_ready',
                f"Insufficient data: have {data_available.get('row_count', 0)} periods, need {requirements['min_periods']}",
                [f"Fetch at least {requirements['min_periods']} periods of historical data"]
            )
        
        # Check indicators
        if not indicator_status.get('all_available', False):
            missing = indicator_status.get('missing', [])
            recommendations = [
                f"❌ Missing indicators: {', '.join(missing)}",
                "📊 **Action Required:** Calculate indicators for this symbol",
                "💡 **Solution:** Click 'Calculate Indicators' button below or use API: POST /api/v1/refresh-data with data_types=['indicators']",
                "🔍 **Why:** Indicators are calculated from price data. Price data exists but indicators haven't been calculated yet.",
                "⚡ **Quick Fix:** Go to '📥 Fetch Data' section and ensure 'Calculate Indicators' checkbox is checked, then fetch data again."
            ]
            return (
                'not_ready',
                f"Missing required indicators: {', '.join(missing)}. Price data exists but indicators need to be calculated.",
                recommendations
            )
        
        # Check data quality
        if data_quality_score < requirements['data_quality_threshold']:
            recommendations = []
            
            if validation_report is None:
                # No validation report exists - need to fetch data first
                recommendations = [
                    "❌ **Missing Validation Report:** No data quality validation has been performed",
                    "📊 **What's Missing:** Validation report (data quality check) for price data",
                    "💡 **Action Required:** Fetch historical price data to trigger validation",
                    "🔧 **Solution:**",
                    "   1. Go to '📥 Fetch Data' section in Testbed",
                    "   2. Select symbol: " + symbol,
                    "   3. Check 'Price Historical' data type",
                    "   4. Click 'Fetch Data' button",
                    "   5. This will automatically:",
                    "      - Fetch price data from source",
                    "      - Validate data quality",
                    "      - Calculate indicators",
                    "      - Generate validation report",
                    "⚡ **API Call:** POST /api/v1/fetch-historical-data with symbol=" + symbol,
                    "🔍 **Why:** Validation report is created automatically when price data is fetched. Without it, we cannot assess data quality."
                ]
            else:
                # Validation report exists but quality is low
                critical_count = validation_report.critical_issues
                warning_count = validation_report.warnings
                dropped_rows = validation_report.rows_dropped
                total_rows = validation_report.total_rows
                
                recommendations = [
                    f"⚠️ **Data Quality Issue:** Score {data_quality_score:.2f} is below threshold {requirements['data_quality_threshold']}",
                    f"📊 **Quality Metrics:**",
                    f"   - Critical Issues: {critical_count}",
                    f"   - Warnings: {warning_count}",
                    f"   - Rows Dropped: {dropped_rows} of {total_rows} ({dropped_rows/max(1,total_rows)*100:.1f}%)",
                    f"💡 **Action Required:** Review and fix data quality issues",
                    f"🔧 **Solutions:**"
                ]
                
                if critical_count > 0:
                    recommendations.append(f"   1. ❌ **CRITICAL:** {critical_count} critical issue(s) found - data may be unusable")
                    recommendations.append("      → Review validation report details for specific issues")
                    recommendations.append("      → Re-fetch data from alternative source (Finnhub fallback)")
                    recommendations.append("      → Check data source API status")
                
                if warning_count > 0:
                    recommendations.append(f"   2. ⚠️ **WARNINGS:** {warning_count} warning(s) - may affect accuracy")
                    recommendations.append("      → Review validation report for specific warnings")
                    recommendations.append("      → Consider data cleaning or filtering")
                
                if dropped_rows > 0:
                    drop_pct = (dropped_rows / max(1, total_rows)) * 100
                    recommendations.append(f"   3. 📉 **DROPPED ROWS:** {dropped_rows} rows ({drop_pct:.1f}%) were dropped during cleaning")
                    if drop_pct > 10:
                        recommendations.append("      → High drop rate may indicate data source issues")
                        recommendations.append("      → Consider fetching from alternative source")
                    else:
                        recommendations.append("      → Normal cleaning process, but may affect indicator accuracy")
                
                recommendations.extend([
                    "🔍 **View Details:** Check 'Validation & Audit' section for full validation report",
                    "⚡ **Quick Fix:** Re-fetch data: POST /api/v1/fetch-historical-data with symbol=" + symbol,
                    "📋 **Validation Report ID:** " + (validation_report.report_id or "N/A")
                ])
            
            return (
                'partial',
                f"Data quality below threshold: {data_quality_score:.2f} < {requirements['data_quality_threshold']}" + 
                ("" if validation_report else " (No validation report found)"),
                recommendations
            )
        
        # All checks passed
        return (
            'ready',
            f"Data is ready for {requirements} signal generation. Quality score: {data_quality_score:.2f}",
            []
        )
    
    def _save_readiness_result(self, result: SignalReadinessResult):
        """Save readiness result to database"""
        try:
            readiness_id = f"{result.symbol}_{result.signal_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
            query = """
                INSERT OR REPLACE INTO signal_readiness
                (readiness_id, symbol, signal_type, readiness_status, required_indicators,
                 available_indicators, missing_indicators, data_quality_score,
                 validation_report_id, readiness_timestamp, readiness_reason, recommendations)
                VALUES (:readiness_id, :symbol, :signal_type, :readiness_status, :required_indicators,
                        :available_indicators, :missing_indicators, :data_quality_score,
                        :validation_report_id, :timestamp, :reason, :recommendations)
            """
            db.execute_update(query, {
                "readiness_id": readiness_id,
                "symbol": result.symbol,
                "signal_type": result.signal_type,
                "readiness_status": result.readiness_status,
                "required_indicators": json.dumps(result.required_indicators),
                "available_indicators": json.dumps(result.available_indicators),
                "missing_indicators": json.dumps(result.missing_indicators),
                "data_quality_score": result.data_quality_score,
                "validation_report_id": result.validation_report_id,
                "timestamp": datetime.now(),
                "reason": result.readiness_reason,
                "recommendations": json.dumps(result.recommendations)
            })
        except Exception as e:
            logger.warning(f"Failed to save readiness result (non-critical): {e}")

