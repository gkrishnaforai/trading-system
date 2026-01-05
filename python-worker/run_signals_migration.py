#!/usr/bin/env python3
"""
Simple migration runner for trading signals table
Quick way to create the trading_signals table
"""

import sys
import os
from pathlib import Path

# Add the python-worker directory to the path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from migrations.create_trading_signals_table import create_trading_signals_table
    
    print("🚀 Creating trading_signals table...")
    success = create_trading_signals_table()
    
    if success:
        print("✅ Migration completed successfully!")
        print("\n📊 Table is ready for signal storage")
        print("🔍 Verify with: SELECT COUNT(*) FROM trading_signals;")
    else:
        print("❌ Migration failed")
        sys.exit(1)
        
except Exception as e:
    print(f"❌ Migration error: {e}")
    sys.exit(1)
