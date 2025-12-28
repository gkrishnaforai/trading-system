#!/usr/bin/env python3
"""
Load sample fundamental data for testing stock insights
"""

import sys
import os
from datetime import datetime

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_database
from app.repositories.fundamentals_repository import FundamentalsRepository

def load_sample_fundamentals():
    """Load sample fundamental data for common symbols"""
    print("📊 Loading sample fundamental data...")
    
    init_database()
    
    # Sample fundamental data for popular stocks
    sample_data = {
        "AAPL": {
            "pe_ratio": 29.5,
            "pb_ratio": 45.2,
            "price_to_sales": 7.8,
            "ev_ebitda": 22.1,
            "forward_pe": 25.3,
            "debt_to_equity": 1.73,
            "return_on_equity": 0.36,
            "return_on_assets": 0.21,
            "profit_margin": 0.23,
            "operating_margin": 0.30,
            "current_ratio": 1.07,
            "enterprise_value": 3200000000000,
            "operating_income": 108900000000,
            "sector": "Technology",
            "industry": "Consumer Electronics"
        },
        "MSFT": {
            "pe_ratio": 35.2,
            "pb_ratio": 13.8,
            "price_to_sales": 12.1,
            "ev_ebitda": 24.5,
            "forward_pe": 28.7,
            "debt_to_equity": 0.47,
            "return_on_equity": 0.39,
            "return_on_assets": 0.15,
            "profit_margin": 0.36,
            "operating_margin": 0.41,
            "current_ratio": 1.9,
            "enterprise_value": 2800000000000,
            "operating_income": 83300000000,
            "sector": "Technology",
            "industry": "Software"
        },
        "GOOGL": {
            "pe_ratio": 25.8,
            "pb_ratio": 7.1,
            "price_to_sales": 6.2,
            "ev_ebitda": 18.9,
            "forward_pe": 22.1,
            "debt_to_equity": 0.11,
            "return_on_equity": 0.18,
            "return_on_assets": 0.13,
            "profit_margin": 0.25,
            "operating_margin": 0.28,
            "current_ratio": 2.8,
            "enterprise_value": 1900000000000,
            "operating_income": 74800000000,
            "sector": "Technology",
            "industry": "Internet Services"
        }
    }
    
    repo = FundamentalsRepository()
    success_count = 0
    
    for symbol, fundamentals in sample_data.items():
        try:
            success = repo.upsert_fundamentals(symbol, fundamentals)
            if success:
                print(f"✅ Loaded fundamentals for {symbol}")
                success_count += 1
            else:
                print(f"❌ Failed to load fundamentals for {symbol}")
        except Exception as e:
            print(f"❌ Error loading {symbol}: {e}")
    
    print(f"\n🎉 Successfully loaded fundamental data for {success_count}/{len(sample_data)} symbols")
    
    # Verify data was loaded
    print("\n🔍 Verifying loaded data:")
    for symbol in sample_data.keys():
        data = repo.fetch_by_symbol(symbol)
        if data:
            print(f"✅ {symbol}: {len(data)} fields loaded")
            print(f"   Sample: P/E={data.get('pe_ratio', 'N/A')}, Debt/Equity={data.get('debt_to_equity', 'N/A')}")
        else:
            print(f"❌ {symbol}: No data found")

if __name__ == "__main__":
    load_sample_fundamentals()
