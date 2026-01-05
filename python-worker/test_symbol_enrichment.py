#!/usr/bin/env python3
"""
Test script for symbol enrichment functionality.
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

def test_symbol_enrichment():
    """Test the symbol enrichment setup."""
    try:
        print("🧪 Testing Symbol Enrichment Setup...")
        
        # Test imports
        print("✓ Testing imports...")
        from app.repositories.stocks_repository import StocksRepository, MissingSymbolsRepository
        from app.services.symbol_enrichment_service import SymbolEnrichmentService
        from app.data_validation.earnings_data_validator import EarningsDataValidator
        print("✓ All imports successful")
        
        # Test table creation
        print("✓ Testing table creation...")
        StocksRepository.create_table()
        MissingSymbolsRepository.create_table()
        print("✓ Tables created successfully")
        
        # Test validator integration
        print("✓ Testing validator integration...")
        validator = EarningsDataValidator()
        
        # Test with sample earnings data
        sample_earnings = [{
            'symbol': 'TEST',
            'earnings_date': '2024-01-15',
            'eps_actual': 1.25,
            'eps_estimated': 1.20
        }]
        
        report = validator.validate_earnings_data(sample_earnings)
        print(f"✓ Validation completed with {len(report.issues)} issues")
        
        # Check if missing symbol was queued
        missing_symbols = MissingSymbolsRepository.get_pending_symbols(10)
        print(f"✓ Found {len(missing_symbols)} symbols in queue")
        
        # Test API integration
        print("✓ Testing API integration...")
        from app.api.symbol_enrichment import router
        print("✓ API router created successfully")
        
        print("\n🎉 All tests passed! Symbol enrichment is ready to use.")
        print("\n📋 Next steps:")
        print("1. Start the API server: python start_api_server.py")
        print("2. Initialize tables: POST /symbols/initialize-stocks-table")
        print("3. Check for missing symbols: POST /symbols/check-missing/earnings_calendar")
        print("4. Process missing symbols: POST /symbols/enrich-missing")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_symbol_enrichment()
    sys.exit(0 if success else 1)
