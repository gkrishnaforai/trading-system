"""
Data Validator
Comprehensive validation for financial market data
Industry Standard: Multi-layer validation with detailed reporting
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

# Import checks lazily to avoid circular import
# We'll import them in __init__ method instead

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation issues"""
    CRITICAL = "critical"  # Data unusable, must fix
    WARNING = "warning"     # Data quality concern, may affect accuracy
    INFO = "info"           # Minor issue, data still usable


@dataclass
class ValidationIssue:
    """Individual validation issue"""
    check_name: str
    severity: ValidationSeverity
    message: str
    affected_rows: Optional[List[int]] = None
    affected_columns: Optional[List[str]] = None
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    recommendation: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of a single validation check"""
    check_name: str
    passed: bool
    severity: ValidationSeverity
    issues: List[ValidationIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    rows_checked: int = 0
    rows_failed: int = 0


@dataclass
class ValidationReport:
    """Comprehensive validation report for a dataset"""
    symbol: str
    data_type: str
    timestamp: datetime
    total_rows: int
    total_columns: int
    rows_after_cleaning: int
    rows_dropped: int
    validation_results: List[ValidationResult] = field(default_factory=list)
    overall_status: str = "unknown"  # "pass", "warning", "fail"
    critical_issues: int = 0
    warnings: int = 0
    recommendations: List[str] = field(default_factory=list)
    report_id: Optional[str] = None  # Database report_id
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary for JSON serialization
        
        Ensures all values are JSON-serializable (converts numpy/pandas types to native Python types)
        """
        def _make_json_serializable(obj):
            """Recursively convert numpy/pandas types to native Python types"""
            if isinstance(obj, (np.integer, np.floating)):
                return float(obj) if isinstance(obj, np.floating) else int(obj)
            elif isinstance(obj, np.bool_):
                return bool(obj)
            elif isinstance(obj, (np.ndarray, pd.Series)):
                return obj.tolist()
            elif isinstance(obj, pd.Timestamp):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: _make_json_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_make_json_serializable(item) for item in obj]
            elif isinstance(obj, (bool, int, float, str, type(None))):
                return obj
            else:
                # Fallback: convert to string for unknown types
                return str(obj)
        
        return {
            "symbol": self.symbol,
            "data_type": self.data_type,
            "timestamp": self.timestamp.isoformat(),
            "total_rows": int(self.total_rows),
            "total_columns": int(self.total_columns),
            "rows_after_cleaning": int(self.rows_after_cleaning),
            "rows_dropped": int(self.rows_dropped),
            "overall_status": self.overall_status,
            "critical_issues": int(self.critical_issues),
            "warnings": int(self.warnings),
            "validation_results": [
                {
                    "check_name": r.check_name,
                    "passed": bool(r.passed),  # Ensure native bool
                    "severity": r.severity.value,
                    "rows_checked": int(r.rows_checked),
                    "rows_failed": int(r.rows_failed),
                    "issues": [
                        {
                            "message": i.message,
                            "severity": i.severity.value,
                            "affected_columns": i.affected_columns,
                            "metric_value": _make_json_serializable(i.metric_value),
                            "threshold": _make_json_serializable(i.threshold),
                            "recommendation": i.recommendation
                        }
                        for i in r.issues
                    ],
                    "metrics": _make_json_serializable(r.metrics)
                }
                for r in self.validation_results
            ],
            "recommendations": self.recommendations
        }


class DataValidator:
    """
    Comprehensive data validator for financial market data
    
    Industry Standard Validation Checks:
    1. Missing Values - Critical for time series continuity
    2. Duplicates - Prevent data skewing
    3. Data Types - Ensure numeric columns are numeric
    4. Range Checks - Price/volume must be positive, reasonable ranges
    5. Outliers - Detect anomalies (statistical + domain knowledge)
    6. Continuity - Time series should be continuous (no large gaps)
    7. Volume Checks - Volume should be non-negative, reasonable
    
    Best Practices:
    - Fail fast on critical issues
    - Report all issues with severity levels
    - Provide actionable recommendations
    - Track validation history
    """
    
    def __init__(self):
        """Initialize validator with standard checks"""
        # Import checks here to avoid circular import
        # Checks import types from validator, which are already defined at this point
        from app.data_validation.checks import (
            MissingValuesCheck,
            DuplicateCheck,
            DataTypeCheck,
            RangeCheck,
            OutlierCheck,
            ContinuityCheck,
            VolumeCheck,
            IndicatorDataCheck
        )
        
        self.checks: List['DataQualityCheck'] = [
            MissingValuesCheck(),
            DuplicateCheck(),
            DataTypeCheck(),
            RangeCheck(),
            OutlierCheck(),
            ContinuityCheck(),
            VolumeCheck(),
            IndicatorDataCheck()  # Check if data supports indicator calculations
        ]
    
    def validate(
        self,
        data: pd.DataFrame,
        symbol: str,
        data_type: str = "price_historical",
        strict: bool = True
    ) -> ValidationReport:
        """
        Validate financial market data
        
        Args:
            data: DataFrame with OHLCV data
            symbol: Stock symbol
            data_type: Type of data (price_historical, fundamentals, etc.)
            strict: If True, fail on critical issues
        
        Returns:
            ValidationReport with detailed results
        """
        if data is None or data.empty:
            return ValidationReport(
                symbol=symbol,
                data_type=data_type,
                timestamp=datetime.now(),
                total_rows=0,
                total_columns=0,
                rows_after_cleaning=0,
                rows_dropped=0,
                overall_status="fail",
                critical_issues=1,
                recommendations=["Data is empty or None. Check data source."]
            )
        
        logger.info(f"🔍 Validating {data_type} data for {symbol}: {len(data)} rows, {len(data.columns)} columns")
        
        # Track original state
        original_rows = len(data)
        original_columns = len(data.columns)
        
        # Run all validation checks
        validation_results: List[ValidationResult] = []
        critical_issues_count = 0
        warnings_count = 0
        
        for check in self.checks:
            try:
                result = check.validate(data, symbol, data_type)
                validation_results.append(result)
                
                # Count issues by severity
                for issue in result.issues:
                    if issue.severity == ValidationSeverity.CRITICAL:
                        critical_issues_count += 1
                    elif issue.severity == ValidationSeverity.WARNING:
                        warnings_count += 1
                
                # Log critical failures
                if not result.passed and result.severity == ValidationSeverity.CRITICAL:
                    logger.error(f"❌ Critical validation failure for {symbol}: {result.check_name}")
                    for issue in result.issues:
                        logger.error(f"   - {issue.message}")
                
            except Exception as e:
                logger.error(f"Error running {check.__class__.__name__} for {symbol}: {e}", exc_info=True)
                validation_results.append(ValidationResult(
                    check_name=check.__class__.__name__,
                    passed=False,
                    severity=ValidationSeverity.CRITICAL,
                    issues=[ValidationIssue(
                        check_name=check.__class__.__name__,
                        severity=ValidationSeverity.CRITICAL,
                        message=f"Validation check failed with exception: {str(e)}"
                    )],
                    rows_checked=len(data),
                    rows_failed=len(data)
                ))
                critical_issues_count += 1
        
        # Determine overall status
        if critical_issues_count > 0:
            overall_status = "fail"
        elif warnings_count > 0:
            overall_status = "warning"
        else:
            overall_status = "pass"
        
        # Generate recommendations
        recommendations = self._generate_recommendations(validation_results, data)
        
        # Calculate rows after cleaning (estimate based on validation issues)
        rows_dropped = self._estimate_rows_dropped(validation_results, data)
        rows_after_cleaning = original_rows - rows_dropped
        
        report = ValidationReport(
            symbol=symbol,
            data_type=data_type,
            timestamp=datetime.now(),
            total_rows=original_rows,
            total_columns=original_columns,
            rows_after_cleaning=rows_after_cleaning,
            rows_dropped=rows_dropped,
            validation_results=validation_results,
            overall_status=overall_status,
            critical_issues=critical_issues_count,
            warnings=warnings_count,
            recommendations=recommendations
        )
        
        # Log summary
        logger.info(f"✅ Validation complete for {symbol}: {overall_status.upper()} "
                   f"({critical_issues_count} critical, {warnings_count} warnings, "
                   f"{rows_dropped} rows would be dropped)")
        
        return report
    
    def _generate_recommendations(
        self,
        results: List[ValidationResult],
        data: pd.DataFrame
    ) -> List[str]:
        """Generate actionable recommendations based on validation results"""
        recommendations = []
        
        for result in results:
            if not result.passed:
                for issue in result.issues:
                    if issue.recommendation:
                        recommendations.append(issue.recommendation)
        
        # Add general recommendations
        if any(r.check_name == "MissingValuesCheck" and not r.passed for r in results):
            recommendations.append("Consider using forward-fill or interpolation for missing values")
        
        if any(r.check_name == "OutlierCheck" and not r.passed for r in results):
            recommendations.append("Review outliers - they may be valid market events or data errors")
        
        if any(r.check_name == "DuplicateCheck" and not r.passed for r in results):
            recommendations.append("Remove duplicate rows before analysis")
        
        return list(set(recommendations))  # Remove duplicates
    
    def _estimate_rows_dropped(
        self,
        results: List[ValidationResult],
        data: pd.DataFrame
    ) -> int:
        """Estimate how many rows would be dropped after cleaning"""
        dropped_rows = set()
        
        for result in results:
            if not result.passed and result.severity == ValidationSeverity.CRITICAL:
                for issue in result.issues:
                    if issue.affected_rows:
                        dropped_rows.update(issue.affected_rows)
        
        return len(dropped_rows)
    
    def validate_and_clean(
        self,
        data: pd.DataFrame,
        symbol: str,
        data_type: str = "price_historical"
    ) -> tuple[pd.DataFrame, ValidationReport]:
        """
        Validate and clean data (remove bad rows)
        
        Returns:
            Tuple of (cleaned_data, validation_report)
        """
        report = self.validate(data, symbol, data_type, strict=False)
        
        # Clean data based on critical issues
        cleaned_data = data.copy()
        rows_before = len(cleaned_data)
        
        for result in report.validation_results:
            if not result.passed and result.severity == ValidationSeverity.CRITICAL:
                for issue in result.issues:
                    if issue.affected_rows:
                        # Drop rows with critical issues
                        cleaned_data = cleaned_data.drop(cleaned_data.index[issue.affected_rows])
        
        # Remove duplicates
        cleaned_data = cleaned_data.drop_duplicates()
        
        # Remove rows with NaN in critical columns
        critical_cols = ['close', 'high', 'low', 'open']
        available_cols = [col for col in critical_cols if col in cleaned_data.columns]
        if available_cols:
            cleaned_data = cleaned_data.dropna(subset=available_cols)
        
        rows_after = len(cleaned_data)
        rows_dropped = rows_before - rows_after
        
        logger.info(f"🧹 Cleaned {symbol} data: {rows_before} → {rows_after} rows ({rows_dropped} dropped)")
        
        # Update report with actual cleaning results
        report.rows_dropped = rows_dropped
        report.rows_after_cleaning = rows_after
        
        return cleaned_data, report

