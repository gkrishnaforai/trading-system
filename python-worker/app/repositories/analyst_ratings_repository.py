"""
Analyst Ratings Repository
Handles storage and retrieval of analyst ratings data
"""
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.repositories.base_repository import BaseRepository


class AnalystRatingsRepository(BaseRepository):
    """Repository for analyst ratings data"""
    
    def store_ratings(self, symbol: str, ratings: List[Dict[str, Any]]) -> bool:
        """Store analyst ratings in database"""
        try:
            rows = []
            for rating in ratings:
                row = {
                    'stock_symbol': symbol,
                    'rating_date': self._parse_date(rating.get('ratingDate')),
                    'analyst_name': rating.get('analystName'),
                    'analyst_firm': rating.get('analystFirm'),
                    'rating': rating.get('rating'),
                    'rating_action': rating.get('ratingAction'),
                    'price_target': rating.get('priceTarget'),
                    'published_at': self._parse_date(rating.get('publishedAt')),
                    'created_at': datetime.utcnow(),
                    'payload': rating
                }
                rows.append(row)
            
            # Create table if not exists
            self._ensure_table()
            
            # Upsert ratings
            BaseRepository.upsert_many(
                table='analyst_ratings',
                unique_columns=['stock_symbol', 'rating_date', 'analyst_name'],
                rows=rows
            )
            
            return True
            
        except Exception as e:
            print(f"Error storing analyst ratings for {symbol}: {e}")
            return False
    
    def get_recent_ratings(self, symbol: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get recent analyst ratings for a symbol"""
        try:
            query = """
            SELECT payload, rating_date, analyst_name, rating, price_target
            FROM analyst_ratings
            WHERE stock_symbol = %s
              AND rating_date >= NOW() - INTERVAL '%s days'
            ORDER BY rating_date DESC
            """
            result = db.execute_query(query, (symbol, days))
            return [dict(row) for row in result]
        except Exception:
            return []
    
    def _ensure_table(self):
        """Ensure analyst_ratings table exists"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS analyst_ratings (
            stock_symbol VARCHAR(20) NOT NULL,
            rating_date DATE NOT NULL,
            analyst_name VARCHAR(100),
            analyst_firm VARCHAR(100),
            rating VARCHAR(20),
            rating_action VARCHAR(50),
            price_target DECIMAL(10,2),
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            payload JSONB,
            PRIMARY KEY (stock_symbol, rating_date, analyst_name)
        );
        
        CREATE INDEX IF NOT EXISTS idx_analyst_ratings_symbol_date ON analyst_ratings(stock_symbol, rating_date DESC);
        """
        db.execute_query(create_table_sql)
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime"""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            return None
