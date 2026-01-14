#!/usr/bin/env python3
"""Fix missing source column in raw_market_data_intraday table"""

import sys
import os
sys.path.append('/app')

from app.database import db
from app.observability.logging import get_logger

logger = get_logger("fix_schema")

def fix_intraday_schema():
    """Fix missing source column in raw_market_data_intraday table"""
    try:
        # Initialize database connection
        db.initialize()
        
        # Check if source column exists
        check_query = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'raw_market_data_intraday' 
            AND column_name = 'source'
        """
        
        result = db.execute_query(check_query)
        
        if result:
            logger.info("✅ Source column already exists in raw_market_data_intraday table")
            print("✅ Source column already exists")
            return True
        
        # Add source column if it doesn't exist
        alter_query = """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'raw_market_data_intraday' 
                    AND column_name = 'source'
                ) THEN
                    ALTER TABLE raw_market_data_intraday ADD COLUMN source TEXT;
                    
                    -- Update primary key to include source
                    ALTER TABLE raw_market_data_intraday DROP CONSTRAINT IF EXISTS raw_market_data_intraday_pkey;
                    ALTER TABLE raw_market_data_intraday ADD PRIMARY KEY (stock_symbol, ts, interval, source);
                    
                    RAISE NOTICE 'Added source column to raw_market_data_intraday';
                END IF;
            END $$;
        """
        
        db.execute_update(alter_query)
        
        logger.info("✅ Fixed raw_market_data_intraday table schema")
        print("✅ Successfully added source column to raw_market_data_intraday table")
        return True
        
    except Exception as e:
        logger.error(f"Failed to fix intraday schema: {e}")
        print(f"❌ Failed to fix schema: {str(e)}")
        return False
    finally:
        if db.engine:
            db.close()

if __name__ == "__main__":
    success = fix_intraday_schema()
    sys.exit(0 if success else 1)
