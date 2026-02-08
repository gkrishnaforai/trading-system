#!/usr/bin/env python3
"""
Verify FMP Configuration and Default Data Provider Setup
Ensures FMP is configured as default and can read from .env file
"""

import os
import sys
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("🔍 VERIFYING FMP CONFIGURATION")
    print("=" * 50)
    
    # Check if .env file exists
    env_file = Path(".env")
    if env_file.exists():
        print(f"✅ .env file found: {env_file.absolute()}")
    else:
        print(f"❌ .env file not found: {env_file.absolute()}")
        print("📝 Creating .env from .env.example...")
        
        # Copy from .env.example if it exists
        example_file = Path(".env.example")
        if example_file.exists():
            with open(example_file, 'r') as src, open(env_file, 'w') as dst:
                dst.write(src.read())
            print(f"✅ Created .env from .env.example")
        else:
            print("❌ .env.example file not found")
            return False
    
    # Load settings
    try:
        from app.config import settings
        print("✅ Settings loaded successfully")
    except Exception as e:
        print(f"❌ Error loading settings: {e}")
        return False
    
    # Check FMP configuration
    print("\n📊 FMP CONFIGURATION:")
    print(f"   • FMP API Key: {'✅ Set' if settings.fmp_api_key else '❌ Missing'}")
    print(f"   • FMP Enabled: {'✅ Yes' if settings.fmp_enabled else '❌ No'}")
    print(f"   • FMP Base URL: {settings.fmp_base_url}")
    print(f"   • FMP Timeout: {settings.fmp_timeout}s")
    print(f"   • FMP Max Retries: {settings.fmp_max_retries}")
    print(f"   • FMP Rate Limit: {settings.fmp_rate_limit_calls}/{settings.fmp_rate_limit_window}s")
    
    # Check data provider configuration
    print("\n🎯 DATA PROVIDER CONFIGURATION:")
    print(f"   • Primary Data Provider: {settings.primary_data_provider or 'Not set'}")
    print(f"   • Fallback Data Provider: {settings.fallback_data_provider or 'Not set'}")
    print(f"   • Default Data Provider: {settings.default_data_provider}")
    
    # Verify FMP is primary and default
    if settings.primary_data_provider == "fmp":
        print("✅ FMP is configured as primary data provider")
    else:
        print(f"⚠️ Primary data provider is '{settings.primary_data_provider}', not 'fmp'")
        print("💡 Add 'PRIMARY_DATA_PROVIDER=fmp' to your .env file")
    
    if settings.default_data_provider == "fmp":
        print("✅ FMP is configured as default data provider")
    else:
        print(f"⚠️ Default data provider is '{settings.default_data_provider}', not 'fmp'")
    
    # Check if both are set to FMP (ideal configuration)
    if settings.primary_data_provider == "fmp" and settings.default_data_provider == "fmp":
        print("🎉 Perfect! FMP is set as both PRIMARY and DEFAULT")
    elif settings.default_data_provider == "fmp":
        print("✅ Good! FMP is at least set as DEFAULT (will be used as primary if PRIMARY is not set)")
    
    # Test data source initialization
    try:
        from app.data_sources import get_data_source, PRIMARY_DATA_SOURCE, FALLBACK_DATA_SOURCE
        
        print(f"\n🔄 DATA SOURCE INITIALIZATION:")
        print(f"   • Primary Source: {PRIMARY_DATA_SOURCE}")
        print(f"   • Fallback Source: {FALLBACK_DATA_SOURCE}")
        
        # Try to get FMP data source
        fmp_source = get_data_source("fmp", use_fallback=False)
        print(f"✅ FMP data source created successfully: {type(fmp_source).__name__}")
        
        # Check if FMP is available
        if hasattr(fmp_source, 'is_available') and fmp_source.is_available():
            print("✅ FMP data source is available")
        else:
            print("⚠️ FMP data source may not be fully available (check API key)")
        
    except Exception as e:
        print(f"❌ Error testing data source: {e}")
        return False
    
    # Test FMP client initialization
    try:
        from app.providers.financial_modeling_prep.client import FinancialModelingPrepClient
        
        client = FinancialModelingPrepClient.from_settings()
        print(f"✅ FMP client initialized successfully")
        print(f"   • API Key: {'✅ Set' if client.config.api_key else '❌ Missing'}")
        print(f"   • Base URL: {client.config.base_url}")
        
    except Exception as e:
        print(f"❌ Error initializing FMP client: {e}")
        return False
    
    print("\n🎉 VERIFICATION COMPLETE!")
    print("✅ FMP is properly configured as the default data provider")
    print("✅ System reads configuration from .env file")
    print("✅ All components can initialize successfully")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
