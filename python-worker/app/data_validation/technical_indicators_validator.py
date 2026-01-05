from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from .validator import ValidationReport, ValidationResult, ValidationIssue, ValidationSeverity

class TechnicalIndicatorsValidator:
    """Validator for technical indicators data"""
    
    def __init__(self):
        # Define valid ranges for common indicators
        self.indicator_ranges = {
            'RSI': {'min': 0, 'max': 100},
            'STOCH': {'min': 0, 'max': 100},
            'STOCHRSI': {'min': 0, 'max': 100},
            'WILLR': {'min': -100, 'max': 0},
            'ADX': {'min': 0, 'max': 100},
            'CCI': {'min': -200, 'max': 200},
            'ATR': {'min': 0, 'max': float('inf')},
            'MFI': {'min': 0, 'max': 100},
            'OBV': {'min': float('-inf'), 'max': float('inf')},  # Can be negative
            'FORCE': {'min': float('-inf'), 'max': float('inf')},  # Can be negative
            'MACD': {'min': float('-inf'), 'max': float('inf')},  # Can be negative
            'EMA': {'min': 0, 'max': float('inf')},  # Price indicators
            'SMA': {'min': 0, 'max': float('inf')},  # Price indicators
            'BBANDS': {'min': 0, 'max': float('inf')},  # Price bands
        }
        
        # Define valid time periods for indicators
        self.valid_periods = {
            'RSI': [5, 7, 9, 10, 12, 14, 21, 25, 28, 30],
            'STOCH': [5, 7, 9, 10, 12, 14, 21, 25, 28, 30],
            'STOCHRSI': [5, 7, 9, 10, 12, 14, 21, 25, 28, 30],
            'WILLR': [5, 7, 9, 10, 12, 14, 21, 25, 28, 30],
            'ADX': [5, 7, 9, 10, 12, 14, 21, 25, 28, 30],
            'CCI': [5, 7, 9, 10, 12, 14, 21, 25, 28, 30],
            'ATR': [5, 7, 9, 10, 12, 14, 21, 25, 28, 30],
            'MFI': [5, 7, 9, 10, 12, 14, 21, 25, 28, 30],
            'EMA': [5, 7, 9, 10, 12, 14, 21, 25, 28, 30, 50, 100, 200],
            'SMA': [5, 7, 9, 10, 12, 14, 21, 25, 28, 30, 50, 100, 200],
            'BBANDS': [5, 7, 9, 10, 12, 14, 21, 25, 28, 30, 50, 100, 200],
        }
        
        # Required fields for each indicator type
        self.required_fields = {
            'RSI': ['date', 'value', 'period'],
            'STOCH': ['date', 'slowd', 'slowk', 'period'],
            'STOCHRSI': ['date', 'fastd', 'fastk', 'period'],
            'WILLR': ['date', 'value', 'period'],
            'ADX': ['date', 'value', 'period'],
            'CCI': ['date', 'value', 'period'],
            'ATR': ['date', 'value', 'period'],
            'MFI': ['date', 'value', 'period'],
            'OBV': ['date', 'value'],
            'FORCE': ['date', 'value', 'period'],
            'MACD': ['date', 'macd', 'signal', 'histogram', 'period'],
            'EMA': ['date', 'value', 'period'],
            'SMA': ['date', 'value', 'period'],
            'BBANDS': ['date', 'upper_band', 'middle_band', 'lower_band', 'period'],
        }
    
    def validate(self, indicators_data: Dict[str, List[Dict[str, Any]]], symbol: str, data_type: str = "technical_indicators") -> ValidationReport:
        """Validate technical indicators data and return a ValidationReport"""
        
        issues = []
        total_indicators = 0
        
        if not indicators_data:
            issues.append(ValidationIssue(
                field="indicators_data",
                severity=ValidationSeverity.CRITICAL,
                message="No indicators data provided",
                value=None,
                recommendation="Ensure indicators data is fetched from the data source"
            ))
            return self._create_report(symbol, data_type, issues, 0)
        
        for indicator_type, data in indicators_data.items():
            if not data:
                issues.append(ValidationIssue(
                    field=indicator_type,
                    severity=ValidationSeverity.WARNING,
                    message=f"No data for indicator type: {indicator_type}",
                    value=None,
                    recommendation=f"Check if {indicator_type} data is available for {symbol}"
                ))
                continue
            
            total_indicators += len(data)
            
            # Validate indicator type
            if indicator_type not in self.required_fields:
                issues.append(ValidationIssue(
                    field="indicator_type",
                    severity=ValidationSeverity.WARNING,
                    message=f"Unknown indicator type: {indicator_type}",
                    value=indicator_type,
                    recommendation=f"Add validation rules for {indicator_type} or check data source"
                ))
                continue
            
            # Validate each data point
            for i, item in enumerate(data):
                item_issues = self._validate_indicator_item(indicator_type, item, i)
                issues.extend(item_issues)
        
        # Determine overall status
        critical_issues = [i for i in issues if i.severity == ValidationSeverity.CRITICAL]
        overall_status = "fail" if critical_issues else "pass"
        
        # Calculate validation score
        score = max(0, 100 - len(critical_issues) * 20 - len(issues) * 2)
        
        return ValidationReport(
            symbol=symbol,
            data_type=data_type,
            timestamp=datetime.utcnow(),
            overall_status=overall_status,
            validation_result=ValidationResult(
                is_valid=overall_status == "pass",
                issues=issues,
                score=score
            )
        )
    
    def _validate_indicator_item(self, indicator_type: str, item: Dict[str, Any], index: int) -> List[ValidationIssue]:
        """Validate a single indicator data point"""
        issues = []
        
        # Check required fields
        for field in self.required_fields.get(indicator_type, []):
            if field not in item or item[field] is None:
                issues.append(ValidationIssue(
                    field=f"{indicator_type}[{index}].{field}",
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Missing required field '{field}' in {indicator_type} data",
                    value=item.get(field),
                    recommendation=f"Ensure '{field}' is included in {indicator_type} data"
                ))
        
        # Validate date field
        if 'date' in item:
            date_value = item['date']
            if date_value is None:
                issues.append(ValidationIssue(
                    field=f"{indicator_type}[{index}].date",
                    severity=ValidationSeverity.CRITICAL,
                    message="Date field is null",
                    value=None,
                    recommendation="Provide valid date for indicator data"
                ))
            elif not isinstance(date_value, (datetime, str)):
                issues.append(ValidationIssue(
                    field=f"{indicator_type}[{index}].date",
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Invalid date type: {type(date_value)}",
                    value=date_value,
                    recommendation="Date should be datetime object or ISO string"
                ))
        
        # Validate period field
        if 'period' in item and item['period'] is not None:
            period = item['period']
            valid_periods = self.valid_periods.get(indicator_type, [])
            if valid_periods and period not in valid_periods:
                issues.append(ValidationIssue(
                    field=f"{indicator_type}[{index}].period",
                    severity=ValidationSeverity.WARNING,
                    message=f"Unusual period value: {period} for {indicator_type}",
                    value=period,
                    recommendation=f"Expected periods: {valid_periods}"
                ))
        
        # Validate numeric ranges
        for field, value in item.items():
            if field in ['value', 'slowd', 'slowk', 'fastd', 'fastk', 'macd', 'signal', 'histogram', 
                        'upper_band', 'middle_band', 'lower_band'] and value is not None:
                try:
                    numeric_value = float(value)
                    range_info = self.indicator_ranges.get(indicator_type, {})
                    
                    if 'min' in range_info and numeric_value < range_info['min']:
                        issues.append(ValidationIssue(
                            field=f"{indicator_type}[{index}].{field}",
                            severity=ValidationSeverity.WARNING,
                            message=f"Value {numeric_value} below minimum {range_info['min']} for {indicator_type}",
                            value=numeric_value,
                            recommendation=f"Check data source for {indicator_type} calculation errors"
                        ))
                    
                    if 'max' in range_info and numeric_value > range_info['max']:
                        issues.append(ValidationIssue(
                            field=f"{indicator_type}[{index}].{field}",
                            severity=ValidationSeverity.WARNING,
                            message=f"Value {numeric_value} above maximum {range_info['max']} for {indicator_type}",
                            value=numeric_value,
                            recommendation=f"Check data source for {indicator_type} calculation errors"
                        ))
                    
                    # Check for NaN or infinite values
                    if numeric_value != numeric_value or numeric_value in [float('inf'), float('-inf')]:
                        issues.append(ValidationIssue(
                            field=f"{indicator_type}[{index}].{field}",
                            severity=ValidationSeverity.CRITICAL,
                            message=f"Invalid numeric value: {numeric_value}",
                            value=numeric_value,
                            recommendation="Replace NaN/Infinity with valid numbers"
                        ))
                        
                except (ValueError, TypeError):
                    issues.append(ValidationIssue(
                        field=f"{indicator_type}[{index}].{field}",
                        severity=ValidationSeverity.CRITICAL,
                        message=f"Invalid numeric value: {value}",
                        value=value,
                        recommendation="Ensure numeric fields contain valid numbers"
                    ))
        
        # Special validations for specific indicators
        if indicator_type == 'MACD':
            issues.extend(self._validate_macd_item(item, index))
        elif indicator_type == 'BBANDS':
            issues.extend(self._validate_bbands_item(item, index))
        elif indicator_type in ['STOCH', 'STOCHRSI']:
            issues.extend(self._validate_stoch_item(item, indicator_type, index))
        
        return issues
    
    def _validate_macd_item(self, item: Dict[str, Any], index: int) -> List[ValidationIssue]:
        """Special validation for MACD indicator"""
        issues = []
        
        # Check MACD line relationship with signal line
        macd = item.get('macd')
        signal = item.get('signal')
        
        if macd is not None and signal is not None:
            try:
                macd_val = float(macd)
                signal_val = float(signal)
                
                # Histogram should equal MACD - Signal
                histogram = item.get('histogram')
                if histogram is not None:
                    hist_val = float(histogram)
                    expected_hist = macd_val - signal_val
                    if abs(hist_val - expected_hist) > 0.001:  # Small tolerance for floating point
                        issues.append(ValidationIssue(
                            field=f"MACD[{index}].histogram",
                            severity=ValidationSeverity.WARNING,
                            message=f"MACD histogram inconsistency: expected {expected_hist}, got {hist_val}",
                            value=hist_val,
                            recommendation="Verify MACD calculation: histogram should equal MACD - signal"
                        ))
            except (ValueError, TypeError):
                issues.append(ValidationIssue(
                    field=f"MACD[{index}]",
                    severity=ValidationSeverity.CRITICAL,
                    message="Invalid numeric values in MACD data",
                    value=item,
                    recommendation="Ensure MACD values are valid numbers"
                ))
        
        return issues
    
    def _validate_bbands_item(self, item: Dict[str, Any], index: int) -> List[ValidationIssue]:
        """Special validation for Bollinger Bands"""
        issues = []
        
        upper = item.get('upper_band')
        middle = item.get('middle_band')
        lower = item.get('lower_band')
        
        if all(v is not None for v in [upper, middle, lower]):
            try:
                upper_val = float(upper)
                middle_val = float(middle)
                lower_val = float(lower)
                
                # Upper band should be >= middle band >= lower band
                if upper_val < middle_val:
                    issues.append(ValidationIssue(
                        field=f"BBANDS[{index}].upper_band",
                        severity=ValidationSeverity.WARNING,
                        message=f"Upper band {upper_val} should be >= middle band {middle_val}",
                        value=upper_val,
                        recommendation="Check Bollinger Bands calculation"
                    ))
                
                if middle_val < lower_val:
                    issues.append(ValidationIssue(
                        field=f"BBANDS[{index}].middle_band",
                        severity=ValidationSeverity.WARNING,
                        message=f"Middle band {middle_val} should be >= lower band {lower_val}",
                        value=middle_val,
                        recommendation="Check Bollinger Bands calculation"
                    ))
                
                # All values should be positive
                if any(v <= 0 for v in [upper_val, middle_val, lower_val]):
                    issues.append(ValidationIssue(
                        field=f"BBANDS[{index}]",
                        severity=ValidationSeverity.WARNING,
                        message="Bollinger Bands should be positive values",
                        value=item,
                        recommendation="Check for price data errors in Bollinger Bands calculation"
                    ))
                    
            except (ValueError, TypeError):
                issues.append(ValidationIssue(
                    field=f"BBANDS[{index}]",
                    severity=ValidationSeverity.CRITICAL,
                    message="Invalid numeric values in Bollinger Bands",
                    value=item,
                    recommendation="Ensure Bollinger Bands values are valid numbers"
                ))
        
        return issues
    
    def _validate_stoch_item(self, item: Dict[str, Any], indicator_type: str, index: int) -> List[ValidationIssue]:
        """Special validation for Stochastic oscillators"""
        issues = []
        
        if indicator_type == 'STOCH':
            slowk = item.get('slowk')
            slowd = item.get('slowd')
            values = [slowk, slowd]
            fields = ['slowk', 'slowd']
        else:  # STOCHRSI
            fastk = item.get('fastk')
            fastd = item.get('fastd')
            values = [fastk, fastd]
            fields = ['fastk', 'fastd']
        
        for value, field in zip(values, fields):
            if value is not None:
                try:
                    val = float(value)
                    if val < 0 or val > 100:
                        issues.append(ValidationIssue(
                            field=f"{indicator_type}[{index}].{field}",
                            severity=ValidationSeverity.WARNING,
                            message=f"{field} value {val} should be between 0 and 100",
                            value=val,
                            recommendation="Check Stochastic oscillator calculation"
                        ))
                except (ValueError, TypeError):
                    issues.append(ValidationIssue(
                        field=f"{indicator_type}[{index}].{field}",
                        severity=ValidationSeverity.CRITICAL,
                        message=f"Invalid {field} value: {value}",
                        value=value,
                        recommendation=f"Ensure {field} is a valid number"
                    ))
        
        return issues
    
    def _create_report(self, symbol: str, data_type: str, issues: List[ValidationIssue], total_indicators: int) -> ValidationReport:
        """Create a validation report"""
        critical_issues = [i for i in issues if i.severity == ValidationSeverity.CRITICAL]
        overall_status = "fail" if critical_issues else "pass"
        score = max(0, 100 - len(critical_issues) * 20 - len(issues) * 2)
        
        return ValidationReport(
            symbol=symbol,
            data_type=data_type,
            timestamp=datetime.utcnow(),
            overall_status=overall_status,
            validation_result=ValidationResult(
                is_valid=overall_status == "pass",
                issues=issues,
                score=score
            )
        )
    
    def summarize_issues(self, report: ValidationReport) -> Dict[str, Any]:
        """Create a summary of issues for audit metadata"""
        critical_count = len([i for i in report.validation_result.issues if i.severity == ValidationSeverity.CRITICAL])
        warning_count = len([i for i in report.validation_result.issues if i.severity == ValidationSeverity.WARNING])
        
        # Count issues by indicator type
        indicator_issues = {}
        for issue in report.validation_result.issues:
            field = issue.field
            if '[' in field:
                indicator_type = field.split('[')[0]
                indicator_issues[indicator_type] = indicator_issues.get(indicator_type, 0) + 1
        
        return {
            "validation_status": report.overall_status,
            "critical_issues": critical_count,
            "warning_count": warning_count,
            "total_issues": len(report.validation_result.issues),
            "validation_score": report.validation_result.score,
            "indicator_issues": indicator_issues,
            "missing_fields": [i.field for i in report.validation_result.issues if "missing" in i.message.lower()],
            "range_violations": [i.field for i in report.validation_result.issues if "below minimum" in i.message.lower() or "above maximum" in i.message.lower()]
        }
