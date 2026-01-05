from typing import Dict, Any, List, Optional, Union
from datetime import datetime, date, timedelta
from .validator import ValidationReport, ValidationResult, ValidationIssue, ValidationSeverity

class MarketNewsValidator:
    """Validator for market news data"""
    
    def __init__(self):
        # Required fields for news articles
        self.required_fields = [
            'title',
            'publisher'
        ]
        
        # Important but optional fields
        self.important_fields = [
            'link',
            'published_date',
            'related_symbols'
        ]
        
        # Common news sources for validation
        self.known_publishers = [
            'Reuters', 'Bloomberg', 'CNBC', 'MarketWatch', 'Yahoo Finance',
            'Seeking Alpha', 'The Wall Street Journal', 'Financial Times',
            'Investopedia', 'Motley Fool', 'Business Insider', 'CNN Money',
            'Associated Press', 'Dow Jones', 'Nasdaq', 'NYSE'
        ]
        
        # Suspicious patterns in titles
        self.suspicious_patterns = [
            'click here', 'buy now', 'limited time', 'act fast',
            'guaranteed', 'risk free', 'get rich', 'make money fast',
            '!!!', '???', 'all caps', 'multiple exclamation'
        ]
    
    def validate(self, news_data: List[Dict[str, Any]], symbol: str, data_type: str = "market_news") -> ValidationReport:
        """Validate market news data and return a ValidationReport"""
        
        issues = []
        total_articles = len(news_data) if news_data else 0
        
        if not news_data:
            issues.append(ValidationIssue(
                check_name="data_presence",
                severity=ValidationSeverity.CRITICAL,
                message="No news data provided",
                value=None,
                recommendation="Ensure news data is fetched from the data source"
            ))
            return self._create_report(symbol, data_type, issues, 0)
        
        for i, article in enumerate(news_data):
            item_issues = self._validate_news_article(article, i)
            issues.extend(item_issues)
        
        # Check for duplicate articles
        title_counts = {}
        for i, article in enumerate(news_data):
            if 'title' in article and article['title']:
                title = str(article['title']).strip().lower()
                if title in title_counts:
                    title_counts[title].append(i)
                else:
                    title_counts[title] = [i]
        
        # Flag duplicate titles
        for title, indices in title_counts.items():
            if len(indices) > 1:
                issues.append(ValidationIssue(
                    check_name="duplicate_title_validation",
                    severity=ValidationSeverity.WARNING,
                    message=f"Duplicate news title found at indices {indices}",
                    value=title,
                    recommendation="Remove duplicate news articles"
                ))
        
        # Check for unusual number of articles
        if total_articles > 100:
            issues.append(ValidationIssue(
                check_name="article_count_high_validation",
                severity=ValidationSeverity.WARNING,
                message=f"Unusually high number of articles: {total_articles}",
                value=total_articles,
                recommendation="Verify this is the expected number of articles"
            ))
        elif total_articles < 5:
            issues.append(ValidationIssue(
                check_name="article_count_low_validation",
                severity=ValidationSeverity.INFO,
                message=f"Low number of articles: {total_articles}",
                value=total_articles,
                recommendation="Consider fetching more articles for better coverage"
            ))
        
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
    
    def _validate_news_article(self, article: Dict[str, Any], index: int) -> List[ValidationIssue]:
        """Validate a single news article"""
        issues = []
        
        # Check required fields
        for field in self.required_fields:
            if field not in article or article[field] is None:
                issues.append(ValidationIssue(
                    check_name="required_field_validation",
                    field=f"news[{index}].{field}",
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Missing required field '{field}' in news article",
                    value=article.get(field),
                    recommendation=f"Ensure '{field}' is included in news data"
                ))
        
        # Validate title
        if 'title' in article and article['title'] is not None:
            title_value = str(article['title']).strip()
            if not title_value:
                issues.append(ValidationIssue(
                    check_name="title_empty_validation",
                    severity=ValidationSeverity.CRITICAL,
                    message="Title field is empty",
                    value=article['title'],
                    recommendation="Provide meaningful article title"
                ))
            elif len(title_value) < 10:
                issues.append(ValidationIssue(
                    check_name="title_short_validation",
                    severity=ValidationSeverity.WARNING,
                    message=f"Title seems too short: {title_value}",
                    value=title_value,
                    recommendation="Verify the title is complete"
                ))
            elif len(title_value) > 500:
                issues.append(ValidationIssue(
                    check_name="title_long_validation",
                    severity=ValidationSeverity.WARNING,
                    message=f"Title seems too long: {len(title_value)} characters",
                    value=title_value[:100] + "...",
                    recommendation="Consider truncating very long titles"
                ))
            else:
                # Check for suspicious patterns
                title_lower = title_value.lower()
                for pattern in self.suspicious_patterns:
                    if pattern in title_lower:
                        issues.append(ValidationIssue(
                            check_name="title_suspicious_pattern_validation",
                            severity=ValidationSeverity.WARNING,
                            message=f"Suspicious pattern in title: '{pattern}'",
                            value=title_value,
                            recommendation="Verify this is a legitimate news article"
                        ))
                
                # Check for excessive punctuation
                exclamation_count = title_value.count('!')
                question_count = title_value.count('?')
                if exclamation_count > 2 or question_count > 2:
                    issues.append(ValidationIssue(
                        check_name="title_excessive_punctuation_validation",
                        field=f"news[{index}].title",
                        severity=ValidationSeverity.WARNING,
                        message=f"Excessive punctuation: {exclamation_count} !, {question_count} ?",
                        value=title_value,
                        recommendation="Verify this is a professional news source"
                    ))
        
        # Validate publisher
        if 'publisher' in article and article['publisher'] is not None:
            publisher_value = str(article['publisher']).strip()
            if not publisher_value:
                issues.append(ValidationIssue(
                    check_name="publisher_empty_validation",
                    field=f"news[{index}].publisher",
                    severity=ValidationSeverity.CRITICAL,
                    message="Publisher field is empty",
                    value=article['publisher'],
                    recommendation="Provide news source/publisher name"
                ))
            elif len(publisher_value) > 100:
                issues.append(ValidationIssue(
                    check_name="publisher_length_validation",
                    severity=ValidationSeverity.WARNING,
                    message=f"Publisher name seems too long: {publisher_value}",
                    value=publisher_value,
                    recommendation="Verify publisher name is correct"
                ))
            else:
                # Check if publisher is known
                if publisher_value not in self.known_publishers:
                    issues.append(ValidationIssue(
                        check_name="publisher_known_validation",
                        severity=ValidationSeverity.INFO,
                        message=f"Unknown publisher: {publisher_value}",
                        value=publisher_value,
                        recommendation="Verify this is a legitimate news source"
                    ))
        
        # Validate link
        if 'link' in article and article['link'] is not None:
            link_value = str(article['link']).strip()
            if link_value:
                # Basic URL validation
                if not (link_value.startswith('http://') or link_value.startswith('https://')):
                    issues.append(ValidationIssue(
                        check_name="link_format_validation",
                        field=f"news[{index}].link",
                        severity=ValidationSeverity.WARNING,
                        message="Link should start with http:// or https://",
                        value=link_value,
                        recommendation="Provide valid URL"
                    ))
                elif len(link_value) > 1000:
                    issues.append(ValidationIssue(
                        check_name="link_length_validation",
                        severity=ValidationSeverity.WARNING,
                        message=f"URL seems too long: {len(link_value)} characters",
                        value=link_value[:100] + "...",
                        recommendation="Verify URL is correct"
                    ))
        
        # Validate published_date
        if 'published_date' in article and article['published_date'] is not None:
            date_value = article['published_date']
            validated_date = self._validate_date_field(date_value, f"news[{index}].published_date")
            if validated_date is None:
                issues.append(ValidationIssue(
                    check_name="published_date_validation",
                    severity=ValidationSeverity.WARNING,
                    message=f"Invalid published_date: {date_value}",
                    value=date_value,
                    recommendation="Provide valid date in ISO format or datetime object"
                ))
            else:
                # Check if date is reasonable
                today = date.today()
                if validated_date > today + timedelta(days=1):
                    issues.append(ValidationIssue(
                        check_name="published_date_future_validation", field=f"news[{index}].published_date",
                        severity=ValidationSeverity.WARNING,
                        message=f"Published date {validated_date} is in the future",
                        value=validated_date,
                        recommendation="Verify the publication date is correct"
                    ))
                elif validated_date < today - timedelta(days=365):
                    issues.append(ValidationIssue(
                        check_name="published_date_future_validation", field=f"news[{index}].published_date",
                        severity=ValidationSeverity.INFO,
                        message=f"Published date {validated_date} is over a year old",
                        value=validated_date,
                        recommendation="Consider if this old news is still relevant"
                    ))
        
        # Validate related_symbols
        if 'related_symbols' in article and article['related_symbols'] is not None:
            related_symbols = article['related_symbols']
            if isinstance(related_symbols, list):
                if len(related_symbols) > 20:
                    issues.append(ValidationIssue(
                        check_name="related_symbols_count_validation", field=f"news[{index}].related_symbols",
                        severity=ValidationSeverity.WARNING,
                        message=f"Too many related symbols: {len(related_symbols)}",
                        value=related_symbols[:10],
                        recommendation="Verify all symbols are truly relevant"
                    ))
                
                # Validate each symbol
                for i, symbol in enumerate(related_symbols):
                    symbol_str = str(symbol).strip().upper()
                    if not symbol_str:
                        issues.append(ValidationIssue(
                            field=f"news[{index}].related_symbols[{i}]",
                            severity=ValidationSeverity.WARNING,
                            message="Empty symbol in related_symbols",
                            value=symbol,
                            recommendation="Remove empty symbols"
                        ))
                    elif len(symbol_str) > 10:
                        issues.append(ValidationIssue(
                            field=f"news[{index}].related_symbols[{i}]",
                            severity=ValidationSeverity.WARNING,
                            message=f"Symbol seems too long: {symbol_str}",
                            value=symbol_str,
                            recommendation="Verify symbol format"
                        ))
            elif isinstance(related_symbols, str):
                # Single symbol case
                symbol_str = str(related_symbols).strip().upper()
                if not symbol_str:
                    issues.append(ValidationIssue(
                        check_name="related_symbols_count_validation", field=f"news[{index}].related_symbols",
                        severity=ValidationSeverity.WARNING,
                        message="Empty related_symbols string",
                        value=related_symbols,
                        recommendation="Provide valid symbol or empty list"
                    ))
            else:
                issues.append(ValidationIssue(
                    check_name="related_symbols_count_validation", field=f"news[{index}].related_symbols",
                    severity=ValidationSeverity.WARNING,
                    message="related_symbols should be a list or string",
                    value=type(related_symbols),
                    recommendation="Use list format for multiple symbols"
                ))
        
        # Check for missing important fields
        for field in self.important_fields:
            if field not in article or article[field] is None:
                issues.append(ValidationIssue(
                    field=f"news[{index}].{field}",
                    severity=ValidationSeverity.INFO,
                    message=f"Missing important field '{field}' in news article",
                    value=article.get(field),
                    recommendation=f"Include '{field}' for more complete news data"
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
    
    def _create_report(self, symbol: str, data_type: str, issues: List[ValidationIssue], total_articles: int) -> ValidationReport:
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
        info_count = len([i for i in report.validation_result.issues if i.severity == ValidationSeverity.INFO])
        
        # Count specific issue types
        missing_required = [i for i in report.validation_result.issues if "Missing required field" in i.message]
        missing_important = [i for i in report.validation_result.issues if "Missing important field" in i.message]
        title_issues = [i for i in report.validation_result.issues if "title" in i.field]
        publisher_issues = [i for i in report.validation_result.issues if "publisher" in i.field]
        date_issues = [i for i in report.validation_result.issues if "published_date" in i.field]
        suspicious_content = [i for i in report.validation_result.issues if "suspicious" in i.message.lower()]
        
        return {
            "validation_status": report.overall_status,
            "critical_issues": critical_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "total_issues": len(report.validation_result.issues),
            "validation_score": report.validation_result.score,
            "missing_required_fields": len(missing_required),
            "missing_important_fields": len(missing_important),
            "title_issues": len(title_issues),
            "publisher_issues": len(publisher_issues),
            "date_issues": len(date_issues),
            "suspicious_content_count": len(suspicious_content),
            "missing_fields": [i.field for i in missing_required + missing_important],
            "fields_with_issues": list(set([i.field for i in report.validation_result.issues if i.field != "news_data"]))
        }
