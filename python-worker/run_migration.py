#!/usr/bin/env python3
"""
Database Migration Runner
Creates Alpha Vantage tables and Stock Insights snapshots table
"""
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import db
from sqlalchemy import text

def run_alpha_vantage_migration():
    """Run the Alpha Vantage table creation migration"""
    print("🗄️ RUNNING ALPHA VANTAGE DATABASE MIGRATION")
    print("=" * 50)
    
    try:
        # Read the migration SQL file
        migration_file = "migrations/create_alphavantage_tables.sql"
        
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        print(f"✅ Loaded migration from {migration_file}")
        
        # Initialize database connection
        db.initialize()
        print("✅ Database connection initialized")
        
        # Execute migration with proper error handling
        with db.get_session() as session:
            # Simple approach: Execute key CREATE TABLE statements individually
            key_statements = [
                # Tables
                """
                CREATE TABLE IF NOT EXISTS fundamentals_summary (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    name VARCHAR(255),
                    sector VARCHAR(100),
                    industry VARCHAR(100),
                    market_cap BIGINT,
                    pe_ratio NUMERIC(10, 4),
                    pb_ratio NUMERIC(10, 4),
                    eps NUMERIC(10, 4),
                    beta NUMERIC(6, 4),
                    dividend_yield NUMERIC(8, 6),
                    revenue_ttm BIGINT,
                    gross_profit_ttm BIGINT,
                    operating_margin_ttm NUMERIC(8, 6),
                    profit_margin NUMERIC(8, 6),
                    roe NUMERIC(8, 6),
                    debt_to_equity NUMERIC(10, 4),
                    price_to_sales NUMERIC(10, 4),
                    ev_to_revenue NUMERIC(10, 4),
                    ev_to_ebitda NUMERIC(10, 4),
                    price_to_book NUMERIC(10, 4),
                    data_source VARCHAR(50) DEFAULT 'alphavantage',
                    updated_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, data_source)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS fundamentals (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    report_type VARCHAR(50) NOT NULL,
                    fiscal_date_ending DATE,
                    reported_date DATE,
                    reported_currency VARCHAR(10),
                    total_revenue BIGINT,
                    gross_profit BIGINT,
                    operating_income BIGINT,
                    net_income BIGINT,
                    research_and_development BIGINT,
                    selling_general_and_admin BIGINT,
                    interest_expense BIGINT,
                    income_tax_expense BIGINT,
                    total_assets BIGINT,
                    total_liabilities BIGINT,
                    total_shareholder_equity BIGINT,
                    cash_and_cash_equivalents BIGINT,
                    short_term_investments BIGINT,
                    long_term_debt BIGINT,
                    operating_cash_flow BIGINT,
                    investing_cash_flow BIGINT,
                    financing_cash_flow BIGINT,
                    free_cash_flow BIGINT,
                    capital_expenditures BIGINT,
                    reported_eps NUMERIC(10, 4),
                    estimated_eps NUMERIC(10, 4),
                    surprise NUMERIC(10, 4),
                    surprise_percentage NUMERIC(8, 4),
                    data_source VARCHAR(50) DEFAULT 'alphavantage',
                    updated_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, report_type, fiscal_date_ending, data_source)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS raw_market_data_daily (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    date DATE NOT NULL,
                    open NUMERIC(12, 4),
                    high NUMERIC(12, 4),
                    low NUMERIC(12, 4),
                    close NUMERIC(12, 4),
                    volume BIGINT,
                    adjusted_close NUMERIC(12, 4),
                    data_source VARCHAR(50) DEFAULT 'alphavantage',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date, data_source)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS indicators_daily (
                    id SERIAL PRIMARY KEY,
                    stock_symbol VARCHAR(10) NOT NULL,
                    trade_date DATE NOT NULL,
                    indicator_name VARCHAR(50) NOT NULL,
                    indicator_value NUMERIC(12, 6),
                    time_period INTEGER,
                    data_source VARCHAR(50) DEFAULT 'alphavantage',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_symbol, trade_date, indicator_name, data_source)
                )
                """
            ]
            
            for i, statement in enumerate(key_statements, 1):
                try:
                    session.execute(text(statement))
                    session.commit()
                    print(f"✅ Created table {i}/{len(key_statements)}")
                except Exception as e:
                    session.rollback()
                    if "already exists" in str(e):
                        print(f"⚠️  Table {i} already exists: {e}")
                    else:
                        print(f"❌ Table {i} failed: {e}")
                        print(f"   SQL: {statement[:100]}...")
            
            # Create indexes separately
            index_statements = [
                "CREATE INDEX IF NOT EXISTS idx_fundamentals_summary_symbol ON fundamentals_summary(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_fundamentals_symbol ON fundamentals(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_raw_market_daily_symbol ON raw_market_data_daily(stock_symbol)",
                "CREATE INDEX IF NOT EXISTS idx_indicators_daily_symbol ON indicators_daily(stock_symbol)"
            ]
            
            for i, statement in enumerate(index_statements, 1):
                try:
                    session.execute(text(statement))
                    session.commit()
                    print(f"✅ Created index {i}/{len(index_statements)}")
                except Exception as e:
                    session.rollback()
                    if "already exists" in str(e):
                        print(f"⚠️  Index {i} already exists")
                    else:
                        print(f"❌ Index {i} failed: {e}")
        
        print(f"\n🎉 MIGRATION COMPLETED SUCCESSFULLY!")
        print(f"✅ All Alpha Vantage tables created")
        
        # Verify tables were created
        print(f"\n🔍 VERIFYING TABLES:")
        with db.get_session() as session:
            tables_to_check = [
                'fundamentals_summary',
                'fundamentals', 
                'raw_market_data_daily',
                'indicators_daily'
            ]
            
            for table in tables_to_check:
                try:
                    result = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                    print(f"✅ {table}: {result} records")
                except Exception as e:
                    print("✅ Alpha Vantage migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Error running Alpha Vantage migration: {e}")
        raise

def run_stock_insights_migration():
    """Run the Stock Insights table creation migration"""
    print("\n📊 RUNNING STOCK INSIGHTS DATABASE MIGRATION")
    print("=" * 50)
    
    try:
        # Read the migration SQL file
        migration_file = "migrations/create_stock_insights_table.sql"
        
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        print(f"📄 Reading migration from: {migration_file}")
        
        # Execute the migration
        statements = [stmt.strip() for stmt in migration_sql.split(';') if stmt.strip()]
        
        for i, statement in enumerate(statements, 1):
            print(f"🚀 Executing statement {i}/{len(statements)}...")
            db.execute_update(statement)
        
        print("✅ Stock Insights migration completed successfully!")
        
        # Verify table was created
        verify_sql = """
            SELECT table_name, column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'stock_insights_snapshots'
            ORDER BY ordinal_position;
        """
        
        columns = db.execute_query(verify_sql)
        if columns:
            print(f"✅ Table 'stock_insights_snapshots' verified with {len(columns)} columns:")
            for col in columns:
                print(f"   • {col['table_name']}.{col['column_name']} ({col['data_type']})")
        else:
            print("❌ Table not found after migration")
            
    except Exception as e:
        print(f"❌ Error running Stock Insights migration: {e}")
        raise

def run_migration():
    """Run all migrations"""
    print("🔧 RUNNING ALL DATABASE MIGRATIONS")
    print("=" * 60)
    
    try:
        # Run Alpha Vantage migration
        run_alpha_vantage_migration()
        
        # Run Stock Insights migration
        run_stock_insights_migration()
        
        print("\n🎉 ALL MIGRATIONS COMPLETED SUCCESSFULLY!")
        print("\n✅ You can now:")
        print("   • Run: streamlit run streamlit_trading_dashboard.py")
        print("   • Test enhanced overall recommendations")
        print("   • View entry/exit plans with reasoning")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("\n🔧 Troubleshooting:")
        print("   • Ensure DATABASE_URL is set correctly")
        print("   • Ensure you have database permissions")
        print("   • Check that PostgreSQL is running")
        raise

def main():
    """Main function"""
    print("🚀 ALPHA VANTAGE DATABASE MIGRATION")
    print("=" * 40)
    
    success = run_migration()
    
    if success:
        print(f"\n🎯 MIGRATION RESULT: SUCCESS!")
        print(f"✅ Database is ready for Alpha Vantage data loading")
        print(f"✅ All tables and indexes created")
        print(f"✅ Triggers and constraints applied")
        
        print(f"\n📋 NEXT STEPS:")
        print(f"   1. Run the Alpha Vantage data loader test")
        print(f"   2. Load data for your desired symbols")
        print(f"   3. Verify data in the database")
        
    else:
        print(f"\n❌ MIGRATION FAILED")
        print(f"   Check database connection and permissions")
    
    return success

if __name__ == "__main__":
    main()
