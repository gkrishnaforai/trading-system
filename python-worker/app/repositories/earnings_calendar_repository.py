"""
Repository for earnings calendar data following our architecture pattern.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, date
import pandas as pd
from app.database import db

class EarningsCalendarRepository:
    """Repository for earnings calendar data."""
    
    @staticmethod
    def create_table():
        """Create earnings calendar table if it doesn't exist."""
        create_sql = """
        CREATE TABLE IF NOT EXISTS earnings_calendar (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            company_name VARCHAR(255),
            earnings_date DATE NOT NULL,
            eps_estimate DECIMAL(10, 2),
            eps_actual DECIMAL(10, 2),
            revenue_estimate BIGINT,
            revenue_actual BIGINT,
            quarter INTEGER,
            year INTEGER,
            time VARCHAR(50),
            market_cap BIGINT,
            sector VARCHAR(100),
            industry VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, earnings_date, quarter, year)
        );
        
        CREATE INDEX IF NOT EXISTS idx_earnings_date ON earnings_calendar(earnings_date);
        CREATE INDEX IF NOT EXISTS idx_earnings_symbol ON earnings_calendar(symbol);
        CREATE INDEX IF NOT EXISTS idx_earnings_date_range ON earnings_calendar(earnings_date, symbol);
        """
        
        db.execute_update(create_sql)
    
    @staticmethod
    def upsert_earnings(earnings_data: List[Dict[str, Any]]) -> int:
        """Insert or update earnings data using our standard pattern."""
        if not earnings_data:
            return 0
        
        # Prepare data for insertion
        inserted_count = 0
        for earnings in earnings_data:
            try:
                query = """
                    INSERT INTO earnings_calendar
                    (symbol, company_name, earnings_date, eps_estimate, eps_actual,
                     revenue_estimate, revenue_actual, quarter, year, time,
                     market_cap, sector, industry, created_at, updated_at)
                    VALUES (:symbol, :company_name, :earnings_date, :eps_estimate, :eps_actual,
                            :revenue_estimate, :revenue_actual, :quarter, :year, :time,
                            :market_cap, :sector, :industry, :created_at, :updated_at)
                    ON CONFLICT (symbol, earnings_date, quarter, year)
                    DO UPDATE SET
                      company_name = EXCLUDED.company_name,
                      eps_estimate = EXCLUDED.eps_estimate,
                      eps_actual = EXCLUDED.eps_actual,
                      revenue_estimate = EXCLUDED.revenue_estimate,
                      revenue_actual = EXCLUDED.revenue_actual,
                      time = EXCLUDED.time,
                      market_cap = EXCLUDED.market_cap,
                      sector = EXCLUDED.sector,
                      industry = EXCLUDED.industry,
                      updated_at = EXCLUDED.updated_at
                """
                
                params = {
                    "symbol": earnings.get("symbol"),
                    "company_name": earnings.get("company_name"),
                    "earnings_date": earnings.get("earnings_date"),
                    "eps_estimate": earnings.get("eps_estimate"),
                    "eps_actual": earnings.get("eps_actual"),
                    "revenue_estimate": earnings.get("revenue_estimate"),
                    "revenue_actual": earnings.get("revenue_actual"),
                    "quarter": earnings.get("quarter"),
                    "year": earnings.get("year"),
                    "time": earnings.get("time"),
                    "market_cap": earnings.get("market_cap"),
                    "sector": earnings.get("sector"),
                    "industry": earnings.get("industry"),
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                }
                
                db.execute_update(query, params)
                inserted_count += 1
                
            except Exception as e:
                # Log error but continue with other records
                print(f"Failed to upsert earnings for {earnings.get('symbol')}: {e}")
                continue
        
        return inserted_count
    
    @staticmethod
    def fetch_earnings_by_date_range(start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Fetch earnings within a date range."""
        query = """
        SELECT * FROM earnings_calendar
        WHERE earnings_date BETWEEN :start_date AND :end_date
        ORDER BY earnings_date, symbol
        """
        
        return db.execute_query(query, {"start_date": start_date, "end_date": end_date})
    
    @staticmethod
    def fetch_earnings_by_symbol(symbol: str, start_date: date = None, end_date: date = None) -> List[Dict[str, Any]]:
        """Fetch earnings for a specific symbol."""
        if start_date and end_date:
            query = """
            SELECT * FROM earnings_calendar
            WHERE symbol = :symbol AND earnings_date BETWEEN :start_date AND :end_date
            ORDER BY earnings_date DESC
            """
            params = {"symbol": symbol, "start_date": start_date, "end_date": end_date}
        else:
            query = """
            SELECT * FROM earnings_calendar
            WHERE symbol = :symbol
            ORDER BY earnings_date DESC
            LIMIT 20
            """
            params = {"symbol": symbol}
        
        return db.execute_query(query, params)
    
    @staticmethod
    def fetch_upcoming_earnings(days_ahead: int = 30) -> List[Dict[str, Any]]:
        """Fetch upcoming earnings within the next N days."""
        query = f"""
        SELECT * FROM earnings_calendar
        WHERE earnings_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '{days_ahead} days'
        ORDER BY earnings_date, market_cap DESC
        """
        
        return db.execute_query(query)
    
    @staticmethod
    def fetch_earnings_by_sector(sector: str, start_date: date = None, end_date: date = None) -> List[Dict[str, Any]]:
        """Fetch earnings for a specific sector."""
        if start_date and end_date:
            query = """
            SELECT * FROM earnings_calendar
            WHERE sector = :sector AND earnings_date BETWEEN :start_date AND :end_date
            ORDER BY earnings_date, market_cap DESC
            """
            params = {"sector": sector, "start_date": start_date, "end_date": end_date}
        else:
            query = """
            SELECT * FROM earnings_calendar
            WHERE sector = :sector AND earnings_date >= CURRENT_DATE
            ORDER BY earnings_date, market_cap DESC
            LIMIT 50
            """
            params = {"sector": sector}
        
        return db.execute_query(query, params)
    
    @staticmethod
    def delete_old_earnings(before_date: date) -> int:
        """Delete earnings data before a specific date."""
        query = "DELETE FROM earnings_calendar WHERE earnings_date < :before_date"
        
        try:
            # For DELETE, we need to handle differently since execute_update doesn't return row count
            # First count what will be deleted
            count_query = "SELECT COUNT(*) as count FROM earnings_calendar WHERE earnings_date < :before_date"
            result = db.execute_query(count_query, {"before_date": before_date})
            count = result[0]['count'] if result else 0
            
            # Then delete
            db.execute_update(query, {"before_date": before_date})
            return count
        except Exception as e:
            print(f"Failed to delete old earnings: {e}")
            return 0
