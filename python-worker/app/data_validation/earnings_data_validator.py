from typing import Dict, Any, List, Optional, Union
from datetime import datetime, date
from .validator import ValidationReport, ValidationResult, ValidationIssue, ValidationSeverity
from app.repositories.stocks_repository import StocksRepository, MissingSymbolsRepository

class EarningsDataValidator:
    """Validator for earnings data"""
    
    def __init__(self):
        # Define reasonable ranges for earnings values
        self.eps_ranges = {
            'min': -100,  # Allow negative EPS
            'max': 1000   # Very high but reasonable upper bound
        }
        
        self.revenue_ranges = {
            'min': 0,      # Revenue should not be negative
            'max': 1e12    # 1 trillion - very high but reasonable
        }
        
        # Required fields for earnings data
        self.required_fields = [
            'earnings_date',
            'symbol'
        ]
        
        # Optional but important fields
        self.important_fields = [
            'eps_actual',
            'eps_estimated',
            'revenue_actual',
            'revenue_estimated',
            'quarter',
            'year',
            'currency'
        ]
    
    def validate(self, earnings_data: List[Dict[str, Any]], symbol: str, data_type: str = "earnings_data") -> ValidationReport:
        """Validate earnings data and return a ValidationReport"""
        
        issues = []
        total_earnings = len(earnings_data) if earnings_data else 0
        
        if not earnings_data:
            issues.append(ValidationIssue(
                check_name="data_presence", field="earnings_data",
                severity=ValidationSeverity.CRITICAL,
                message="No earnings data provided",
                value=None,
                recommendation="Ensure earnings data is fetched from the data source"
            ))
            return self._create_report(symbol, data_type, issues, 0)
        
        for i, earning in enumerate(earnings_data):
            item_issues = self._validate_earnings_item(earning, i)
            issues.extend(item_issues)
        
        # Check for duplicate earnings dates
        date_counts = {}
        for i, earning in enumerate(earnings_data):
            if 'earnings_date' in earning and earning['earnings_date']:
                earning_date = earning['earnings_date']
                if isinstance(earning_date, datetime):
                    earning_date = earning_date.date()
                elif isinstance(earning_date, str):
                    try:
                        earning_date = datetime.fromisoformat(earning_date.replace('Z', '+00:00')).date()
                    except ValueError:
                        continue
                
                date_str = earning_date.isoformat()
                if date_str in date_counts:
                    date_counts[date_str].append(i)
                else:
                    date_counts[date_str] = [i]
        
        # Flag duplicate dates
        for date_str, indices in date_counts.items():
            if len(indices) > 1:
                issues.append(ValidationIssue(
                    check_name="duplicate_date_validation", field="duplicate_earnings_date",
                    severity=ValidationSeverity.WARNING,
                    message=f"Duplicate earnings date {date_str} found at indices {indices}",
                    value=date_str,
                    recommendation="Consolidate duplicate earnings records or verify data accuracy"
                ))
        
        # Determine overall status
        critical_issues = [i for i in issues if i.severity == ValidationSeverity.CRITICAL]
        overall_status = "fail" if critical_issues else "pass"
        
        # Calculate validation score
        score = max(0, 100 - len(critical_issues) * 20 - len(issues) * 3)
        
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
    
    def _validate_earnings_item(self, earning: Dict[str, Any], index: int) -> List[ValidationIssue]:
        """Validate a single earnings data point"""
        issues = []
        
        # Check required fields
        for field in self.required_fields:
            if field not in earning or earning[field] is None:
                issues.append(ValidationIssue(
                    field=f"earnings[{index}].{field}",
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Missing required field '{field}' in earnings data",
                    value=earning.get(field),
                    recommendation=f"Ensure '{field}' is included in earnings data"
                ))
        
        # Validate earnings_date
        if 'earnings_date' in earning and earning['earnings_date'] is not None:
            date_value = earning['earnings_date']
            validated_date = self._validate_date_field(date_value, f"earnings[{index}].earnings_date")
            if validated_date is None:
                issues.append(ValidationIssue(

                check_name="earnings_date_validation", field=f"earnings[{index}].earnings_date",
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Invalid earnings_date: {date_value}",
                    value=date_value,
                    recommendation="Provide valid date in ISO format or datetime object"
                ))
            else:
                # Check if date is in reasonable range (not too far in past or future)
                today = date.today()
                if validated_date < today.replace(year=today.year - 10):
                    issues.append(ValidationIssue(

                    check_name="earnings_date_validation", field=f"earnings[{index}].earnings_date",
                        severity=ValidationSeverity.WARNING,
                        message=f"Earnings date {validated_date} is more than 10 years in the past",
                        value=validated_date,
                        recommendation="Verify the earnings date is correct"
                    ))
                elif validated_date > today.replace(year=today.year + 2):
                    issues.append(ValidationIssue(

                    check_name="earnings_date_validation", field=f"earnings[{index}].earnings_date",
                        severity=ValidationSeverity.WARNING,
                        message=f"Earnings date {validated_date} is more than 2 years in the future",
                        value=validated_date,
                        recommendation="Verify the earnings date is correct"
                    ))
        
        # Validate symbol field
        if 'symbol' in earning and earning['symbol'] is not None:
            symbol_value = str(earning['symbol']).strip()
            if not symbol_value:
                issues.append(ValidationIssue(

                check_name="symbol_validation", field=f"earnings[{index}].symbol",
                    severity=ValidationSeverity.CRITICAL,
                    message="Symbol field is empty",
                    value=earning['symbol'],
                    recommendation="Provide valid stock symbol"
                ))
            elif len(symbol_value) > 10:
                issues.append(ValidationIssue(

                check_name="symbol_validation", field=f"earnings[{index}].symbol",
                    severity=ValidationSeverity.WARNING,
                    message=f"Unusually long symbol: {symbol_value}",
                    value=symbol_value,
                    recommendation="Verify the stock symbol is correct"
                ))
            else:
                # Check if symbol exists in stocks table, queue if missing
                try:
                    if not StocksRepository.symbol_exists(symbol_value):
                        # Add to missing symbols queue for enrichment
                        MissingSymbolsRepository.add_missing_symbol(
                            symbol_value, 
                            'earnings_calendar',
                            earning.get('id') if 'id' in earning else None
                        )
                        issues.append(ValidationIssue(
                            check_name="symbol_missing_validation",
                            field=f"earnings[{index}].symbol",
                            severity=ValidationSeverity.INFO,
                            message=f"Symbol {symbol_value} not found in master stocks table - queued for enrichment",
                            value=symbol_value,
                            recommendation="Symbol will be automatically enriched with stock data"
                        ))
                except Exception as e:
                    # Log error but don't fail validation
                    issues.append(ValidationIssue(
                        check_name="symbol_check_error",
                        field=f"earnings[{index}].symbol",
                        severity=ValidationSeverity.WARNING,
                        message=f"Could not verify symbol existence: {str(e)}",
                        value=symbol_value,
                        recommendation="Manual verification recommended"
                    ))
        
        # Validate EPS values
        for eps_field in ['eps_actual', 'eps_estimated']:
            if eps_field in earning and earning[eps_field] is not None:
                eps_value = earning[eps_field]
                try:
                    eps_numeric = float(eps_value)
                    if eps_numeric < self.eps_ranges['min'] or eps_numeric > self.eps_ranges['max']:
                        issues.append(ValidationIssue(
                            field=f"earnings[{index}].{eps_field}",
                            severity=ValidationSeverity.WARNING,
                            message=f"EPS value {eps_numeric} outside reasonable range [{self.eps_ranges['min']}, {self.eps_ranges['max']}]",
                            value=eps_numeric,
                            recommendation="Verify EPS calculation or data source accuracy"
                        ))
                    
                    # Check for NaN or infinite values
                    if eps_numeric != eps_numeric or eps_numeric in [float('inf'), float('-inf')]:
                        issues.append(ValidationIssue(
                            field=f"earnings[{index}].{eps_field}",
                            severity=ValidationSeverity.CRITICAL,
                            message=f"Invalid EPS value: {eps_numeric}",
                            value=eps_numeric,
                            recommendation="Replace NaN/Infinity with valid EPS numbers"
                        ))
                        
                except (ValueError, TypeError):
                    issues.append(ValidationIssue(
                        field=f"earnings[{index}].{eps_field}",
                        severity=ValidationSeverity.CRITICAL,
                        message=f"Invalid EPS value: {eps_value}",
                        value=eps_value,
                        recommendation="Ensure EPS fields contain valid numbers"
                    ))
        
        # Validate Revenue values
        for revenue_field in ['revenue_actual', 'revenue_estimated']:
            if revenue_field in earning and earning[revenue_field] is not None:
                revenue_value = earning[revenue_field]
                try:
                    revenue_numeric = float(revenue_value)
                    if revenue_numeric < self.revenue_ranges['min'] or revenue_numeric > self.revenue_ranges['max']:
                        issues.append(ValidationIssue(
                            field=f"earnings[{index}].{revenue_field}",
                            severity=ValidationSeverity.WARNING,
                            message=f"Revenue value {revenue_numeric} outside reasonable range [{self.revenue_ranges['min']}, {self.revenue_ranges['max']}]",
                            value=revenue_numeric,
                            recommendation="Verify revenue calculation or data source accuracy"
                        ))
                    
                    # Check for NaN or infinite values
                    if revenue_numeric != revenue_numeric or revenue_numeric in [float('inf'), float('-inf')]:
                        issues.append(ValidationIssue(
                            field=f"earnings[{index}].{revenue_field}",
                            severity=ValidationSeverity.CRITICAL,
                            message=f"Invalid revenue value: {revenue_numeric}",
                            value=revenue_numeric,
                            recommendation="Replace NaN/Infinity with valid revenue numbers"
                        ))
                        
                except (ValueError, TypeError):
                    issues.append(ValidationIssue(
                        field=f"earnings[{index}].{revenue_field}",
                        severity=ValidationSeverity.CRITICAL,
                        message=f"Invalid revenue value: {revenue_value}",
                        value=revenue_value,
                        recommendation="Ensure revenue fields contain valid numbers"
                    ))
        
        # Validate quarter and year
        if 'quarter' in earning and earning['quarter'] is not None:
            quarter_value = earning['quarter']
            try:
                quarter_numeric = int(quarter_value)
                if quarter_numeric < 1 or quarter_numeric > 4:
                    issues.append(ValidationIssue(

                    check_name="quarter_validation", field=f"earnings[{index}].quarter",
                        severity=ValidationSeverity.WARNING,
                        message=f"Quarter value {quarter_numeric} should be between 1 and 4",
                        value=quarter_numeric,
                        recommendation="Verify quarter value is correct"
                    ))
            except (ValueError, TypeError):
                issues.append(ValidationIssue(

                check_name="quarter_validation", field=f"earnings[{index}].quarter",
                    severity=ValidationSeverity.WARNING,
                    message=f"Invalid quarter value: {quarter_value}",
                    value=quarter_value,
                    recommendation="Quarter should be an integer between 1 and 4"
                ))
        
        if 'year' in earning and earning['year'] is not None:
            year_value = earning['year']
            try:
                year_numeric = int(year_value)
                current_year = date.today().year
                if year_numeric < current_year - 20 or year_numeric > current_year + 5:
                    issues.append(ValidationIssue(

                    check_name="year_validation", field=f"earnings[{index}].year",
                        severity=ValidationSeverity.WARNING,
                        message=f"Year value {year_numeric} seems unusual",
                        value=year_numeric,
                        recommendation="Verify year value is correct"
                    ))
            except (ValueError, TypeError):
                issues.append(ValidationIssue(

                check_name="year_validation", field=f"earnings[{index}].year",
                    severity=ValidationSeverity.WARNING,
                    message=f"Invalid year value: {year_value}",
                    value=year_value,
                    recommendation="Year should be a valid integer"
                ))
        
        # Validate currency
        if 'currency' in earning and earning['currency'] is not None:
            currency_value = str(earning['currency']).upper().strip()
            if len(currency_value) != 3:
                issues.append(ValidationIssue(

                check_name="currency_validation", field=f"earnings[{index}].currency",
                    severity=ValidationSeverity.WARNING,
                    message=f"Currency code should be 3 characters: {currency_value}",
                    value=currency_value,
                    recommendation="Use standard 3-letter currency codes (USD, EUR, etc.)"
                ))
        
        # Check for consistency between actual and estimated values
        if ('eps_actual' in earning and 'eps_estimated' in earning and 
            earning['eps_actual'] is not None and earning['eps_estimated'] is not None):
            try:
                actual_eps = float(earning['eps_actual'])
                estimated_eps = float(earning['eps_estimated'])
                
                # Check for extreme surprises (more than 1000% difference)
                if estimated_eps != 0:
                    surprise_pct = abs((actual_eps - estimated_eps) / estimated_eps) * 100
                    if surprise_pct > 1000:
                        issues.append(ValidationIssue(

                        check_name="eps_validation", field=f"earnings[{index}].eps_surprise",
                            severity=ValidationSeverity.WARNING,
                            message=f"Extreme EPS surprise: {surprise_pct:.1f}%",
                            value={"actual": actual_eps, "estimated": estimated_eps},
                            recommendation="Verify EPS values are correct and in same units"
                        ))
            except (ValueError, TypeError):
                issues.append(
                    ValidationIssue(
                        check_name="EPSConsistencyCheck",
                        severity=ValidationSeverity.WARNING,
                        message="Cannot compare EPS actual vs estimated values",
                        field=f"earnings[{index}].eps_consistency",
                        value=earning,
                        recommendation="Ensure both EPS values are valid numbers"
                    )
)
        
        # Check for missing important fields
        for field in self.important_fields:
            if field not in earning or earning[field] is None:
                issues.append(ValidationIssue(
                    field=f"earnings[{index}].{field}",
                    severity=ValidationSeverity.INFO,
                    message=f"Missing important field '{field}' in earnings data",
                    value=earning.get(field),
                    recommendation=f"Include '{field}' for more complete earnings analysis"
                ))
        
        return issues
    
    def _validate_date_field(self, date_value: Any, field_name: str) -> Optional[date]:
        """Validate and convert date field to date object"""
        if isinstance(date_value, datetime):
            return date_value.date()
        elif isinstance(date_value, date):
            return date_value
        elif isinstance(date_value, str):
            try:
                # Try ISO format first
                return datetime.fromisoformat(date_value.replace('Z', '+00:00')).date()
            except ValueError:
                try:
                    # Try other common formats
                    return datetime.strptime(date_value, '%Y-%m-%d').date()
                except ValueError:
                    return None
        return None
    
    def _create_report(self, symbol: str, data_type: str, issues: List[ValidationIssue], total_earnings: int) -> ValidationReport:
        """Create a validation report"""
        critical_issues = [i for i in issues if i.severity == ValidationSeverity.CRITICAL]
        overall_status = "fail" if critical_issues else "pass"
        score = max(0, 100 - len(critical_issues) * 20 - len(issues) * 3)
        
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
        info_count = len([i for i in report.validation_result.issues if i.severity == ValidationSeverity.INFO])
        
        # Count specific issue types
        missing_required = [i for i in report.validation_result.issues if "Missing required field" in i.message]
        missing_important = [i for i in report.validation_result.issues if "Missing important field" in i.message]
        range_violations = [i for i in report.validation_result.issues if "outside reasonable range" in i.message]
        date_issues = [i for i in report.validation_result.issues if "earnings_date" in i.field]
        
        return {
            "validation_status": report.overall_status,
            "critical_issues": critical_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "total_issues": len(report.validation_result.issues),
            "validation_score": report.validation_result.score,
            "missing_required_fields": len(missing_required),
            "missing_important_fields": len(missing_important),
            "range_violations": len(range_violations),
            "date_issues": len(date_issues),
            "missing_fields": [i.field for i in missing_required + missing_important],
            "fields_with_range_issues": [i.field for i in range_violations]
        }
