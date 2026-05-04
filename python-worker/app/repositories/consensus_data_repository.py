"""
Consensus Data Repository
Handles storage and retrieval of consensus analyst data
"""
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.repositories.base_repository import BaseRepository


class ConsensusDataRepository(BaseRepository):
    """Repository for consensus analyst data"""
    
    def store_consensus(self, symbol: str, consensus_data: Dict[str, Any]) -> bool:
        """Store consensus data in database"""
        try:
            row = {
                'stock_symbol': symbol,
                'consensus_date': self._parse_date(consensus_data.get('consensusDate')),
                'analyst_count': consensus_data.get('analystCount'),
                'consensus_rating': consensus_data.get('consensusRating'),
                'consensus_price_target': consensus_data.get('consensusPriceTarget'),
                'price_target_high': consensus_data.get('priceTargetHigh'),
                'price_target_low': consensus_data.get('priceTargetLow'),
                'buy_ratings': consensus_data.get('buyRatings'),
                'hold_ratings': consensus_data.get('holdRatings'),
                'sell_ratings': consensus_data.get('sellRatings'),
                'published_at': self._parse_date(consensus_data.get('publishedAt')),
                'created_at': datetime.utcnow(),
                'payload': consensus_data
            }
            
            # Create table if not exists
            self._ensure_table()
            
            # Upsert consensus data
            BaseRepository.upsert_many(
                table='consensus_data',
                unique_columns=['stock_symbol'],
                rows=[row]
            )
            
            return True
            
        except Exception as e:
            print(f"Error storing consensus data for {symbol}: {e}")
            return False
    
    def get_consensus(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get consensus data for a symbol"""
        try:
            query = """
            SELECT payload, consensus_date, analyst_count, consensus_rating, consensus_price_target
            FROM consensus_data
            WHERE stock_symbol = %s
            ORDER BY consensus_date DESC
            LIMIT 1
            """
            result = db.execute_query(query, (symbol,))
            if result:
                return dict(result[0])
            return None
        except Exception:
            return None
    
    def _ensure_table(self):
        """Ensure consensus_data table exists"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS consensus_data (
            stock_symbol VARCHAR(20) PRIMARY KEY,
            consensus_date DATE NOT NULL,
            analyst_count INTEGER,
            consensus_rating VARCHAR(20),
            consensus_price_target DECIMAL(10,2),
            price_target_high DECIMAL(10,2),
            price_target_low DECIMAL(10,2),
            buy_ratings INTEGER,
            hold_ratings INTEGER,
            sell_ratings INTEGER,
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            payload JSONB
        );
        
        CREATE INDEX IF NOT EXISTS idx_consensus_data_date ON consensus_data(consensus_date DESC);
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
