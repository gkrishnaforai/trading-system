"""
Data Quality Checks
Individual validation checks for financial market data
Each check is independent and can be run separately
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod

# Import types directly from validator
# This is safe because validator doesn't import checks at module level
from app.data_validation.validator import (
    ValidationResult,
    ValidationIssue,
    ValidationSeverity
)

logger = logging.getLogger(__name__)


class DataQualityCheck(ABC):
    """Base class for data quality checks"""
    
    @abstractmethod
    def validate(
        self,
        data: pd.DataFrame,
        symbol: str,
        data_type: str
    ) -> ValidationResult:
        """Run validation check"""
        pass
    
    def _normalize_column_names(self, data: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names to lowercase"""
        data = data.copy()
        data.columns = [col.lower() for col in data.columns]
        return data


class MissingValuesCheck(DataQualityCheck):
    """Check for missing values in critical columns"""
    
    def validate(
        self,
        data: pd.DataFrame,
        symbol: str,
        data_type: str
    ) -> ValidationResult:
        """Check for missing values"""
        data = self._normalize_column_names(data)
        
        issues = []
        critical_cols = ['close', 'high', 'low', 'open', 'volume']
        available_cols = [col for col in critical_cols if col in data.columns]
        
        if not available_cols:
            return ValidationResult(
                check_name="MissingValuesCheck",
                passed=False,
                severity=ValidationSeverity.CRITICAL,
                issues=[ValidationIssue(
                    check_name="MissingValuesCheck",
                    severity=ValidationSeverity.CRITICAL,
                    message="No critical columns found (close, high, low, open, volume)",
                    recommendation="Check data source - required columns are missing"
                )],
                rows_checked=len(data),
                rows_failed=len(data)
            )
        
        total_missing = 0
        for col in available_cols:
            missing_count = data[col].isna().sum()
            missing_pct = (missing_count / len(data)) * 100 if len(data) > 0 else 0
            total_missing += missing_count
            
            if missing_count > 0:
                severity = ValidationSeverity.CRITICAL if missing_pct > 10 else ValidationSeverity.WARNING
                issues.append(ValidationIssue(
                    check_name="MissingValuesCheck",
                    severity=severity,
                    message=f"Column '{col}' has {missing_count} missing values ({missing_pct:.1f}%)",
                    affected_columns=[col],
                    metric_value=missing_pct,
                    threshold=10.0,
                    recommendation=f"Fill missing values in '{col}' or remove affected rows"
                ))
        
        passed = total_missing == 0
        severity = ValidationSeverity.CRITICAL if not passed and any(
            i.severity == ValidationSeverity.CRITICAL for i in issues
        ) else ValidationSeverity.WARNING if not passed else ValidationSeverity.INFO
        
        return ValidationResult(
            check_name="MissingValuesCheck",
            passed=passed,
            severity=severity,
            issues=issues,
            metrics={"total_missing": total_missing, "missing_percentage": (total_missing / (len(data) * len(available_cols))) * 100},
            rows_checked=len(data),
            rows_failed=total_missing
        )


class DuplicateCheck(DataQualityCheck):
    """Check for duplicate rows"""
    
    def validate(
        self,
        data: pd.DataFrame,
        symbol: str,
        data_type: str
    ) -> ValidationResult:
        """Check for duplicates"""
        data = self._normalize_column_names(data)
        
        # Check for duplicate rows
        duplicates = data.duplicated()
        duplicate_count = duplicates.sum()
        
        issues = []
        if duplicate_count > 0:
            duplicate_indices = data[duplicates].index.tolist()
            duplicate_pct = (duplicate_count / len(data)) * 100 if len(data) > 0 else 0
            
            severity = ValidationSeverity.CRITICAL if duplicate_pct > 5 else ValidationSeverity.WARNING
            issues.append(ValidationIssue(
                check_name="DuplicateCheck",
                severity=severity,
                message=f"Found {duplicate_count} duplicate rows ({duplicate_pct:.1f}%)",
                affected_rows=duplicate_indices,
                metric_value=duplicate_pct,
                threshold=5.0,
                recommendation="Remove duplicate rows before analysis"
            ))
        
        return ValidationResult(
            check_name="DuplicateCheck",
            passed=duplicate_count == 0,
            severity=ValidationSeverity.WARNING if duplicate_count > 0 else ValidationSeverity.INFO,
            issues=issues,
            metrics={"duplicate_count": duplicate_count},
            rows_checked=len(data),
            rows_failed=duplicate_count
        )


class DataTypeCheck(DataQualityCheck):
    """Check that numeric columns are actually numeric"""
    
    def validate(
        self,
        data: pd.DataFrame,
        symbol: str,
        data_type: str
    ) -> ValidationResult:
        """Check data types"""
        data = self._normalize_column_names(data)
        
        issues = []
        numeric_cols = ['close', 'high', 'low', 'open', 'volume']
        available_cols = [col for col in numeric_cols if col in data.columns]
        
        for col in available_cols:
            if not pd.api.types.is_numeric_dtype(data[col]):
                # Try to convert
                try:
                    pd.to_numeric(data[col], errors='raise')
                    issues.append(ValidationIssue(
                        check_name="DataTypeCheck",
                        severity=ValidationSeverity.WARNING,
                        message=f"Column '{col}' is not numeric but can be converted",
                        affected_columns=[col],
                        recommendation=f"Convert '{col}' to numeric type"
                    ))
                except (ValueError, TypeError):
                    issues.append(ValidationIssue(
                        check_name="DataTypeCheck",
                        severity=ValidationSeverity.CRITICAL,
                        message=f"Column '{col}' contains non-numeric values that cannot be converted",
                        affected_columns=[col],
                        recommendation=f"Fix non-numeric values in '{col}' or remove affected rows"
                    ))
        
        return ValidationResult(
            check_name="DataTypeCheck",
            passed=len(issues) == 0,
            severity=ValidationSeverity.CRITICAL if any(
                i.severity == ValidationSeverity.CRITICAL for i in issues
            ) else ValidationSeverity.WARNING if issues else ValidationSeverity.INFO,
            issues=issues,
            rows_checked=len(data),
            rows_failed=len([i for i in issues if i.severity == ValidationSeverity.CRITICAL])
        )


class RangeCheck(DataQualityCheck):
    """Check that values are within reasonable ranges"""
    
    def validate(
        self,
        data: pd.DataFrame,
        symbol: str,
        data_type: str
    ) -> ValidationResult:
        """Check value ranges"""
        data = self._normalize_column_names(data)
        
        issues = []
        
        # Price columns must be positive
        price_cols = ['close', 'high', 'low', 'open']
        for col in price_cols:
            if col in data.columns:
                negative_count = (data[col] <= 0).sum()
                if negative_count > 0:
                    issues.append(ValidationIssue(
                        check_name="RangeCheck",
                        severity=ValidationSeverity.CRITICAL,
                        message=f"Column '{col}' has {negative_count} non-positive values",
                        affected_columns=[col],
                        metric_value=negative_count,
                        recommendation=f"Remove or fix non-positive values in '{col}'"
                    ))
                
                # Check high >= low, high >= close, etc.
                if 'high' in data.columns and 'low' in data.columns:
                    invalid_high_low = (data['high'] < data['low']).sum()
                    if invalid_high_low > 0:
                        issues.append(ValidationIssue(
                            check_name="RangeCheck",
                            severity=ValidationSeverity.CRITICAL,
                            message=f"Found {invalid_high_low} rows where high < low",
                            metric_value=invalid_high_low,
                            recommendation="Fix rows where high < low (data corruption)"
                        ))
        
        # Volume should be non-negative
        if 'volume' in data.columns:
            negative_volume = (data['volume'] < 0).sum()
            if negative_volume > 0:
                issues.append(ValidationIssue(
                    check_name="RangeCheck",
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Column 'volume' has {negative_volume} negative values",
                    affected_columns=['volume'],
                    metric_value=negative_volume,
                    recommendation="Fix negative volume values"
                ))
        
        return ValidationResult(
            check_name="RangeCheck",
            passed=len(issues) == 0,
            severity=ValidationSeverity.CRITICAL if issues else ValidationSeverity.INFO,
            issues=issues,
            rows_checked=len(data),
            rows_failed=sum(i.metric_value or 0 for i in issues)
        )


class OutlierCheck(DataQualityCheck):
    """Check for statistical outliers"""
    
    def validate(
        self,
        data: pd.DataFrame,
        symbol: str,
        data_type: str
    ) -> ValidationResult:
        """Check for outliers using IQR method"""
        data = self._normalize_column_names(data)
        
        issues = []
        
        if 'close' not in data.columns:
            return ValidationResult(
                check_name="OutlierCheck",
                passed=True,
                severity=ValidationSeverity.INFO,
                rows_checked=len(data),
                rows_failed=0
            )
        
        # Use IQR method for outlier detection
        close_prices = pd.to_numeric(data['close'], errors='coerce')
        Q1 = close_prices.quantile(0.25)
        Q3 = close_prices.quantile(0.75)
        IQR = Q3 - Q1
        
        lower_bound = Q1 - 3 * IQR  # More lenient (3x IQR)
        upper_bound = Q3 + 3 * IQR
        
        outliers = ((close_prices < lower_bound) | (close_prices > upper_bound)).sum()
        outlier_pct = (outliers / len(data)) * 100 if len(data) > 0 else 0
        
        if outliers > 0:
            # Outliers in financial data can be valid (splits, crashes, etc.)
            # So we mark as warning, not critical
            issues.append(ValidationIssue(
                check_name="OutlierCheck",
                severity=ValidationSeverity.WARNING,
                message=f"Found {outliers} potential outliers ({outlier_pct:.1f}%) using IQR method",
                metric_value=outlier_pct,
                threshold=5.0,
                recommendation="Review outliers - they may be valid market events (splits, crashes) or data errors"
            ))
        
        return ValidationResult(
            check_name="OutlierCheck",
            passed=outliers == 0,
            severity=ValidationSeverity.WARNING if outliers > 0 else ValidationSeverity.INFO,
            issues=issues,
            metrics={"outlier_count": outliers, "outlier_percentage": outlier_pct},
            rows_checked=len(data),
            rows_failed=outliers
        )


class ContinuityCheck(DataQualityCheck):
    """Check time series continuity (no large gaps)"""
    
    def validate(
        self,
        data: pd.DataFrame,
        symbol: str,
        data_type: str
    ) -> ValidationResult:
        """Check for gaps in time series"""
        data = self._normalize_column_names(data)
        
        issues = []
        
        # Try to find date column
        date_col = None
        for col in ['date', 'timestamp', 'time']:
            if col in data.columns:
                date_col = col
                break
        
        if date_col is None:
            # Check if index is datetime
            if isinstance(data.index, pd.DatetimeIndex):
                date_col = "index"
            else:
                return ValidationResult(
                    check_name="ContinuityCheck",
                    passed=True,
                    severity=ValidationSeverity.INFO,
                    issues=[ValidationIssue(
                        check_name="ContinuityCheck",
                        severity=ValidationSeverity.INFO,
                        message="No date column found, skipping continuity check"
                    )],
                    rows_checked=len(data),
                    rows_failed=0
                )
        
        # Get dates
        if date_col == "index":
            dates = data.index
        else:
            dates = pd.to_datetime(data[date_col], errors='coerce')
        
        # Sort by date
        dates_sorted = dates.sort_values()
        
        # Calculate gaps
        if len(dates_sorted) > 1:
            date_diffs = dates_sorted.diff().dropna()
            
            # For daily data, expect ~1 day gaps (weekends/holidays are OK)
            # Large gaps (> 7 days) might indicate missing data
            large_gaps = (date_diffs > pd.Timedelta(days=7)).sum()
            
            if large_gaps > 0:
                issues.append(ValidationIssue(
                    check_name="ContinuityCheck",
                    severity=ValidationSeverity.WARNING,
                    message=f"Found {large_gaps} gaps larger than 7 days in time series",
                    metric_value=large_gaps,
                    recommendation="Review large gaps - may indicate missing data periods"
                ))
        
        return ValidationResult(
            check_name="ContinuityCheck",
            passed=len(issues) == 0,
            severity=ValidationSeverity.WARNING if issues else ValidationSeverity.INFO,
            issues=issues,
            rows_checked=len(data),
            rows_failed=0
        )


class VolumeCheck(DataQualityCheck):
    """Check volume data quality"""
    
    def validate(
        self,
        data: pd.DataFrame,
        symbol: str,
        data_type: str
    ) -> ValidationResult:
        """Check volume data"""
        data = self._normalize_column_names(data)
        
        issues = []
        
        if 'volume' not in data.columns:
            return ValidationResult(
                check_name="VolumeCheck",
                passed=True,
                severity=ValidationSeverity.INFO,
                issues=[ValidationIssue(
                    check_name="VolumeCheck",
                    severity=ValidationSeverity.INFO,
                    message="Volume column not found, skipping volume check"
                )],
                rows_checked=len(data),
                rows_failed=0
            )
        
        volume = pd.to_numeric(data['volume'], errors='coerce')
        
        # Check for zero volume (may be valid for some days, but too many is suspicious)
        zero_volume = (volume == 0).sum()
        zero_volume_pct = (zero_volume / len(data)) * 100 if len(data) > 0 else 0
        
        if zero_volume_pct > 20:  # More than 20% zero volume is suspicious
            issues.append(ValidationIssue(
                check_name="VolumeCheck",
                severity=ValidationSeverity.WARNING,
                message=f"Found {zero_volume} zero-volume days ({zero_volume_pct:.1f}%)",
                metric_value=zero_volume_pct,
                threshold=20.0,
                recommendation="Review zero-volume days - may indicate data quality issues"
            ))
        
        return ValidationResult(
            check_name="VolumeCheck",
            passed=zero_volume_pct <= 20,
            severity=ValidationSeverity.WARNING if issues else ValidationSeverity.INFO,
            issues=issues,
            metrics={"zero_volume_count": zero_volume, "zero_volume_percentage": zero_volume_pct},
            rows_checked=len(data),
            rows_failed=zero_volume
        )


class IndicatorDataCheck(DataQualityCheck):
    """
    Check if data is sufficient for indicator calculations
    Industry Standard: Verify data can support required technical indicators
    """
    
    def validate(
        self,
        data: pd.DataFrame,
        symbol: str,
        data_type: str
    ) -> ValidationResult:
        """Check if data supports indicator calculations"""
        data = self._normalize_column_names(data)
        
        issues = []
        
        if 'close' not in data.columns:
            return ValidationResult(
                check_name="IndicatorDataCheck",
                passed=False,
                severity=ValidationSeverity.CRITICAL,
                issues=[ValidationIssue(
                    check_name="IndicatorDataCheck",
                    severity=ValidationSeverity.CRITICAL,
                    message="Missing 'close' column - required for all indicator calculations",
                    recommendation="Ensure 'close' price data is available"
                )],
                rows_checked=len(data),
                rows_failed=len(data)
            )
        
        close = pd.to_numeric(data['close'], errors='coerce')
        valid_close_count = close.notna().sum()
        total_rows = len(data)
        
        # Required indicators and their minimum data requirements
        indicator_requirements = {
            'EMA9': 9,
            'EMA21': 21,
            'SMA50': 50,
            'RSI14': 14,
            'MACD': 26,  # MACD typically uses 12, 26, 9
            'ATR14': 14
        }
        
        # Check if we have enough data for each indicator
        for indicator_name, min_periods in indicator_requirements.items():
            if valid_close_count < min_periods:
                issues.append(ValidationIssue(
                    check_name="IndicatorDataCheck",
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Insufficient data for {indicator_name}: need {min_periods} periods, have {valid_close_count} valid close prices",
                    metric_value=valid_close_count,
                    threshold=min_periods,
                    recommendation=f"Fetch at least {min_periods} periods of historical data for {indicator_name} calculation"
                ))
        
        # Check if we have enough data for swing trading (needs EMA9, EMA21, SMA50 minimum)
        swing_trading_min = max(indicator_requirements['EMA9'], indicator_requirements['EMA21'], indicator_requirements['SMA50'])
        if valid_close_count < swing_trading_min:
            issues.append(ValidationIssue(
                check_name="IndicatorDataCheck",
                severity=ValidationSeverity.CRITICAL,
                message=f"Insufficient data for swing trading signals: need at least {swing_trading_min} periods, have {valid_close_count}",
                metric_value=valid_close_count,
                threshold=swing_trading_min,
                recommendation=f"Fetch at least {swing_trading_min} periods (preferably 200+) of historical data for swing trading"
            ))
        
        # Check data quality for indicator calculation
        # Need at least 2 valid values at the end for EMA calculations
        if valid_close_count >= 21:  # Have enough for EMA21
            # Check last few values are valid (needed for current signal)
            last_valid_count = close.tail(21).notna().sum()
            if last_valid_count < 2:
                issues.append(ValidationIssue(
                    check_name="IndicatorDataCheck",
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Insufficient valid data at tail: need at least 2 valid values in last 21 periods for EMA calculations, have {last_valid_count}",
                    metric_value=last_valid_count,
                    threshold=2,
                    recommendation="Data has gaps at the end - fill missing values or fetch more recent data"
                ))
        
        passed = len(issues) == 0
        severity = ValidationSeverity.CRITICAL if not passed else ValidationSeverity.INFO
        
        return ValidationResult(
            check_name="IndicatorDataCheck",
            passed=passed,
            severity=severity,
            issues=issues,
            metrics={
                "total_rows": total_rows,
                "valid_close_count": valid_close_count,
                "indicator_requirements": indicator_requirements
            },
            rows_checked=total_rows,
            rows_failed=total_rows - valid_close_count if not passed else 0
        )
