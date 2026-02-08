#!/usr/bin/env python3
"""
Migrate FMP stock list data to the existing stocks table
Follows DRY principle - uses existing database structure
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import init_database, db
from app.providers.financial_modeling_prep.client import EnhancedFMPClient, FinancialModelingPrepConfig
from app.observability.logging import get_logger
from datetime import datetime
from sqlalchemy import text

logger = get_logger("migrate_fmp_to_stocks")

def migrate_fmp_to_stocks():
    """Migrate FMP stock list to existing stocks table"""
    print("🔄 Migrating FMP Stock List to Stocks Table")
    print("=" * 60)
    
    try:
        # Initialize database
        print("1️⃣ Initializing database connection...")
        init_database()
        print("   ✅ Database initialized")
        
        # Check existing stocks table
        print("\n2️⃣ Checking existing stocks table...")
        existing_count = db.execute_query("SELECT COUNT(*) as count FROM stocks")
        print(f"   📊 Existing stocks: {existing_count[0]['count']}")
        
        # Clear existing stocks table for clean migration
        if existing_count[0]['count'] > 0:
            print("\n🗑️  Clearing existing stocks table and dependencies...")
            with db.session_factory() as session:
                # Clear dependent tables first
                session.execute(text("DELETE FROM portfolio_holdings"))
                session.execute(text("DELETE FROM stocks"))
                session.commit()
            print("   ✅ Existing stocks and dependencies cleared")
        
        # Create FMP client
        print("\n3️⃣ Creating FMP client...")
        config = FinancialModelingPrepConfig(
            api_key="4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ",
            base_url="https://financialmodelingprep.com/stable"
        )
        client = EnhancedFMPClient(config)
        print("   ✅ FMP client created")
        
        # Fetch stock list
        print("\n4️⃣ Fetching stock list from FMP...")
        stock_list = client.get_stock_list()
        
        if not stock_list:
            print("   ❌ No stock list data received")
            return False
        
        print(f"   ✅ Fetched {len(stock_list)} stocks")
        
        # Migrate to stocks table
        print(f"\n5️⃣ Migrating {len(stock_list)} stocks to stocks table...")
        
        batch_size = 1000
        added_count = 0
        updated_count = 0
        
        with db.session_factory() as session:
            for i in range(0, len(stock_list), batch_size):
                batch = stock_list[i:i + batch_size]
                
                for stock in batch:
                    symbol = stock.get('symbol')
                    if not symbol:
                        continue
                    
                    # Check if stock exists
                    existing = session.execute(
                        text("SELECT symbol FROM stocks WHERE symbol = :symbol"),
                        {"symbol": symbol}
                    ).fetchone()
                    
                    if existing:
                        # Update existing stock
                        session.execute(
                            text("""
                            UPDATE stocks SET 
                                company_name = :name,
                                exchange = :exchange,
                                currency = :currency,
                                updated_at = :updated_at
                            WHERE symbol = :symbol
                            """),
                            {
                                "symbol": symbol,
                                "name": stock.get('companyName'),  # Fixed: use 'companyName' field
                                "exchange": stock.get('exchange'),
                                "currency": "USD",  # Default to USD for FMP data
                                "updated_at": datetime.utcnow()
                            }
                        )
                        updated_count += 1
                    else:
                        # Insert new stock
                        session.execute(
                            text("""
                            INSERT INTO stocks (
                                symbol, company_name, exchange, currency, 
                                is_active, created_at, updated_at
                            ) VALUES (
                                :symbol, :name, :exchange, :currency,
                                :is_active, :created_at, :updated_at
                            )
                            """),
                            {
                                "symbol": symbol,
                                "name": stock.get('companyName', symbol),  # Fixed: use 'companyName' field
                                "exchange": stock.get('exchange'),
                                "currency": "USD",  # Default to USD for FMP data
                                "is_active": True,
                                "created_at": datetime.utcnow(),
                                "updated_at": datetime.utcnow()
                            }
                        )
                        added_count += 1
                
                # Commit batch
                session.commit()
                print(f"   📊 Processed {min(i + batch_size, len(stock_list))}/{len(stock_list)} stocks")
        
        print(f"\n🎉 MIGRATION COMPLETE")
        print(f"   ✅ New stocks added: {added_count}")
        print(f"   ✅ Existing stocks updated: {updated_count}")
        print(f"   📊 Total processed: {len(stock_list)}")
        
        # Clean up fmp_stock_list table if it exists
        print(f"\n6️⃣ Cleaning up temporary fmp_stock_list table...")
        try:
            with db.session_factory() as session:
                session.execute(text("DROP TABLE IF EXISTS fmp_stock_list"))
                session.commit()
            print("   ✅ Temporary fmp_stock_list table dropped")
        except Exception as e:
            print(f"   ⚠️  Could not drop fmp_stock_list table: {e}")
        
        # Show final statistics
        print(f"\n📈 Final Database Statistics:")
        with db.session_factory() as session:
            final_count = session.execute(text("SELECT COUNT(*) as count FROM stocks")).fetchone()
            print(f"   📊 Total stocks in database: {final_count[0]}")
            
            # Show sample data
            sample = session.execute(text("""
                SELECT symbol, company_name, exchange, is_active 
                FROM stocks 
                WHERE company_name IS NOT NULL 
                ORDER BY symbol 
                LIMIT 5
            """)).fetchall()
            
            print(f"\n📋 Sample stocks:")
            for row in sample:
                print(f"   • {row[0]}: {row[1]} ({row[2]}) - {'Active' if row[3] else 'Inactive'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        logger.error(f"FMP migration failed: {e}")
        return False

def main():
    """Main function"""
    success = migrate_fmp_to_stocks()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("🚀 Streamlit UI will now show all FMP stock symbols!")
        print("🔄 API endpoint /api/v1/stocks/available is ready!")
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
