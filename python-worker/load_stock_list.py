#!/usr/bin/env python3
"""
Load complete stock list from FMP API into database
This will populate the stocks table with all available symbols
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.providers.financial_modeling_prep.client import EnhancedFMPClient, FinancialModelingPrepConfig
from app.database import init_database
from app.observability.logging import get_logger
import requests

logger = get_logger("load_stock_list")

def load_stock_list():
    """Load complete stock list from FMP API"""
    print("📥 Loading Complete Stock List from FMP API")
    print("=" * 60)
    
    try:
        # Initialize database
        print("1️⃣ Initializing database connection...")
        init_database()
        print("   ✅ Database initialized")
        
        # Create FMP client
        print("\n2️⃣ Creating FMP client...")
        config = FinancialModelingPrepConfig(
            api_key="4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ",
            base_url="https://financialmodelingprep.com/stable"
        )
        client = EnhancedFMPClient(config)
        print("   ✅ FMP client created")
        
        # Fetch stock list
        print("\n3️⃣ Fetching stock list from FMP...")
        stock_list = client.get_stock_list()
        
        if not stock_list:
            print("   ❌ No stock list data received")
            return False
        
        print(f"   ✅ Fetched {len(stock_list)} stocks")
        
        # Show sample of data
        print("\n📊 Sample stocks:")
        for i, stock in enumerate(stock_list[:5]):
            print(f"   {i+1}. {stock.get('symbol', 'N/A')}: {stock.get('name', 'N/A')}")
        
        if len(stock_list) > 5:
            print(f"   ... and {len(stock_list) - 5} more")
        
        # Store in database
        print(f"\n4️⃣ Storing {len(stock_list)} stocks in database...")
        
        # Create stocks table if it doesn't exist
        from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Boolean, Index
        from sqlalchemy.orm import declarative_base
        from datetime import datetime
        from app.database import db
        
        Base = declarative_base()
        
        class StockList(Base):
            """Complete stock list from FMP"""
            __tablename__ = "fmp_stock_list"
            
            symbol = Column(String(10), primary_key=True)
            name = Column(String(255), nullable=False)
            price = Column(Float)
            exchange = Column(String(50))
            exchangeShortName = Column(String(50))
            type = Column(String(50))
            
            # Metadata
            created_at = Column(DateTime, default=datetime.utcnow)
            data_source = Column(String(50), default="fmp")
            
            __table_args__ = (
                Index('idx_stock_list_symbol', 'symbol'),
                Index('idx_stock_list_exchange', 'exchange'),
                Index('idx_stock_list_type', 'type'),
            )
        
        # Create table
        Base.metadata.create_all(db.engine)
        print("   ✅ Stock list table created/verified")
        
        # Store stocks in batches
        batch_size = 1000
        stored_count = 0
        
        with db.session_factory() as session:
            for i in range(0, len(stock_list), batch_size):
                batch = stock_list[i:i + batch_size]
                
                for stock in batch:
                    symbol = stock.get('symbol')
                    if not symbol:
                        continue
                    
                    # Check if stock exists
                    existing = session.query(StockList).filter_by(symbol=symbol).first()
                    
                    if existing:
                        # Update existing
                        existing.name = stock.get('name', existing.name)
                        existing.price = stock.get('price')
                        existing.exchange = stock.get('exchange')
                        existing.exchangeShortName = stock.get('exchangeShortName')
                        existing.type = stock.get('type')
                    else:
                        # Create new
                        stock_record = StockList(
                            symbol=symbol,
                            name=stock.get('name', ''),
                            price=stock.get('price'),
                            exchange=stock.get('exchange'),
                            exchangeShortName=stock.get('exchangeShortName'),
                            type=stock.get('type')
                        )
                        session.add(stock_record)
                        stored_count += 1
                
                # Commit batch
                session.commit()
                print(f"   📊 Processed {min(i + batch_size, len(stock_list))}/{len(stock_list)} stocks")
        
        print(f"\n🎉 STOCK LIST LOAD COMPLETE")
        print(f"   📊 Total processed: {len(stock_list)}")
        print(f"   ✅ New stocks added: {stored_count}")
        print(f"   🗄️  Stored in: fmp_stock_list table")
        
        # Show statistics
        print(f"\n📈 Database Statistics:")
        with db.session_factory() as session:
            total_stocks = session.query(StockList).count()
            exchanges = session.query(StockList.exchange).distinct().count()
            types = session.query(StockList.type).distinct().count()
            
            print(f"   📊 Total stocks in DB: {total_stocks}")
            print(f"   🏢 Exchanges: {exchanges}")
            print(f"   📋 Types: {types}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error loading stock list: {e}")
        logger.error(f"Stock list load failed: {e}")
        return False

def main():
    """Main function"""
    success = load_stock_list()
    
    if success:
        print("\n✅ Stock list loaded successfully!")
        print("🚀 Ready for stock grades analysis with full symbol universe!")
    else:
        print("\n❌ Stock list load failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
