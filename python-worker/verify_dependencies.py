#!/usr/bin/env python3
"""
Verify that all required dependencies from requirements.txt are installed.
This helps catch issues where Docker container wasn't rebuilt after adding new dependencies.
"""
import sys
import importlib

REQUIRED_PACKAGES = {
    'polygon': 'polygon>=1.2.8  # Required for Massive.com data source',
    'fastapi': 'fastapi>=0.104.0',
    'pandas': 'pandas>=2.1.0',
    'yfinance': 'yfinance>=0.2.0',
    'sqlalchemy': 'sqlalchemy>=2.0.0',
    'asyncpg': 'asyncpg>=0.29.0',
}

def check_package(package_name: str) -> tuple[bool, str]:
    """Check if a package is installed and importable"""
    try:
        importlib.import_module(package_name)
        return True, "✅ Installed"
    except ImportError as e:
        return False, f"❌ Not installed: {e}"

def main():
    """Check all required packages"""
    print("🔍 Verifying required dependencies...\n")
    
    all_ok = True
    for package, requirement in REQUIRED_PACKAGES.items():
        is_installed, message = check_package(package)
        status = "✅" if is_installed else "❌"
        print(f"{status} {package:20s} - {message}")
        if not is_installed:
            all_ok = False
            print(f"   Required: {requirement}")
    
    print()
    if all_ok:
        print("✅ All required packages are installed!")
        return 0
    else:
        print("❌ Some required packages are missing!")
        print("\n💡 Solution: Rebuild Docker container to install missing packages:")
        print("   docker-compose build python-worker")
        print("   docker-compose up -d python-worker")
        return 1

if __name__ == "__main__":
    sys.exit(main())

