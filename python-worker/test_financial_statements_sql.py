#!/usr/bin/env python3
"""
Test SQL Insert for Financial Statements
Tests the exact SQL that's failing in the application
"""

import psycopg2
import json
import os
from datetime import datetime, date
from urllib.parse import urlparse

# Read database configuration from .env file
def get_db_config():
    """Get database config from .env file or environment variables"""
    
    # Try to read from .env file
    env_file = '.env'
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        # Fallback to individual environment variables
        database_url = f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', 'postgres')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'trading_system')}"
    
    print(f"📡 Using database URL: {database_url.replace(database_url.split('@')[1].split(':')[0] if '@' in database_url else 'password', '***')}")
    
    # Parse database URL
    parsed = urlparse(database_url)
    
    return {
        'host': parsed.hostname or 'localhost',
        'port': parsed.port or 5432,
        'database': parsed.path.lstrip('/') or 'trading_system',
        'user': parsed.username or 'postgres',
        'password': parsed.password or 'postgres'
    }

# Database connection parameters from .env
DB_CONFIG = get_db_config()

def fix_table_schema():
    """Fix missing columns in the financial_statements table"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("\n=== Fixing financial_statements table schema ===")
        
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'financial_statements'
            );
        """)
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            print("❌ Table 'financial_statements' does not exist - creating it...")
            cursor.execute("""
                CREATE TABLE financial_statements (
                    stock_symbol VARCHAR(20) NOT NULL,
                    period_type VARCHAR(20) NOT NULL,
                    statement_type VARCHAR(50) NOT NULL,
                    fiscal_period DATE NOT NULL,
                    payload TEXT,
                    data_source VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (stock_symbol, period_type, statement_type, fiscal_period)
                );
            """)
            print("✅ Table created successfully!")
        else:
            print("✅ Table exists - checking for missing columns...")
            
            # Check existing columns
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'financial_statements'
            """)
            existing_columns = {row[0] for row in cursor.fetchall()}
            
            # Required columns
            required_columns = {
                'stock_symbol', 'period_type', 'statement_type', 'fiscal_period',
                'payload', 'data_source', 'created_at', 'updated_at'
            }
            
            missing_columns = required_columns - existing_columns
            
            if missing_columns:
                print(f"🔧 Adding missing columns: {missing_columns}")
                
                # Add missing columns with appropriate types
                column_definitions = {
                    'payload': 'TEXT',
                    'data_source': 'VARCHAR(50)',
                    'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                    'updated_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                }
                
                for column in missing_columns:
                    if column in column_definitions:
                        definition = column_definitions[column]
                        cursor.execute(f"""
                            ALTER TABLE financial_statements 
                            ADD COLUMN IF NOT EXISTS {column} {definition}
                        """)
                        print(f"✅ Added column: {column}")
                
                # Check if primary key exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM pg_constraint 
                        WHERE conrelid = 'financial_statements'::regclass 
                        AND contype = 'p'
                    );
                """)
                has_primary_key = cursor.fetchone()[0]
                
                if not has_primary_key:
                    print("🔧 Adding primary key constraint...")
                    cursor.execute("""
                        ALTER TABLE financial_statements 
                        ADD CONSTRAINT financial_statements_pkey 
                        PRIMARY KEY (stock_symbol, period_type, statement_type, fiscal_period)
                    """)
                    print("✅ Added primary key constraint")
            else:
                print("✅ All required columns exist")
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error fixing schema: {e}")
        return False

def test_table_schema():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("=== Checking financial_statements table schema ===")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'financial_statements'
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        if not columns:
            print("❌ Table 'financial_statements' does not exist!")
            return False
            
        print("✅ Table schema:")
        for col in columns:
            print(f"   - {col[0]}: {col[1]} (nullable: {col[2]}, default: {col[3]})")
        
        # Check constraints
        cursor.execute("""
            SELECT conname, contype, pg_get_constraintdef(oid)
            FROM pg_constraint 
            WHERE conrelid = 'financial_statements'::regclass
        """)
        
        constraints = cursor.fetchall()
        if constraints:
            print("\n✅ Table constraints:")
            for con in constraints:
                print(f"   - {con[0]}: {con[1]} - {con[2]}")
        else:
            print("\n⚠️ No constraints found")
            
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error checking schema: {e}")
        return False

def test_simple_insert():
    """Test a simple insert first"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("\n=== Testing Simple Insert ===")
        
        # Test with minimal data
        simple_sql = """
            INSERT INTO financial_statements 
            (stock_symbol, period_type, statement_type, fiscal_period)
            VALUES (%s, %s, %s, %s)
        """
        
        params = ('TEST', 'annual', 'income_statement', date(2023, 12, 31))
        print(f"SQL: {simple_sql}")
        print(f"Params: {params}")
        
        cursor.execute(simple_sql, params)
        conn.commit()
        print("✅ Simple insert successful!")
        
        # Clean up
        cursor.execute("DELETE FROM financial_statements WHERE stock_symbol = 'TEST'")
        conn.commit()
        print("✅ Test data cleaned up")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Simple insert failed: {e}")
        return False

def test_full_insert():
    """Test the full insert with all parameters"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("\n=== Testing Full Insert (Exact Same as Application) ===")
        
        # Exact same parameters from the application
        record = {
            'stock_symbol': 'AAPL',
            'period_type': 'annual',
            'statement_type': 'income_statement',
            'fiscal_period': date(2026, 12, 31),
            'payload': '{"date": "2021-09-25", "symbol": "AAPL", "reportedCurrency": "USD", "cik": "0000320193", "filingDate": "2021-10-29", "acceptedDate": "2021-10-28 18:00:00", "revenue": 365817000000, "costOfRevenue": 209136000000, "grossProfit": 156681000000, "grossProfitMargin": 0.43, "researchAndDevelopmentExpenses": 21914000000, "generalAndAdministrativeExpenses": 25049000000, "sellingAndMarketingExpenses": 26980000000, "otherExpenses": 0, "operatingExpenses": 283030000000, "costAndExpenses": 283030000000, "interestIncome": 2681000000, "interestExpense": 2931000000, "depreciationAndAmortization": 0, "ebitda": 82787000000, "ebitdaratio": 0.23, "operatingIncome": 82787000000, "operatingIncomeRatio": 0.23, "totalOtherIncomeExpensesNet": -248000000, "incomeBeforeTax": 82539000000, "incomeBeforeTaxRatio": 0.23, "incomeTaxExpense": 13855000000, "netIncome": 94680000000, "netIncomeRatio": 0.26, "eps": 5.67, "epsdiluted": 5.61, "weightedAverageShsOut": 16701272000, "weightedAverageShsOutDil": 16864919000}',
            'data_source': 'unknown',
            'created_at': datetime(2026, 1, 21, 5, 57, 3, 928344),
            'updated_at': datetime(2026, 1, 21, 5, 57, 3, 928344)
        }
        
        # Exact same SQL from the application
        sql = """
            INSERT INTO financial_statements 
            (stock_symbol, period_type, statement_type, fiscal_period, payload, data_source, created_at, updated_at)
            VALUES (%(stock_symbol)s, %(period_type)s, %(statement_type)s, %(fiscal_period)s, %(payload)s, %(data_source)s, %(created_at)s, %(updated_at)s)
            ON CONFLICT (stock_symbol, period_type, statement_type, fiscal_period)
            DO UPDATE SET
                payload = EXCLUDED.payload,
                data_source = EXCLUDED.data_source,
                updated_at = NOW()
        """
        
        print(f"SQL: {sql}")
        print(f"Parameters:")
        for key, value in record.items():
            print(f"   - {key}: {type(value).__name__} = {value}")
        
        cursor.execute(sql, record)
        conn.commit()
        print("✅ Full insert successful!")
        
        # Clean up
        cursor.execute("""
            DELETE FROM financial_statements 
            WHERE stock_symbol = %(stock_symbol)s 
              AND period_type = %(period_type)s 
              AND statement_type = %(statement_type)s 
              AND fiscal_period = %(fiscal_period)s
        """, record)
        conn.commit()
        print("✅ Test data cleaned up")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Full insert failed: {e}")
        print(f"Error type: {type(e).__name__}")
        return False

def test_alternative_insert():
    """Test alternative approaches if the main one fails"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("\n=== Testing Alternative Insert (Without ON CONFLICT) ===")
        
        record = {
            'stock_symbol': 'AAPL',
            'period_type': 'annual', 
            'statement_type': 'income_statement',
            'fiscal_period': date(2026, 12, 31),
            'payload': '{"date": "2021-09-25", "symbol": "AAPL"}',
            'data_source': 'unknown',
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        
        # Try without ON CONFLICT first
        sql = """
            INSERT INTO financial_statements 
            (stock_symbol, period_type, statement_type, fiscal_period, payload, data_source, created_at, updated_at)
            VALUES (%(stock_symbol)s, %(period_type)s, %(statement_type)s, %(fiscal_period)s, %(payload)s, %(data_source)s, %(created_at)s, %(updated_at)s)
        """
        
        cursor.execute(sql, record)
        conn.commit()
        print("✅ Alternative insert successful!")
        
        # Clean up
        cursor.execute("""
            DELETE FROM financial_statements 
            WHERE stock_symbol = %(stock_symbol)s 
              AND period_type = %(period_type)s 
              AND statement_type = %(statement_type)s 
              AND fiscal_period = %(fiscal_period)s
        """, record)
        conn.commit()
        print("✅ Test data cleaned up")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Alternative insert failed: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Testing Financial Statements SQL Insert")
    print("=" * 50)
    
    # Step 1: Fix table schema first
    if not fix_table_schema():
        print("\n❌ Schema fix failed - cannot proceed with insert tests")
        exit(1)
    
    # Step 2: Check table schema
    if not test_table_schema():
        print("\n❌ Schema check failed - cannot proceed with insert tests")
        exit(1)
    
    # Test 2: Simple insert
    if not test_simple_insert():
        print("\n❌ Simple insert failed - basic table structure issue")
        exit(1)
    
    # Test 3: Full insert (exact same as application)
    if not test_full_insert():
        print("\n❌ Full insert failed - this is the exact issue from the application")
        
        # Test 4: Alternative insert
        print("\n🔄 Trying alternative approach...")
        if not test_alternative_insert():
            print("\n❌ All insert tests failed")
            exit(1)
        else:
            print("\n✅ Alternative insert worked - issue is with ON CONFLICT clause")
    else:
        print("\n✅ Full insert worked - issue might be elsewhere")
    
    print("\n🎉 SQL testing completed!")
