"""
Stock Insights Repository
Handles storing and retrieving stock insights snapshots with entry/exit plans and reasoning
"""

from typing import Dict, Any, Optional, List
import json
from datetime import datetime

from app.repositories.base_repository import BaseRepository
from app.database import db
from app.observability.logging import get_logger

logger = get_logger(__name__)


class StockInsightsRepository:
    """Repository for stock insights snapshots"""
    
    def __init__(self):
        """Initialize stock insights repository"""
        self.table_name = "stock_insights_snapshots"
    
    def save_insights(self, symbol: str, insights: Dict[str, Any]) -> bool:
        """
        Save stock insights snapshot to database
        
        Args:
            symbol: Stock symbol
            insights: Complete insights data with entry/exit plans
            
        Returns:
            True if successful
        """
        try:
            # Prepare data for insertion
            data = {
                "stock_symbol": symbol,
                "insights_date": datetime.now().date(),
                "generated_at": datetime.now(),
                "source": "stock_insights_service",
                "payload": json.dumps(insights),  # Store as JSONB
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            
            # Use base repository upsert method
            success = BaseRepository.upsert_many(
                table="stock_insights_snapshots",
                unique_columns=["stock_symbol", "insights_date"],
                rows=[data]
            )
            
            if success:
                logger.info(f"Saved insights snapshot for {symbol}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error saving insights for {symbol}: {e}")
            return False
    
    def fetch_latest_insights(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch latest insights snapshot for a symbol
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Complete insights data or None if not found
        """
        try:
            query = """
                SELECT *
                FROM stock_insights_snapshots
                WHERE stock_symbol = :symbol
                ORDER BY insights_date DESC, generated_at DESC
                LIMIT 1
            """
            
            result = db.execute_query(query, {"symbol": symbol})
            
            if result and len(result) > 0:
                insights = result[0]
                
                # Extract data from payload JSONB
                payload_str = insights.get("payload", "{}")
                
                # PostgreSQL JSONB might return dict directly or as string
                if isinstance(payload_str, str):
                    payload = json.loads(payload_str)
                else:
                    payload = payload_str
                
                if isinstance(payload, dict):
                    # Add metadata
                    payload["generated_at"] = insights.get("generated_at")
                    payload["insights_date"] = insights.get("insights_date")
                    return payload
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching insights for {symbol}: {e}")
            return None
    
    def get_symbols_with_insights(self, limit: int = 100) -> List[str]:
        """
        Get list of symbols that have insights snapshots
        
        Args:
            limit: Maximum number of symbols to return
            
        Returns:
            List of stock symbols
        """
        try:
            query = """
                SELECT DISTINCT stock_symbol
                FROM stock_insights_snapshots
                ORDER BY insights_date DESC
                LIMIT :limit
            """
            
            result = db.execute_query(query, {"limit": limit})
            
            if result:
                return [row["stock_symbol"] for row in result]
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting symbols with insights: {e}")
            return []
