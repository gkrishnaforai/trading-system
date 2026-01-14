#!/usr/bin/env python3
"""
Manual Bulk Stock Loading Script
Run this script to populate the stocks table with popular stocks
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.bulk_stock_loader import BulkStockLoader

async def main():
    """Main function to run bulk stock loading"""
    print("🚀 Starting Manual Bulk Stock Loading...")
    print("=" * 60)
    
    loader = BulkStockLoader()
    
    # Show current database state
    print("📊 Current Database Summary:")
    summary = loader.get_database_summary()
    if 'error' not in summary:
        print(f"  Total stocks: {summary['total_stocks']}")
        print(f"  Sectors: {len(summary['by_sector'])}")
        print(f"  Exchanges: {len(summary['by_exchange'])}")
        
        if summary['by_sector']:
            print("\n🏢 Current Sectors:")
            for sector, count in list(summary['by_sector'].items())[:5]:
                print(f"    {sector}: {count}")
    else:
        print(f"  Error: {summary['error']}")
    
    print("\n" + "=" * 60)
    
    # Confirm before loading
    response = input("Do you want to load popular stocks? (y/N): ").strip().lower()
    if response != 'y':
        print("❌ Bulk loading cancelled")
        return
    
    print("\n🚀 Starting bulk load...")
    
    # Load stocks
    results = await loader.load_all_popular_stocks()
    
    print("\n" + "=" * 60)
    print("📈 Loading Results:")
    print(f"  Total processed: {results['total']}")
    print(f"  ✅ Successfully loaded: {results['loaded']}")
    print(f"  ❌ Failed: {results['failed']}")
    print(f"  ⏭️ Skipped (already exist): {results['skipped']}")
    
    if loader.failed_symbols:
        print(f"\n❌ Failed symbols: {', '.join(loader.failed_symbols)}")
    
    # Show final database state
    print("\n📊 Final Database Summary:")
    final_summary = loader.get_database_summary()
    if 'error' not in final_summary:
        print(f"  Total stocks: {final_summary['total_stocks']}")
        
        if final_summary['by_sector']:
            print("\n🏢 Top Sectors:")
            for sector, count in list(final_summary['by_sector'].items())[:5]:
                print(f"    {sector}: {count}")
        
        if final_summary['by_exchange']:
            print("\n📈 Top Exchanges:")
            for exchange, count in list(final_summary['by_exchange'].items())[:5]:
                print(f"    {exchange}: {count}")
        
        print("\n🕐 Recent Additions:")
        for recent in final_summary['recent_additions'][:5]:
            print(f"    {recent['symbol']} - {recent['company']}")
    else:
        print(f"  Error: {final_summary['error']}")
    
    print("\n" + "=" * 60)
    print("✅ Bulk stock loading completed!")

if __name__ == "__main__":
    asyncio.run(main())
