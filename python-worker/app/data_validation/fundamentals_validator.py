from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.data_validation.validator import (
    ValidationIssue,
    ValidationReport,
    ValidationResult,
    ValidationSeverity,
)


@dataclass(frozen=True)
class FundamentalsValidationConfig:
    critical_required_keys: Tuple[str, ...] = (
        "market_cap",
        "pe_ratio",
        "eps",
        "revenue",
        "debt_to_equity",
        "sector",
        "industry",
    )

    warning_required_keys: Tuple[str, ...] = (
        "forward_pe",
        "dividend_yield",
        "profit_margin",
        "current_ratio",
        "price_to_sales",
        "roe",
        "revenue_growth",
    )


class FundamentalsValidator:
    """Validate a fundamentals payload dict and generate a ValidationReport."""

    def __init__(self, config: Optional[FundamentalsValidationConfig] = None):
        self.config = config or FundamentalsValidationConfig()

    def validate(self, payload: Dict[str, Any], symbol: str, data_type: str = "fundamentals") -> ValidationReport:
        timestamp = datetime.now()

        if not payload or not isinstance(payload, dict):
            return ValidationReport(
                symbol=symbol,
                data_type=data_type,
                timestamp=timestamp,
                total_rows=0,
                total_columns=0,
                rows_after_cleaning=0,
                rows_dropped=0,
                overall_status="fail",
                critical_issues=1,
                recommendations=["Fundamentals payload is empty or not a dict. Check data source."],
            )

        total_columns = len(payload)
        issues: List[ValidationIssue] = []
        missing_required: List[str] = []
        missing_optional: List[str] = []
        invalid_fields: List[str] = []

        for k in self.config.critical_required_keys:
            v = payload.get(k)
            if v is None or (isinstance(v, str) and not v.strip()):
                missing_required.append(k)

        for k in self.config.warning_required_keys:
            v = payload.get(k)
            if v is None or (isinstance(v, str) and not v.strip()):
                missing_optional.append(k)

        if missing_required:
            issues.append(
                ValidationIssue(
                    check_name="FundamentalsRequiredFieldsCheck",
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Missing required fundamentals fields: {', '.join(missing_required)}",
                    affected_columns=missing_required,
                    recommendation="Re-fetch fundamentals later (provider may publish late) or use fallback source.",
                )
            )

        if missing_optional:
            issues.append(
                ValidationIssue(
                    check_name="FundamentalsOptionalFieldsCheck",
                    severity=ValidationSeverity.WARNING,
                    message=f"Missing optional fundamentals fields: {', '.join(missing_optional)}",
                    affected_columns=missing_optional,
                    recommendation="This is common for some providers/symbols; consider computing via other fields or using a fallback source if needed.",
                )
            )

        # Numeric sanity checks (industry-style guardrails; warnings vs critical)
        numeric_non_negative = ["market_cap", "revenue"]
        for k in numeric_non_negative:
            v = payload.get(k)
            if v is None:
                continue
            try:
                fv = float(v)
                if fv < 0:
                    invalid_fields.append(k)
                    issues.append(
                        ValidationIssue(
                            check_name="FundamentalsRangeCheck",
                            severity=ValidationSeverity.WARNING,
                            message=f"Field '{k}' is negative ({fv}).",
                            affected_columns=[k],
                            recommendation="Check provider payload; retry with fallback source if persists.",
                        )
                    )
            except Exception:
                invalid_fields.append(k)
                issues.append(
                    ValidationIssue(
                        check_name="FundamentalsTypeCheck",
                        severity=ValidationSeverity.WARNING,
                        message=f"Field '{k}' is not numeric.",
                        affected_columns=[k],
                        recommendation="Check provider payload; retry with fallback source if persists.",
                    )
                )

        # Optional but useful: sector/industry missing is warning
        for k in ("sector", "industry"):
            v = payload.get(k)
            if v is None or (isinstance(v, str) and not v.strip()):
                issues.append(
                    ValidationIssue(
                        check_name="FundamentalsClassificationCheck",
                        severity=ValidationSeverity.WARNING,
                        message=f"Field '{k}' is missing.",
                        affected_columns=[k],
                        recommendation="This may affect screeners/peer grouping; re-fetch later if needed.",
                    )
                )

        critical = sum(1 for i in issues if i.severity == ValidationSeverity.CRITICAL)
        warnings = sum(1 for i in issues if i.severity == ValidationSeverity.WARNING)

        overall_status = "pass"
        if critical > 0:
            overall_status = "fail"
        elif warnings > 0:
            overall_status = "warning"

        results: List[ValidationResult] = []
        if missing_required:
            results.append(
                ValidationResult(
                    check_name="FundamentalsRequiredFieldsCheck",
                    passed=False,
                    severity=ValidationSeverity.CRITICAL,
                    issues=[i for i in issues if i.check_name == "FundamentalsRequiredFieldsCheck"],
                    metrics={
                        "missing_required_count": len(missing_required),
                        "missing_required": missing_required,
                    },
                    rows_checked=1,
                    rows_failed=1,
                )
            )
        else:
            results.append(
                ValidationResult(
                    check_name="FundamentalsRequiredFieldsCheck",
                    passed=True,
                    severity=ValidationSeverity.INFO,
                    issues=[],
                    metrics={"missing_required_count": 0},
                    rows_checked=1,
                    rows_failed=0,
                )
            )

        if missing_optional:
            results.append(
                ValidationResult(
                    check_name="FundamentalsOptionalFieldsCheck",
                    passed=False,
                    severity=ValidationSeverity.WARNING,
                    issues=[i for i in issues if i.check_name == "FundamentalsOptionalFieldsCheck"],
                    metrics={
                        "missing_optional_count": len(missing_optional),
                        "missing_optional": missing_optional,
                    },
                    rows_checked=1,
                    rows_failed=0,
                )
            )
        else:
            results.append(
                ValidationResult(
                    check_name="FundamentalsOptionalFieldsCheck",
                    passed=True,
                    severity=ValidationSeverity.INFO,
                    issues=[],
                    metrics={"missing_optional_count": 0},
                    rows_checked=1,
                    rows_failed=0,
                )
            )

        type_or_range_issues = [
            i
            for i in issues
            if i.check_name in ("FundamentalsTypeCheck", "FundamentalsRangeCheck")
        ]
        if type_or_range_issues:
            results.append(
                ValidationResult(
                    check_name="FundamentalsTypeAndRangeChecks",
                    passed=False,
                    severity=ValidationSeverity.WARNING,
                    issues=type_or_range_issues,
                    metrics={"invalid_field_count": len(set(invalid_fields))},
                    rows_checked=1,
                    rows_failed=1,
                )
            )
        else:
            results.append(
                ValidationResult(
                    check_name="FundamentalsTypeAndRangeChecks",
                    passed=True,
                    severity=ValidationSeverity.INFO,
                    issues=[],
                    metrics={"invalid_field_count": 0},
                    rows_checked=1,
                    rows_failed=0,
                )
            )

        classification_issues = [i for i in issues if i.check_name == "FundamentalsClassificationCheck"]
        if classification_issues:
            results.append(
                ValidationResult(
                    check_name="FundamentalsClassificationCheck",
                    passed=False,
                    severity=ValidationSeverity.WARNING,
                    issues=classification_issues,
                    metrics={"missing_classification_count": len(classification_issues)},
                    rows_checked=1,
                    rows_failed=1,
                )
            )

        recommendations = list({i.recommendation for i in issues if i.recommendation})

        return ValidationReport(
            symbol=symbol,
            data_type=data_type,
            timestamp=timestamp,
            total_rows=1,
            total_columns=total_columns,
            rows_after_cleaning=1,
            rows_dropped=0,
            validation_results=results,
            overall_status=overall_status,
            critical_issues=critical,
            warnings=warnings,
            recommendations=recommendations,
        )

    def summarize_issues(self, report: ValidationReport) -> Dict[str, Any]:
        missing: List[str] = []
        invalid: List[str] = []
        for r in report.validation_results:
            for i in r.issues:
                if i.affected_columns:
                    if i.check_name == "FundamentalsRequiredFieldsCheck":
                        missing.extend(i.affected_columns)
                    if i.check_name in ("FundamentalsTypeCheck", "FundamentalsRangeCheck"):
                        invalid.extend(i.affected_columns)
        return {
            "missing_fields": sorted(set(missing)),
            "invalid_fields": sorted(set(invalid)),
            "overall_status": report.overall_status,
            "critical_issues": report.critical_issues,
            "warnings": report.warnings,
        }
