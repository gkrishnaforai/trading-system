#!/usr/bin/env python3
"""
Fix remaining stock_symbol references across all files
This script will systematically replace old column names with new ones
"""

import os
import re
from pathlib import Path

def fix_stock_symbol_references():
    """Fix all remaining stock_symbol references in the codebase"""
    
    base_dir = Path("/Users/krishnag/tools/trading-system/python-worker")
    
    # Files to fix
    files_to_fix = [
        "app/data_management/refresh_manager.py",
        "app/data_validation/signal_readiness.py", 
        "app/repositories/fundamentals_repository.py",
        "app/repositories/indicators_repository.py",
        "app/repositories/market_data_daily_repository.py",
        "app/repositories/market_data_intraday_repository.py"
    ]
    
    # Patterns to replace
    replacements = [
        # SQL WHERE clauses
        (r'WHERE\s+stock_symbol\s*=', 'WHERE symbol ='),
        (r'WHERE\s+stock_symbol\s*IS\s+NOT\s+NULL', 'WHERE symbol IS NOT NULL'),
        (r'WHERE\s+stock_symbol\s*!=', 'WHERE symbol !='),
        (r'AND\s+stock_symbol\s*=', 'AND symbol ='),
        
        # SELECT DISTINCT
        (r'SELECT\s+DISTINCT\s+stock_symbol', 'SELECT DISTINCT symbol'),
        
        # ON CONFLICT clauses
        (r'ON\s+CONFLICT\s*\(\s*stock_symbol', 'ON CONFLICT (symbol'),
        (r'ON\s+CONFLICT\s*\(\s*stock_symbol,\s*as_of_date', 'ON CONFLICT (symbol, as_of_date'),
        (r'ON\s+CONFLICT\s*\(\s*stock_symbol,\s*trade_date', 'ON CONFLICT (symbol, date)'),
        (r'ON\s+CONFLICT\s*\(\s*stock_symbol,\s*ts', 'ON CONFLICT (symbol, ts)'),
        
        # INSERT INTO columns - use simpler patterns
        (r'INSERT\s+INTO\s+(\w+)\s*\(\s*stock_symbol', r'INSERT INTO \1 (symbol'),
        
        # Dictionary keys in Python code
        (r'"stock_symbol"\s*:', '"symbol":'),
        (r"'stock_symbol'\s*:", "'symbol':"),
        (r'get\("stock_symbol"\)', 'get("symbol")'),
        (r'get\([\'"]stock_symbol[\'"]\)', 'get("symbol")'),
        
        # Result extraction
        (r'row\["stock_symbol"\]', 'row["symbol"]'),
        (r'row\[\'stock_symbol\'\]', 'row["symbol"]'),
    ]
    
    for file_path in files_to_fix:
        full_path = base_dir / file_path
        if not full_path.exists():
            print(f"❌ File not found: {file_path}")
            continue
            
        print(f"🔧 Fixing {file_path}...")
        
        try:
            with open(full_path, 'r') as f:
                content = f.read()
            
            original_content = content
            
            # Apply replacements
            for pattern, replacement in replacements:
                content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
            
            # Only write if changed
            if content != original_content:
                with open(full_path, 'w') as f:
                    f.write(content)
                print(f"✅ Updated {file_path}")
            else:
                print(f"ℹ️  No changes needed for {file_path}")
                
        except Exception as e:
            print(f"❌ Error fixing {file_path}: {e}")

if __name__ == "__main__":
    print("🔧 Fixing remaining stock_symbol references...")
    fix_stock_symbol_references()
    print("✅ Done! Please rebuild and restart the container.")
