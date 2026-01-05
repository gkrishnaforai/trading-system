"""
Fundamentals Repository
Handles fundamental data storage and retrieval using the repository pattern
"""

from typing import Dict, Any, Optional, List
import pandas as pd
import json
from datetime import datetime

from app.repositories.base_repository import BaseRepository
from app.database import db
from app.observability.logging import get_logger

logger = get_logger(__name__)


class FundamentalsRepository:
    """Repository for fundamental financial data"""
    
    def __init__(self):
        """Initialize fundamentals repository"""
        self.table_name = "fundamentals_snapshots"
    
    def fetch_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch latest fundamental data for a symbol
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary of fundamental data or None if not found
        """
        try:
            query = """
                SELECT *
                FROM fundamentals_snapshots
                WHERE stock_symbol = :symbol
                ORDER BY as_of_date DESC
                LIMIT 1
            """
            
            result = db.execute_query(query, {"symbol": symbol})
            
            if result and len(result) > 0:
                fundamentals = result[0]
                
                # Extract data from payload JSONB
                payload = fundamentals.get("payload", {})
                
                # PostgreSQL JSONB might return dict directly or as string
                if isinstance(payload, str):
                    # Parse JSON string back to dictionary
                    payload = json.loads(payload)
                
                if isinstance(payload, dict):
                    # Convert to clean dictionary
                    cleaned_data = {}
                    for key, value in payload.items():
                        if value is None:
                            continue

                        # pd.notna on arrays/Series returns an array, which is not safe in an if.
                        if pd.api.types.is_scalar(value) and not pd.notna(value):
                            continue

                        if isinstance(value, (int, float)):
                            cleaned_data[key] = float(value)
                        else:
                            cleaned_data[key] = value
                    
                    return cleaned_data
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {symbol}: {e}")
            return None
    
    def upsert_fundamentals(self, symbol: str, fundamentals: Dict[str, Any], 
                           snapshot_date: datetime = None) -> bool:
        """
        Insert or update fundamental data for a symbol
        
        Args:
            symbol: Stock symbol
            fundamentals: Dictionary of fundamental data
            snapshot_date: Date of the snapshot (defaults to now)
            
        Returns:
            True if successful
        """
        try:
            if snapshot_date is None:
                snapshot_date = datetime.now()
            
            # Prepare data for insertion using JSONB payload structure
            from app.utils.json_sanitize import json_dumps_sanitized
            
            data = {
                "stock_symbol": symbol,
                "as_of_date": snapshot_date.date(),
                "source": "stock_insights_service",
                "payload": json_dumps_sanitized(fundamentals),  # Serialize dict to JSON string for PostgreSQL
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            
            # Use base repository upsert method
            success = BaseRepository.upsert_many(
                table="fundamentals_snapshots",
                unique_columns=["stock_symbol", "as_of_date"],
                rows=[data]
            )
            
            if success:
                logger.info(f"Upserted fundamentals for {symbol}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error upserting fundamentals for {symbol}: {e}")
            return False
    
    def get_symbols_with_fundamentals(self, limit: int = 100) -> List[str]:
        """
        Get list of symbols that have fundamental data
        
        Args:
            limit: Maximum number of symbols to return
            
        Returns:
            List of stock symbols
        """
        try:
            query = """
                SELECT DISTINCT stock_symbol
                FROM fundamentals_snapshots
                ORDER BY as_of_date DESC
                LIMIT :limit
            """
            
            result = db.execute_query(query, {"limit": limit})
            
            if result:
                return [row["stock_symbol"] for row in result]
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting symbols with fundamentals: {e}")
            return []
