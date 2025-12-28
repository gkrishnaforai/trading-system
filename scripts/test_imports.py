#!/usr/bin/env python3
"""
Quick import test to verify all modules can be imported correctly
"""
import sys
import os

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python-worker'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'streamlit-app'))

def test_imports():
    """Test all critical imports"""
    errors = []
    
    # Test typing imports
    try:
        from typing import Dict, Any
        print("✅ typing imports: Dict, Any")
    except ImportError as e:
        errors.append(f"❌ typing imports: {e}")
    
    # Test data validation imports
    try:
        from app.data_validation.checks import IndicatorDataCheck
        print("✅ IndicatorDataCheck import")
    except Exception as e:
        errors.append(f"❌ IndicatorDataCheck: {e}")
    
    try:
        from app.data_validation.signal_readiness import SignalReadinessValidator
        print("✅ SignalReadinessValidator import")
    except Exception as e:
        errors.append(f"❌ SignalReadinessValidator: {e}")
    
    try:
        from app.data_validation.validator import DataValidator
        print("✅ DataValidator import")
    except Exception as e:
        errors.append(f"❌ DataValidator: {e}")
    
    # Test indicator imports
    try:
        from app.indicators.moving_averages import calculate_ema
        print("✅ calculate_ema import")
    except Exception as e:
        errors.append(f"❌ calculate_ema: {e}")
    
    # Test shared_functions (without streamlit)
    try:
        # Check if file can be parsed (syntax check)
        import ast
        with open('streamlit-app/shared_functions.py', 'r') as f:
            code = f.read()
        ast.parse(code)
        print("✅ shared_functions.py syntax valid")
        
        # Check if Dict, Any are imported
        if 'from typing import Dict, Any' in code or 'from typing import' in code and 'Dict' in code and 'Any' in code:
            print("✅ shared_functions.py has Dict, Any imports")
        else:
            errors.append("❌ shared_functions.py missing Dict, Any imports")
    except Exception as e:
        errors.append(f"❌ shared_functions.py: {e}")
    
    # Test testbed (without streamlit)
    try:
        import ast
        with open('streamlit-app/testbed.py', 'r') as f:
            code = f.read()
        ast.parse(code)
        print("✅ testbed.py syntax valid")
        
        # Check if display_validation_report is imported
        if 'display_validation_report' in code:
            print("✅ testbed.py imports display_validation_report")
        else:
            errors.append("❌ testbed.py missing display_validation_report import")
    except Exception as e:
        errors.append(f"❌ testbed.py: {e}")
    
    if errors:
        print("\n❌ Errors found:")
        for error in errors:
            print(f"  {error}")
        return False
    else:
        print("\n✅ All imports and syntax checks passed!")
        return True

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)

