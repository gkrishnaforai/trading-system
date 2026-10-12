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
    def _has_column(table: str, column: str) -> bool:
        q = """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name = :table
              AND column_name = :column
            LIMIT 1
        """
        rows = db.execute_query(q, {"table": table, "column": column})
        return bool(rows)

    @staticmethod
    def _has_unique_constraint(table: str, columns: List[str]) -> bool:
        """Return True if a UNIQUE constraint/index exists on exactly the given ordered column list.

        Postgres matches ON CONFLICT targets against a UNIQUE index/constraint on the same column set.
        """
        q = """
            SELECT 1
            FROM pg_catalog.pg_constraint c
            JOIN pg_catalog.pg_class t ON t.oid = c.conrelid
            JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
            JOIN LATERAL (
              SELECT array_agg(a.attname::text ORDER BY x.ordinality) AS cols
              FROM unnest(c.conkey) WITH ORDINALITY AS x(attnum, ordinality)
              JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid AND a.attnum = x.attnum
            ) k ON true
            WHERE n.nspname = 'public'
              AND t.relname = :table
              AND c.contype = 'u'
              AND k.cols = :cols
            LIMIT 1
        """

        rows = db.execute_query(q, {"table": table, "cols": columns})
        return bool(rows)
    
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

        # Schema normalization: earnings_calendar has multiple variants across environments.
        date_col = "earnings_date" if EarningsCalendarRepository._has_column("earnings_calendar", "earnings_date") else None
        if date_col is None and EarningsCalendarRepository._has_column("earnings_calendar", "report_date"):
            date_col = "report_date"
        if date_col is None:
            print("earnings_calendar: no supported date column found (expected earnings_date or report_date)")
            return 0

        time_col = None
        if EarningsCalendarRepository._has_column("earnings_calendar", "earnings_time"):
            time_col = "earnings_time"
        elif EarningsCalendarRepository._has_column("earnings_calendar", "time"):
            time_col = "time"

        quarter_col = None
        if EarningsCalendarRepository._has_column("earnings_calendar", "quarter"):
            quarter_col = "quarter"
        elif EarningsCalendarRepository._has_column("earnings_calendar", "fiscal_quarter"):
            quarter_col = "fiscal_quarter"

        year_col = None
        if EarningsCalendarRepository._has_column("earnings_calendar", "year"):
            year_col = "year"
        elif EarningsCalendarRepository._has_column("earnings_calendar", "fiscal_year"):
            year_col = "fiscal_year"

        has_company = EarningsCalendarRepository._has_column("earnings_calendar", "company_name")
        has_market_cap = EarningsCalendarRepository._has_column("earnings_calendar", "market_cap")
        has_sector = EarningsCalendarRepository._has_column("earnings_calendar", "sector")
        has_industry = EarningsCalendarRepository._has_column("earnings_calendar", "industry")
        has_rev_est = EarningsCalendarRepository._has_column("earnings_calendar", "revenue_estimate")
        has_rev_act = EarningsCalendarRepository._has_column("earnings_calendar", "revenue_actual")
        has_eps_est = EarningsCalendarRepository._has_column("earnings_calendar", "eps_estimate")
        has_eps_act = EarningsCalendarRepository._has_column("earnings_calendar", "eps_actual")
        has_created_at = EarningsCalendarRepository._has_column("earnings_calendar", "created_at")
        has_updated_at = EarningsCalendarRepository._has_column("earnings_calendar", "updated_at")

        insert_cols: List[str] = ["symbol"]
        if has_company:
            insert_cols.append("company_name")
        insert_cols.append(date_col)
        if has_eps_est:
            insert_cols.append("eps_estimate")
        if has_eps_act:
            insert_cols.append("eps_actual")
        if has_rev_est:
            insert_cols.append("revenue_estimate")
        if has_rev_act:
            insert_cols.append("revenue_actual")
        if quarter_col is not None:
            insert_cols.append(quarter_col)
        if year_col is not None:
            insert_cols.append(year_col)
        if time_col is not None:
            insert_cols.append(time_col)
        if has_market_cap:
            insert_cols.append("market_cap")
        if has_sector:
            insert_cols.append("sector")
        if has_industry:
            insert_cols.append("industry")
        if has_created_at:
            insert_cols.append("created_at")
        if has_updated_at:
            insert_cols.append("updated_at")

        # Determine a conflict target that matches an existing UNIQUE constraint.
        # Environments differ: some have UNIQUE(symbol, earnings_date, quarter, year), others have
        # UNIQUE(symbol, report_date, fiscal_quarter, fiscal_year), and some only UNIQUE(symbol, <date>). 
        conflict_cols: List[str] = []
        candidate_conflicts: List[List[str]] = []
        if quarter_col is not None and year_col is not None:
            candidate_conflicts.append(["symbol", date_col, quarter_col, year_col])
        candidate_conflicts.append(["symbol", date_col])

        for cols in candidate_conflicts:
            if EarningsCalendarRepository._has_unique_constraint("earnings_calendar", cols):
                conflict_cols = cols
                break

        if conflict_cols:
            update_cols = [c for c in insert_cols if c not in conflict_cols and c != "created_at"]
            if not update_cols:
                update_clause = "DO NOTHING"
            else:
                sets = ",\n                      ".join([f"{c} = EXCLUDED.{c}" for c in update_cols])
                update_clause = f"DO UPDATE SET\n                      {sets}"
        else:
            # No matching UNIQUE constraint found. Many environments have only a PK(id) and indexes.
            # In that case ON CONFLICT cannot work, so we will do a manual upsert (delete+insert).
            update_clause = ""

        cols_sql = ", ".join(insert_cols)
        vals_sql = ", ".join([f":{c}" for c in insert_cols])
        if conflict_cols:
            conflict_sql = ", ".join(conflict_cols)
            query = f"""
                        INSERT INTO earnings_calendar
                        ({cols_sql})
                        VALUES ({vals_sql})
                        ON CONFLICT ({conflict_sql})
                        {update_clause}
                    """
        else:
            query = f"""
                        INSERT INTO earnings_calendar
                        ({cols_sql})
                        VALUES ({vals_sql})
                    """

        delete_query = None
        if not conflict_cols:
            # Natural key delete: always symbol + date; also include fiscal identifiers if present.
            # We only add predicates for fiscal fields when we have a non-null value, to avoid
            # deleting unrelated rows.
            delete_query = f"DELETE FROM earnings_calendar WHERE symbol = :symbol AND {date_col} = :{date_col}"

        inserted_count = 0
        for earnings in earnings_data:
            try:
                now = datetime.now()
                params: Dict[str, Any] = {}
                sym = earnings.get("symbol")
                params["symbol"] = sym.upper() if isinstance(sym, str) else sym
                if has_company:
                    params["company_name"] = earnings.get("company_name")
                params[date_col] = earnings.get("earnings_date") or earnings.get("report_date")
                if params.get(date_col) is None:
                    continue
                if has_eps_est:
                    params["eps_estimate"] = earnings.get("eps_estimate")
                if has_eps_act:
                    params["eps_actual"] = earnings.get("eps_actual")
                if has_rev_est:
                    params["revenue_estimate"] = earnings.get("revenue_estimate")
                if has_rev_act:
                    params["revenue_actual"] = earnings.get("revenue_actual")
                if quarter_col is not None:
                    qv = earnings.get("quarter") or earnings.get("fiscal_quarter")
                    if quarter_col == "fiscal_quarter" and qv is not None:
                        qv = str(qv)
                    params[quarter_col] = qv
                if year_col is not None:
                    params[year_col] = earnings.get("year") or earnings.get("fiscal_year")
                if time_col is not None:
                    params[time_col] = earnings.get("earnings_time") or earnings.get("time")
                if has_market_cap:
                    params["market_cap"] = earnings.get("market_cap")
                if has_sector:
                    params["sector"] = earnings.get("sector")
                if has_industry:
                    params["industry"] = earnings.get("industry")
                if has_created_at:
                    params["created_at"] = now
                if has_updated_at:
                    params["updated_at"] = now

                if delete_query is not None:
                    dq = delete_query
                    # Only constrain on fiscal fields when value is present.
                    if quarter_col is not None and params.get(quarter_col) is not None:
                        dq += f" AND {quarter_col} = :{quarter_col}"
                    if year_col is not None and params.get(year_col) is not None:
                        dq += f" AND {year_col} = :{year_col}"
                    db.execute_update(dq, params)
                db.execute_update(query, params)
                inserted_count += 1
            except Exception as e:
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
