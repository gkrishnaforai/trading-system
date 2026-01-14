#!/usr/bin/env python3
"""
Add macro_market_data table inside container
"""

import psycopg2
import os

def add_macro_table():
    """Add macro_market_data table"""
    
    # Connect to database
    database_url = os.getenv('DATABASE_URL')
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    cursor = conn.cursor()
    
    # Create macro_market_data table
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS macro_market_data (
        id SERIAL PRIMARY KEY,
        data_date DATE NOT NULL UNIQUE,
        vix_close NUMERIC(8, 2),
        nasdaq_symbol VARCHAR(10),
        nasdaq_close NUMERIC(12, 4),
        nasdaq_sma50 NUMERIC(12, 4),
        nasdaq_sma200 NUMERIC(12, 4),
        tnx_yield NUMERIC(6, 4),
        irx_yield NUMERIC(6, 4),
        yield_curve_spread NUMERIC(6, 4),
        sp500_above_50d_pct NUMERIC(5, 4),
        source VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    
    cursor.execute(create_table_sql)
    print('✅ Created macro_market_data table')
    
    # Create index
    create_index_sql = """
    CREATE INDEX IF NOT EXISTS idx_macro_date 
    ON macro_market_data(data_date DESC)
    """
    
    cursor.execute(create_index_sql)
    print('✅ Created idx_macro_date index')
    
    # Verify table exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'macro_market_data'
        )
    """)
    
    table_exists = cursor.fetchone()[0]
    print(f'📊 Table exists: {table_exists}')
    
    cursor.close()
    conn.close()
    print('✅ macro_market_data table added successfully!')

if __name__ == "__main__":
    add_macro_table()
