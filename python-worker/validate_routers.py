#!/usr/bin/env python3
"""
Router Configuration Validator
Automatically checks for common router configuration mistakes
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Any

def find_router_files() -> List[Path]:
    """Find all router files in the API directory"""
    api_dir = Path(__file__).parent / "app" / "api"
    router_files = []
    
    for file_path in api_dir.glob("*.py"):
        if file_path.name != "__init__.py" and file_path.name != "api_server.py":
            router_files.append(file_path)
    
    return router_files

def check_router_prefixes(router_files: List[Path]) -> Dict[str, Any]:
    """Check for prefix issues in router files"""
    issues = []
    
    for router_file in router_files:
        with open(router_file, 'r') as f:
            content = f.read()
        
        # Remove comments to avoid false positives
        lines = content.split('\n')
        code_lines = []
        for line in lines:
            # Remove inline comments
            if '#' in line:
                line = line[:line.index('#')]
            code_lines.append(line)
        code_content = '\n'.join(code_lines)
        
        # Look for APIRouter with prefix in actual code (not comments)
        prefix_pattern = r'APIRouter\s*\(\s*[^)]*prefix\s*='
        if re.search(prefix_pattern, code_content):
            issues.append({
                'file': str(router_file),
                'issue': 'PREFIX_IN_ROUTER_FILE',
                'message': f'Router file contains prefix= in APIRouter definition',
                'severity': 'ERROR'
            })
        
        # Check for router variable
        router_pattern = r'router\s*=\s*APIRouter'
        if not re.search(router_pattern, content):
            issues.append({
                'file': str(router_file),
                'issue': 'NO_ROUTER_VARIABLE',
                'message': f'No router variable found',
                'severity': 'WARNING'
            })
    
    return issues

def check_api_server_imports() -> Dict[str, Any]:
    """Check api_server.py for correct router imports and prefixes"""
    api_server_file = Path(__file__).parent / "app" / "api_server.py"
    issues = []
    
    if not api_server_file.exists():
        issues.append({
            'file': 'api_server.py',
            'issue': 'FILE_NOT_FOUND',
            'message': 'api_server.py not found',
            'severity': 'ERROR'
        })
        return issues
    
    with open(api_server_file, 'r') as f:
        content = f.read()
    
    # Remove comments to avoid false positives
    lines = content.split('\n')
    code_lines = []
    for line in lines:
        # Remove inline comments
        if '#' in line:
            line = line[:line.index('#')]
        code_lines.append(line)
    code_content = '\n'.join(code_lines)
    
    # Check for router imports - more flexible pattern
    import_pattern = r'from\s+app\.api\.[\w_]+\s+import\s+router\s+as\s+\w+_router'
    imports = re.findall(import_pattern, content)
    
    # Check for include_router statements - more precise pattern (ignore comments)
    include_pattern = r'app\.include_router\(\w+_router\s*,'
    includes = re.findall(include_pattern, code_content)
    
    if len(imports) != len(includes):
        issues.append({
            'file': 'api_server.py',
            'issue': 'IMPORT_INCLUDE_MISMATCH',
            'message': f'Found {len(imports)} imports but {len(includes)} include_router statements',
            'severity': 'ERROR'
        })
    
    return issues

def validate_endpoint_urls() -> Dict[str, Any]:
    """Check for potential double prefix issues"""
    api_server_file = Path(__file__).parent / "app" / "api_server.py"
    issues = []
    
    with open(api_server_file, 'r') as f:
        content = f.read()
    
    # Look for potential double prefixes in include_router
    double_prefix_pattern = r'prefix="/api/v\d+/[^"]*"'
    matches = re.findall(double_prefix_pattern, content)
    
    # This is a heuristic - in reality, we'd need to check the actual router files
    # For now, just warn about the pattern
    for match in matches:
        issues.append({
            'file': 'api_server.py',
            'issue': 'POTENTIAL_DOUBLE_PREFIX',
            'message': f'Potential double prefix: {match}',
            'severity': 'WARNING'
        })
    
    return issues

def generate_report(issues: List[Dict[str, Any]]) -> str:
    """Generate a validation report"""
    report = []
    report.append("# 🚨 Router Configuration Validation Report\n")
    
    error_count = sum(1 for issue in issues if issue['severity'] == 'ERROR')
    warning_count = sum(1 for issue in issues if issue['severity'] == 'WARNING')
    
    report.append(f"## Summary")
    report.append(f"- ❌ Errors: {error_count}")
    report.append(f"- ⚠️ Warnings: {warning_count}")
    report.append(f"- 📊 Total Issues: {len(issues)}")
    report.append("")
    
    if error_count > 0:
        report.append("## 🚨 ERRORS - Must Fix")
        for issue in issues:
            if issue['severity'] == 'ERROR':
                report.append(f"### {issue['issue']}")
                report.append(f"**File**: {issue['file']}")
                report.append(f"**Message**: {issue['message']}")
                report.append("")
    
    if warning_count > 0:
        report.append("## ⚠️ WARNINGS - Should Fix")
        for issue in issues:
            if issue['severity'] == 'WARNING':
                report.append(f"### {issue['issue']}")
                report.append(f"**File**: {issue['file']}")
                report.append(f"**Message**: {issue['message']}")
                report.append("")
    
    if len(issues) == 0:
        report.append("## ✅ All Checks Passed!")
        report.append("Router configuration looks good.")
    
    return "\n".join(report)

def main():
    """Main validation function"""
    print("🔍 Validating Router Configuration...")
    print("=" * 50)
    
    # Find router files
    router_files = find_router_files()
    print(f"📁 Found {len(router_files)} router files")
    
    # Run checks
    all_issues = []
    
    # Check router prefixes
    prefix_issues = check_router_prefixes(router_files)
    all_issues.extend(prefix_issues)
    
    # Check api_server imports
    import_issues = check_api_server_imports()
    all_issues.extend(import_issues)
    
    # Validate endpoints
    endpoint_issues = validate_endpoint_urls()
    all_issues.extend(endpoint_issues)
    
    # Generate report
    report = generate_report(all_issues)
    print(report)
    
    # Save report
    report_file = Path(__file__).parent / "router_validation_report.md"
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"\n📄 Report saved to: {report_file}")
    
    # Exit with error code if there are errors
    error_count = sum(1 for issue in all_issues if issue['severity'] == 'ERROR')
    if error_count > 0:
        print(f"\n❌ Validation failed with {error_count} errors")
        sys.exit(1)
    else:
        print(f"\n✅ Validation passed!")
        sys.exit(0)

if __name__ == "__main__":
    main()
